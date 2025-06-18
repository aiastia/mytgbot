from telegram import Update
from telegram.ext import ContextTypes
from utils.file import reload_txt_files
from config import ADMIN_IDS

async def reload_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text('无权限，仅管理员可用。')
        return
    inserted, skipped = reload_txt_files()
    await update.message.reply_text(f'刷新完成，新增 {inserted} 个文件，跳过 {skipped} 个已存在。')
