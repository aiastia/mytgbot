import os
import asyncio
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.error import BadRequest
from ..config.config import ADMIN_USER_ID, DOWNLOAD_DIR, ALLOWED_EXTENSIONS
from modules.db.orm_utils import SessionLocal
from modules.db.orm_models import UploadedDocument, File
from .points_system import add_points  # 添加导入
# 允许的文件类型
# ALLOWED_EXTENSIONS = {'.txt', '.epub', '.pdf', '.mobi'}
# # 下载目录
# DOWNLOAD_DIR = os.path.join(os.getenv('TXT_ROOT', '/app/share_folder'), 'downloaded_docs').replace('\\', '/')
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

async def download_pending_files(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """下载待处理的文件"""
    # 检查是否为管理员
    user_id = update.effective_user.id
    if user_id not in ADMIN_USER_ID:
        await update.effective_message.reply_text("⚠️ 此命令仅限管理员使用")
        return
        
    # 获取消息对象
    message = update.callback_query.message if update.callback_query else update.message
    
    # 发送状态消息
    status_message = await message.reply_text('开始下载文件...')
    
    try:
        # 获取指定的文件ID
        file_ids = []
        if context.args:
            file_ids = [int(arg) for arg in context.args if arg.isdigit()]
        
        with SessionLocal() as session:
            # 如果没有指定ID，获取所有待下载的文件
            if not file_ids:
                pending_docs = session.query(UploadedDocument).filter(
                    UploadedDocument.status == 'approved',
                    UploadedDocument.is_downloaded == False,
                    UploadedDocument.file_size < 20 * 1024 * 1024  # 小于20MB的文件
                ).all()
                file_ids = [doc.id for doc in pending_docs]
            
            if not file_ids:
                await status_message.edit_text("📭 没有待下载的文件")
                return
                
            total_files = len(file_ids)
            successful = 0
            failed = 0
            
            for i, file_id in enumerate(file_ids, 1):
                try:
                    # 获取文件信息
                    doc = session.query(UploadedDocument).filter(UploadedDocument.id == file_id).first()
                    if not doc:
                        await status_message.edit_text(f"❌ 未找到ID为 {file_id} 的文件")
                        failed += 1
                        continue
                        
                    # 检查文件大小
                    if doc.file_size >= 20 * 1024 * 1024:  # 20MB
                        await status_message.edit_text(
                            f"⚠️ 文件太大 (ID: {file_id}, 大小: {doc.file_size/1024/1024:.1f}MB)"
                        )
                        failed += 1
                        await asyncio.sleep(2)
                        continue
                    
                    # 更新状态消息
                    await status_message.edit_text(
                        f"正在下载第 {i}/{total_files} 个文件...\n"
                        f"✅ 成功: {successful}\n"
                        f"❌ 失败: {failed}"
                    )
                      # 下载文件
                    file = await context.bot.get_file(doc.tg_file_id)
                    file_name = doc.file_name
                    
                    # 确保下载目录存在
                    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
                    
                    # 构建完整的下载路径
                    download_path = os.path.join(DOWNLOAD_DIR, file_name).replace('\\', '/')
                    await file.download_to_drive(custom_path=download_path)
                    
                    # 更新文件的下载路径
                    doc.download_path = download_path
                    
                    # 更新数据库状态
                    doc.is_downloaded = True
                    session.commit()
                    
                    successful += 1
                    
                except Exception as e:
                    error_msg = f"下载文件 {file_id} 时出错: {str(e)}"
                    print(error_msg)
                    # 更新状态消息，显示具体的错误信息
                    await status_message.edit_text(
                        f"下载第 {i}/{total_files} 个文件时出错\n"
                        f"文件ID: {file_id}\n"
                        f"错误信息: {str(e)}\n"
                        f"✅ 成功: {successful}\n"
                        f"❌ 失败: {failed + 1}"
                    )
                    failed += 1
                    # 等待一会儿让用户看到错误信息
                    await asyncio.sleep(3)
                    continue
            
            # 更新最终状态
            await status_message.edit_text(
                f"📥 下载完成！\n"
                f"✅ 成功: {successful}\n"
                f"❌ 失败: {failed}\n"
                f"📊 总计: {total_files}"
            )
            
    except Exception as e:
        await status_message.edit_text(f"❌ 发生错误: {str(e)}")
        print(f"Error in download_pending_files: {str(e)}")

async def list_pending_downloads(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """显示待下载文件的分页列表"""
    # 检查是否为回调查询
    message = update.callback_query.message if update.callback_query else update.message
    
    # 获取页码参数
    page = 1
    if context.args and context.args[0].isdigit():
        page = int(context.args[0])
    
    with SessionLocal() as session:
        # 计算总数和页数
        page_size = 5
        total_count = session.query(UploadedDocument).filter(
            UploadedDocument.status == 'approved',
            UploadedDocument.is_downloaded == False
        ).count()
        
        total_pages = (total_count + page_size - 1) // page_size
        
        if total_count == 0:
            await message.reply_text("📭 目前没有待下载的文件")
            return
            
        if page < 1:
            page = 1
        elif page > total_pages:
            page = total_pages
            
        # 获取当前页的文件
        pending_docs = session.query(UploadedDocument).filter(
            UploadedDocument.status == 'approved',
            UploadedDocument.is_downloaded == False
        ).order_by(
            UploadedDocument.file_size.asc()
        ).offset(
            (page - 1) * page_size
        ).limit(page_size).all()

        # 构建文件列表消息
        msg = f"📥 <b>待下载文件列表</b> (第{page}/{total_pages}页)\n"
        msg += f"共{total_count}个文件待下载\n\n"

        for doc in pending_docs:
            size_mb = doc.file_size / (1024 * 1024)
            status = "✅ 可下载" if size_mb < 20 else "❌ 过大"
            msg += (
                f"ID: <code>{doc.id}</code>\n"
                f"📁 {doc.file_name}\n"
                f"📊 {size_mb:.1f}MB {status}\n"
                f"👤 上传者ID: {doc.user_id}\n"
                f"⏰ 上传时间: {doc.upload_time}\n"
                "------------------------\n"
            )

        # 添加导航按钮
        keyboard = []
        nav_buttons = []

        if page > 1:
            nav_buttons.append(
                InlineKeyboardButton("⬅️ 上一页", callback_data=f"pendinglist_{page-1}")
            )
        if page < total_pages:
            nav_buttons.append(
                InlineKeyboardButton("➡️ 下一页", callback_data=f"pendinglist_{page+1}")
            )

        if nav_buttons:
            keyboard.append(nav_buttons)

        # 添加操作按钮
        keyboard.append([
            InlineKeyboardButton("🔄 刷新", callback_data=f"pendinglist_{page}"),
            InlineKeyboardButton("📥 下载当前页", callback_data=f"dlpending_{page}")
        ])

        reply_markup = InlineKeyboardMarkup(keyboard)

        # 如果是回调查询，编辑现有消息；否则发送新消息
        if update.callback_query:
            await message.edit_text(
                msg,
                parse_mode='HTML',
                reply_markup=reply_markup
            )
        else:
            await message.reply_text(
                msg,
                parse_mode='HTML',
                reply_markup=reply_markup
            )

async def list_pending_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理待下载列表的回调按钮"""
    query = update.callback_query
    
    data = query.data.split('_')
    if len(data) != 2:
        await query.answer("无效的回调数据")
        return
    
    action = data[0]
    page = int(data[1])
    
    if action == "pendinglist":
        try:
            # 重新构建消息，调用 list_pending_downloads
            context.args = [str(page)]
            await list_pending_downloads(update, context)
            await query.answer()
        except BadRequest as e:
            if "message is not modified" in str(e).lower():
                # 如果消息内容没有变化，只显示通知
                await query.answer("列表已是最新状态")
            else:
                # 其他错误则重新抛出
                raise
    
    elif action == "dlpending":
        # 下载当前页的文件
        with SessionLocal() as session:
            page_size = 5
            docs = session.query(UploadedDocument).filter(
                UploadedDocument.status == 'approved',
                UploadedDocument.is_downloaded == False
            ).order_by(
                UploadedDocument.file_size.asc()
            ).offset(
                (page - 1) * page_size
            ).limit(page_size).all()
            
            doc_ids = [doc.id for doc in docs]
        
        if not doc_ids:
            await query.answer("当前页面没有可下载的文件")
            return
            
        # 为每个文件ID调用下载函数
        for doc_id in doc_ids:
            context.args = [str(doc_id)]
            await download_pending_files(update, context)
        
        await query.answer("已开始下载当前页的所有文件")