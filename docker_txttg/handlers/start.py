from telegram import Update
from telegram.ext import ContextTypes
from services.user_service import ensure_user, get_sent_file_ids
from utils.db import SessionLocal, File, UploadedDocument
import os
from services.file_service import mark_file_sent

async def on_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /start 命令"""
    user_id = update.effective_user.id
    ensure_user(user_id)
    count = get_sent_file_ids(user_id)
    await update.message.reply_text(f'你已收到 {count} 个文件。') 

async def on_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args and update.message:
        # 显示欢迎信息
        welcome_text = """👋 欢迎使用文件分享机器人！

🤖 这是一个文件分享机器人，你可以：
• 搜索和获取文件
• 每日签到获取积分
• 使用积分兑换VIP

📚 发送 /help 查看完整使用指南
🎯 发送 /checkin 进行每日签到
🔍 发送 /search 搜索文件

如有问题，请联系管理员。"""
        await update.message.reply_text(welcome_text)
        return

    # 处理 deep link 参数
    if update.message:
        start_param = update.message.text.split(' ', 1)[1] if ' ' in update.message.text else ''
    elif update.callback_query:
        start_param = update.callback_query.data.split(' ', 1)[1] if ' ' in update.callback_query.data else ''
    else:
        start_param = ''
    
    if start_param.startswith('upload_'):
        # 处理上传文档
        try:
            doc_id = int(start_param.split('_')[1])
            with SessionLocal() as session:
                doc = session.query(UploadedDocument).filter_by(id=doc_id).first()
                if doc and doc.tg_file_id:
                    # 先发送文件信息
                    info_text = f"""📄 文件信息：
• 文件名：{doc.file_name}
• 上传时间：{doc.upload_time}
• 文件大小：{doc.file_size} bytes

正在发送文件..."""
                    await update.message.reply_text(info_text)
                    # 然后发送文件
                    await update.message.reply_document(doc.tg_file_id)
                    mark_file_sent(update.effective_user.id, doc_id, source='uploaded')
                else:
                    await update.message.reply_text('文件不存在或已被删除。')
        except Exception as e:
            await update.message.reply_text(f'获取文件失败: {str(e)}')
    elif start_param.startswith('file_'):
        # 处理普通文件
        try:
            file_id = int(start_param.split('_')[1])
            with SessionLocal() as session:
                file = session.query(File).filter_by(file_id=file_id).first()
                if file:
                    if file.tg_file_id:
                        # 如果有 tg_file_id，直接发送带说明的文件
                        caption = f"file id: `{file.tg_file_id}`"
                        await update.message.reply_document(file.tg_file_id, caption=caption, parse_mode='Markdown')
                    elif file.file_path and os.path.exists(file.file_path):
                        # 如果是本地文件，先发送带临时说明的文件
                        with open(file.file_path, 'rb') as f:
                            msg = await update.message.reply_document(
                                f,
                                caption="正在生成文件ID..."
                            )
                            # 获取新生成的 tg_file_id
                            if msg.document:
                                tg_file_id = msg.document.file_id
                                # 更新数据库中的 tg_file_id
                                file.tg_file_id = tg_file_id
                                session.commit()
                                # 更新消息说明
                                await msg.edit_caption(caption=f"file id: `{tg_file_id}`", parse_mode='Markdown')
                    else:
                        await update.message.reply_text('文件不存在或已被删除。')
                    mark_file_sent(update.effective_user.id, file_id, source='file')
                else:
                    await update.message.reply_text('文件不存在或已被删除。')
        except Exception as e:
            await update.message.reply_text(f'获取文件失败: {str(e)}')