import os
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from modules.db.orm_utils import SessionLocal
from modules.db.orm_models import UploadedDocument, File
from .points_system import add_points  # 添加导入

# 允许的文件类型
ALLOWED_EXTENSIONS = {'.txt', '.epub', '.pdf', '.mobi'}

# 下载目录
DOWNLOAD_DIR = os.path.join(os.getenv('TXT_ROOT', '/app/share_folder'), 'downloaded_docs').replace('\\', '/')
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理用户上传的文档"""
    if not update.message or not update.message.document:
        return

    user_id = update.effective_user.id
    document = update.message.document
    
    # 检查文件类型
    file_ext = os.path.splitext(document.file_name)[1].lower()
    if file_ext not in ALLOWED_EXTENSIONS:
        await update.message.reply_text("抱歉，只接受txt、epub、pdf和mobi格式的文件。")
        return

    # 检查是否重复
    with SessionLocal() as session:
        # 检查文件名和大小
        existing = session.query(UploadedDocument).filter_by(
            file_name=document.file_name,
            file_size=document.file_size
        ).first()
        
        if existing:
            await update.message.reply_text("该文件已经上传过了。")
            return
            
        # 检查 tg_file_id
        existing_by_tg_id = session.query(UploadedDocument).filter_by(
            tg_file_id=document.file_id
        ).first()
        
        if existing_by_tg_id:
            await update.message.reply_text("该文件已经上传过了。")
            return

        # 检查 files 表中是否存在相同文件
        existing_file = session.query(File).filter(
            (File.file_size == document.file_size) |
            (File.file_path.like(f"%{document.file_name}"))
        ).first()
        
        if existing_file:
            await update.message.reply_text("该文件已经存在于系统中。")
            return

        # 创建新记录
        new_doc = UploadedDocument(
            user_id=user_id,
            file_name=document.file_name,
            file_size=document.file_size,
            tg_file_id=document.file_id,
            upload_time=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        )
        session.add(new_doc)
        session.commit()
        doc_id = new_doc.id

    # 创建管理员操作按钮
    keyboard = [
        [
            InlineKeyboardButton("收录", callback_data=f"doc_approve_{doc_id}"),
            InlineKeyboardButton("收录并下载", callback_data=f"doc_approve_download_{doc_id}"),
            InlineKeyboardButton("拒绝", callback_data=f"doc_reject_{doc_id}")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # 转发给所有管理员
    admin_message = (
        f"新文档上传通知\n"
        f"用户ID: {user_id}\n"
        f"文件名: {document.file_name}\n"
        f"文件大小: {document.file_size} 字节\n"
        f"上传时间: {new_doc.upload_time}"
    )
    
    for admin_id in context.bot_data.get('admin_ids', []):
        try:
            await context.bot.send_document(
                chat_id=admin_id,
                document=document.file_id,
                caption=admin_message,
                reply_markup=reply_markup,
                disable_notification=True
            )
        except Exception as e:
            print(f"发送给管理员 {admin_id} 失败: {e}")

    await update.message.reply_text("您的文档已提交给管理员审核。")

async def handle_document_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理管理员对文档的操作"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    # 验证是否是管理员
    if user_id not in context.bot_data.get('admin_ids', []):
        await query.answer("只有管理员可以执行此操作")
        return

    # 解析回调数据
    parts = query.data.split('_')
    if len(parts) < 3:
        await query.answer("无效的操作")
        return
        
    action = f"{parts[1]}_{parts[2]}" if len(parts) > 3 else parts[1]
    doc_id = int(parts[-1])

    with SessionLocal() as session:
        doc = session.query(UploadedDocument).filter_by(id=doc_id).first()
        if not doc:
            await query.answer("文档不存在")
            return

        if action == "approve":
            doc.status = 'approved'
            doc.approved_by = user_id
            # 给用户增加5积分
            new_points = add_points(doc.user_id, 5)
            await query.edit_message_caption(
                caption=query.message.caption + "\n\n✅ 已收录"
            )
            # 通知用户
            try:
                await context.bot.send_message(
                    chat_id=doc.user_id,
                    text=f"您的文档《{doc.file_name}》已被管理员收录。\n获得5积分奖励！当前积分：{new_points}"
                )
            except Exception as e:
                print(f"通知用户失败: {e}")
            
        elif action == "approve_download":
            # 检查文件是否已经被下载
            if doc.is_downloaded and doc.download_path and os.path.exists(doc.download_path):
                await query.answer("文件已经被其他管理员下载过了")
                return
                
            doc.status = 'approved'
            doc.approved_by = user_id
            doc.is_downloaded = True
            
            try:
                # 获取文件信息
                print(f"Getting file info for file_id: {doc.tg_file_id}")  # 调试信息
                file_info = await context.bot.get_file(doc.tg_file_id)
                print(f"File info: {file_info}")  # 调试信息
                
                if not file_info:
                    raise Exception("无法获取文件信息")

                # 下载文件
                download_path = os.path.join(DOWNLOAD_DIR, doc.file_name).replace('\\', '/')
                
                # 使用download_to_drive下载文件
                print(f"Downloading to: {download_path}")  # 调试信息
                await file_info.download_to_drive(
                    custom_path=download_path,
                    read_timeout=30,
                    write_timeout=30,
                    connect_timeout=30,
                    pool_timeout=30
                )
                
                doc.download_path = download_path
                # 给用户增加5积分
                new_points = add_points(doc.user_id, 5)
                await query.edit_message_caption(
                    caption=query.message.caption + "\n\n✅ 已收录并下载"
                )
                # 通知用户
                try:
                    await context.bot.send_message(
                        chat_id=doc.user_id,
                        text=f"您的文档《{doc.file_name}》已被管理员收录。\n获得5积分奖励！当前积分：{new_points}"
                    )
                except Exception as e:
                    print(f"通知用户失败: {e}")
                    
            except Exception as e:
                print(f"下载文件失败: {str(e)}")
                await query.edit_message_caption(
                    caption=query.message.caption + "\n\n⚠️ 已收录但下载失败，请重试"
                )
                await query.answer("文件下载失败，但已标记为收录")
                # 通知用户下载失败
                try:
                    await context.bot.send_message(
                        chat_id=doc.user_id,
                        text=f"您的文档《{doc.file_name}》已被收录，但下载存档失败，管理员将重试。"
                    )
                except Exception as e:
                    print(f"通知用户失败: {e}")
            
        elif action == "reject":
            doc.status = 'rejected'
            await query.edit_message_caption(
                caption=query.message.caption + "\n\n❌ 已拒绝"
            )
            # 通知用户
            try:
                await context.bot.send_message(
                    chat_id=doc.user_id,
                    text=f"您的文档《{doc.file_name}》已被管理员拒绝。"
                )
            except Exception as e:
                print(f"通知用户失败: {e}")
        
        try:
            session.commit()
            await query.answer("操作已完成")
        except Exception as e:
            print(f"数据库更新失败: {str(e)}")
            session.rollback()
            await query.answer("操作失败，请重试")

async def batch_approve_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """批量批准所有待审核的文档"""
    user_id = update.effective_user.id
    if user_id not in context.bot_data.get('admin_ids', []):
        await update.message.reply_text('只有管理员可以使用此命令。')
        return

    with SessionLocal() as session:
        # 获取所有待审核的文档
        pending_docs = session.query(UploadedDocument).filter(
            UploadedDocument.status == 'pending'
        ).all()
        
        if not pending_docs:
            await update.message.reply_text('没有待审核的文档。')
            return
        
        approved_count = 0
        for doc in pending_docs:
            doc.status = 'approved'
            doc.approved_by = user_id
            # 给用户增加5积分
            new_points = add_points(doc.user_id, 5)
            approved_count += 1
            
            # 通知用户
            try:
                await context.bot.send_message(
                    chat_id=doc.user_id,
                    text=f"您的文档《{doc.file_name}》已被管理员收录。\n获得5积分奖励！当前积分：{new_points}"
                )
            except Exception as e:
                print(f"通知用户失败: {e}")
        
        try:
            session.commit()
            await update.message.reply_text(f'成功批准了 {approved_count} 个文档。')
        except Exception as e:
            session.rollback()
            await update.message.reply_text(f'操作失败：{str(e)}')