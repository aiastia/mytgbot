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
from .document_service import check_duplicate_and_save, approve_document, reject_document, approve_and_download_document, get_pending_documents, batch_approve_documents, batch_download_documents
from .document_utils import format_document_list_message, build_pagination_keyboard
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

    with SessionLocal() as session:
        result = check_duplicate_and_save(session, document, user_id)
        if result == "duplicate":
            await update.message.reply_text("该文件已经上传过了。")
            return
        if result == "exists_in_system":
            await update.message.reply_text("该文件已经存在于系统中。")
            return
        if isinstance(result, UploadedDocument):
            doc_id = result.id
        else:
            await update.message.reply_text("文件保存失败，请重试。")
            return

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
        f"上传时间: {result.upload_time}"
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
        if action == "approve":
            doc, new_points = approve_document(session, doc_id, user_id)
            if not doc:
                await query.answer("文档不存在")
                return
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
            doc, result = await approve_and_download_document(session, doc_id, user_id, context.bot)
            if not doc:
                await query.answer(result or "文档不存在")
                return
            if isinstance(result, str) and result.startswith("下载失败"):
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
            else:
                await query.edit_message_caption(
                    caption=query.message.caption + "\n\n✅ 已收录并下载"
                )
                # 通知用户
                try:
                    await context.bot.send_message(
                        chat_id=doc.user_id,
                        text=f"您的文档《{doc.file_name}》已被管理员收录。\n获得5积分奖励！当前积分：{result}"
                    )
                except Exception as e:
                    print(f"通知用户失败: {e}")
        elif action == "reject":
            doc = reject_document(session, doc_id, user_id)
            if not doc:
                await query.answer("文档不存在")
                return
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
        approved_count, approved_docs = batch_approve_documents(session, user_id)
        if not approved_docs:
            await update.message.reply_text('没有待审核的文档。')
            return
        for doc in approved_docs:
            try:
                await context.bot.send_message(
                    chat_id=doc.user_id,
                    text=f"您的文档《{doc.file_name}》已被管理员收录。\n获得5积分奖励！"
                )
            except Exception as e:
                print(f"通知用户失败: {e}")
        await update.message.reply_text(f'成功批准了 {approved_count} 个文档。')

