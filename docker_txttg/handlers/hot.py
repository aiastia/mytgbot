import  os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes 
from utils.db import SessionLocal, File, SentFile,FileFeedback
from datetime import datetime, timedelta
from services.user_service import ensure_user, get_sent_file_ids, get_user_vip_level
from services.file_service import mark_file_sent
from config import ADMIN_IDS
HOT_PAGE_SIZE = 10

async def hot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_hot_page(update, context, page=0, edit=False)

async def send_hot_page(update, context, page=0, edit=False):
    with SessionLocal() as session:
        from sqlalchemy import func
        seven_days_ago = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
        likes_subq = session.query(
            FileFeedback.file_id,
            func.count().label('likes')
        ).filter(
            FileFeedback.feedback == 1,
            FileFeedback.date >= seven_days_ago
        ).group_by(FileFeedback.file_id).subquery()
        rows = (
            session.query(
                File.file_path,
                File.tg_file_id,
                func.coalesce(likes_subq.c.likes, 0)
            )
            .outerjoin(likes_subq, File.file_id == likes_subq.c.file_id)
            .filter(likes_subq.c.likes != None)
            .order_by(likes_subq.c.likes.desc(), File.file_path)
            .all()
        )
    total = len(rows)
    if total == 0:
        msg = '最近7天还没有文件收到，快去评分吧！'
        if edit and update.callback_query:
            await update.callback_query.edit_message_text(msg)
        else:
            await update.message.reply_text(msg)
        return
    start = page * HOT_PAGE_SIZE
    end = start + HOT_PAGE_SIZE
    page_rows = rows[start:end]
    msg = '🔥 <b>热榜（近7天👍最多的文件）</b> 🔥\n\n'
    for idx, (file_path, tg_file_id, likes) in enumerate(page_rows, start+1):
        filename = os.path.basename(file_path)
        msg += f'<b>{idx}. {filename}</b>\n📄 <code>{tg_file_id}</code>\n👍 <b>{likes}</b>\n\n'
    # 分页按钮
    buttons = []
    if page > 0:
        buttons.append(InlineKeyboardButton('上一页', callback_data=f'hotpage|{page-1}'))
    if end < total:
        buttons.append(InlineKeyboardButton('下一页', callback_data=f'hotpage|{page+1}'))
    reply_markup = InlineKeyboardMarkup([buttons]) if buttons else None
    if edit and update.callback_query:
        await update.callback_query.edit_message_text(msg, parse_mode='HTML', reply_markup=reply_markup)
    else:
        await update.message.reply_text(msg, parse_mode='HTML', reply_markup=reply_markup)


async def hot_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data.split('|')
    if len(data) == 2 and data[0] == 'hotpage':
        page = int(data[1])
        await send_hot_page(update, context, page=page, edit=True)