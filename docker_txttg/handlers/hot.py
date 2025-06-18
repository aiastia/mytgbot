from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from utils.db import SessionLocal, File, SentFile
from datetime import datetime, timedelta
from services.user_service import ensure_user, get_sent_file_ids, get_user_vip_level
from services.file_service import mark_file_sent
from config import ADMIN_IDS

async def hot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理热门文件命令"""
    user_id = update.effective_user.id
    ensure_user(user_id)
    
    # 检查用户VIP等级
    vip_level = get_user_vip_level(user_id)
    if vip_level < 1 and user_id not in ADMIN_IDS:
        await update.message.reply_text("您需要VIP1才能使用此功能！")
        return
    
    # 检查用户今日发送数量
    count = get_sent_file_ids(user_id)
    if count >= 5:
        await update.message.reply_text("您今日已发送5个文件，请明天再来！")
        return
    
    # 获取热门文件
    session = SessionLocal()
    today = datetime.now().date()
    week_ago = today - timedelta(days=7)
    
    # 统计最近7天的文件发送次数
    hot_files = session.query(
        File,
        SentFile.file_id,
        SentFile.sent_at
    ).join(
        SentFile,
        File.file_id == SentFile.file_id
    ).filter(
        SentFile.sent_at >= week_ago
    ).all()
    
    if not hot_files:
        await update.message.reply_text("暂无热门文件！")
        return
    
    # 构建热门文件列表
    message = "🔥 热门文件（最近7天）：\n\n"
    keyboard = []
    
    for file, _, _ in hot_files[:10]:  # 只显示前10个
        message += f"📄 {file.file_name}\n"
        keyboard.append([InlineKeyboardButton(
            f"📄 {file.file_name}",
            callback_data=f"hotpage|{file.file_id}"
        )])
    
    await update.message.reply_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def hot_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理热门文件回调"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    ensure_user(user_id)
    
    # 检查用户VIP等级
    vip_level = get_user_vip_level(user_id)
    if vip_level < 1 and user_id not in ADMIN_IDS:
        await query.message.reply_text("您需要VIP1才能使用此功能！")
        return
    
    # 检查用户今日发送数量
    count = get_sent_file_ids(user_id)
    if count >= 5:
        await query.message.reply_text("您今日已发送5个文件，请明天再来！")
        return
    
    # 获取文件信息
    file_id = int(query.data.split('|')[1])
    
    file = SessionLocal().query(File).filter_by(file_id=file_id).first()
    if not file:
        await query.message.reply_text("文件不存在！")
        return
    
    if file.tg_file_id:
        await query.message.reply_document(
            document=file.tg_file_id,
            caption=f"file id: `{file.tg_file_id}`",
            parse_mode='Markdown'
        )
    else:
        with open(file.file_path, 'rb') as f:
            message = await query.message.reply_document(
                document=f,
                caption="正在生成文件ID..."
            )
            # 获取文件ID并更新数据库
            file_id = message.document.file_id
            mark_file_sent(user_id, file.file_id, 'file')
            # 更新消息
            await message.edit_caption(
                caption=f"file id: `{file_id}`",
                parse_mode='Markdown'
            ) 