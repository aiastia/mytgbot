from telegram import Update
from telegram.ext import ContextTypes
from utils.file import reload_txt_files
from config import ADMIN_IDS

async def reload_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理重载文件命令"""
    user_id = update.effective_user.id
    
    # 检查是否是管理员
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("此命令仅限管理员使用！")
        return
    
    # 发送开始消息
    message = await update.message.reply_text("开始重载文件...")
    
    # 重载文件
    try:
        reload_txt_files()
        await message.edit_text("文件重载完成！")
    except Exception as e:
        await message.edit_text(f"文件重载失败：{str(e)}") 