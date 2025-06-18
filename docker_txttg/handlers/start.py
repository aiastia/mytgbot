from telegram import Update
from telegram.ext import ContextTypes
from services.user_service import ensure_user, get_sent_file_ids

async def on_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /start 命令"""
    user_id = update.effective_user.id
    ensure_user(user_id)
    count = get_sent_file_ids(user_id)
    await update.message.reply_text(f'你已收到 {count} 个文件。') 