async def download_pending_files(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """下载待处理的文件，支持 all、all N、指定ID列表等参数"""
    user_id = update.effective_user.id
    if user_id not in ADMIN_USER_ID:
        await update.effective_message.reply_text("⚠️ 此命令仅限管理员使用")
        return

    # 获取消息对象
    message = update.callback_query.message if update.callback_query else update.message

    # 参数解析
    args = context.args if context.args else []
    arg_str = ' '.join(args).strip().lower()

    # 用法提示
    usage = (
        "【用法说明】\n"
        "1. <b>/download_pending all</b> —— 下载全部待下载文件\n"
        "2. <b>/download_pending all 100</b> —— 下载前100个待下载文件\n"
        "3. <b>/download_pending 123 456</b> —— 下载指定ID的文件（可多个）\n"
        "4. <b>/download_pending 123</b> —— 下载ID为123的文件\n"
        "\n如需帮助请联系管理员。"
    )

    if not args:
        await message.reply_text(usage, parse_mode='HTML')
        return

    session = SessionLocal()
    status_message = None
    try:
        docs = []
        # 1. all 或 all N
        if args[0] == 'all':
            limit = None
            if len(args) > 1 and args[1].isdigit():
                limit = int(args[1])
            # 获取全部待下载文件
            all_docs, _, _ = get_pending_documents(session, 1, 200)
            docs = all_docs[:limit] if limit else all_docs
            if not docs:
                await message.reply_text("📭 没有待下载的文件")
                session.close()
                return
        else:
            # 2. 指定ID列表
            file_ids = [int(arg) for arg in args if arg.isdigit()]
            if not file_ids:
                await message.reply_text(f"参数无效！\n{usage}")
                session.close()
                return
            docs = session.query(UploadedDocument).filter(UploadedDocument.id.in_(file_ids)).all()
            if not docs:
                await message.reply_text("未找到指定ID的待下载文件")
                session.close()
                return

        # 发送状态消息
        status_message = await message.reply_text(f'开始下载 {len(docs)} 个文件...')

        # 批量下载文件
        result = await batch_download_documents(session, docs, context.bot, DOWNLOAD_DIR)
        successful = result['successful']
        failed = result['failed']
        error_details = result['error_details']

        # 构建状态消息
        status_text = (
            f"📥 下载完成！\n"
            f"✅ 成功: {successful}\n"
            f"❌ 失败: {failed}\n"
            f"📊 总计: {len(docs)}"
        )
        if failed > 0:
            status_text += "\n\n❌ 失败详情:"
            for doc_id, error in error_details.items():
                error_msg = f"\n文档ID {doc_id}: {error[:100]}..." if len(error) > 100 else f"\n文档ID {doc_id}: {error}"
                if len(status_text + error_msg) > 4000:
                    status_text += "\n...(更多错误信息已省略)"
                    break
                status_text += error_msg

        session.commit()
        await status_message.edit_text(status_text)

    except Exception as e:
        session.rollback()
        error_msg = f"❌ 发生错误: {str(e)}"
        print(f"Error in download_pending_files: {str(e)}")
        if status_message:
            if len(error_msg) > 4096:
                error_msg = error_msg[:4093] + "..."
            await status_message.edit_text(error_msg)
        else:
            await message.reply_text(error_msg)
    finally:
        session.close()

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
        docs, total_count, total_pages = get_pending_documents(session, page, page_size)
        
        if total_count == 0:
            await message.reply_text("📭 目前没有待下载的文件")
            return
            
        if page < 1:
            page = 1
        elif page > total_pages:
            page = total_pages
            
        # 构建文件列表消息
        msg = format_document_list_message(docs, page, total_pages, total_count)
        reply_markup = build_pagination_keyboard(page, total_pages)

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
    query = update.callback_query
    data = query.data.split('_')
    if len(data) != 2:
        await query.answer("无效的回调数据")
        return

    action = data[0]
    page = int(data[1])
    
    if action == "pendinglist":
        try:
            context.args = [str(page)]
            await list_pending_downloads(update, context)
            await query.answer()
        except BadRequest as e:
            if "message is not modified" in str(e).lower():
                await query.answer("列表已是最新状态")
            else:
                raise
    elif action == "dlpending":
        user_id = update.effective_user.id
        if user_id not in ADMIN_USER_ID:
            await query.answer("⚠️ 仅管理员可操作")
            return
            
        status_message = None
        session = SessionLocal()
        try:
            page_size = 5
            docs, _, _ = get_pending_documents(session, page, page_size)
            if not docs:
                await query.answer("当前页面没有可下载的文件")
                session.close()
                return
                
            status_message = await query.message.reply_text('开始下载当前页文件...')
            
            # 批量下载文件
            result = await batch_download_documents(session, docs, context.bot, DOWNLOAD_DIR)
            successful = result['successful']
            failed = result['failed']
            error_details = result['error_details']
            
            # 提交事务前确保更新状态消息
            status_text = f"📥 下载完成！\n✅ 成功: {successful}\n❌ 失败: {failed}\n📊 总计: {len(docs)}"
            
            # 如果有失败的文件，添加错误详情
            if failed > 0:
                status_text += "\n\n❌ 失败详情:"
                for doc_id, error in error_details.items():
                    status_text += f"\n文档ID {doc_id}: {error[:100]}..." if len(error) > 100 else f"\n文档ID {doc_id}: {error}"
            
            # 确保提交事务
            session.commit()
            
            # 更新状态消息
            await status_message.edit_text(status_text)
            await query.answer("已完成当前页下载")
            
        except Exception as e:
            print(f"下载过程出错: {str(e)}")
            session.rollback()
            error_msg = f"❌ 下载过程出错: {str(e)}"
            if len(error_msg) > 4096:  # Telegram消息长度限制
                error_msg = error_msg[:4093] + "..."
            if status_message:
                await status_message.edit_text(error_msg)
            await query.answer("下载出错，请查看错误信息")
        finally:
            session.close()