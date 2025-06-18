from telegram import Update
from telegram.ext import ContextTypes
from utils.db import SessionLocal, File
from config import ADMIN_IDS

async def getfile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理获取文件命令"""
    user_id = update.effective_user.id
    
    # 检查是否是管理员
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("此命令仅限管理员使用！")
        return
    
    # 获取文件ID
    if not context.args:
        await update.message.reply_text("请提供文件ID！")
        return
    
    try:
        file_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("文件ID必须是数字！")
        return
    
    # 获取文件信息
    session = SessionLocal()
    file = session.query(File).filter_by(file_id=file_id).first()
    
    if not file:
        await update.message.reply_text("文件不存在！")
        return
    
    # 发送文件信息
    file_info = f"""
📁 文件信息：
ID: {file.file_id}
名称: {file.file_name}
大小: {file.file_size} 字节
路径: {file.file_path}
Telegram ID: {file.tg_file_id or '未上传'}
"""
    
    await update.message.reply_text(file_info) 