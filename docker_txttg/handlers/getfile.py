from telegram import Update
from telegram.ext import ContextTypes
from utils.db import SessionLocal, File
from config import ADMIN_IDS

async def getfile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text('用法：/getfile <tg_file_id>')
        return
    tg_file_id = context.args[0]
    
    # 直接使用 tg_file_id 发送文件，不需要查询数据库
    try:
        if tg_file_id.startswith('BQAC') or tg_file_id.startswith('CAAC') or tg_file_id.startswith('HDAA'):
            await update.message.reply_document(tg_file_id, caption=f'file id: `{tg_file_id}`')
        elif tg_file_id.startswith('BAAC'):
            await update.message.reply_video(tg_file_id, caption=f'file id: `{tg_file_id}`')
        elif tg_file_id.startswith('AgAC'):
            await update.message.reply_photo(tg_file_id, caption=f'file id: `{tg_file_id}`')
        else:
            await update.message.reply_text('无效的文件ID格式。')
    except Exception as e:
        await update.message.reply_text(f'发送文件失败: {str(e)}')

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