from db_utils import *
from file_utils import *
from orm_utils import SessionLocal
from orm_models import File, FileFeedback, UploadedDocument, User
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from datetime import datetime, timedelta
import os
import random
from config import TXT_ROOT, TXT_EXTS, ADMIN_USER_ID
from bot_tasks import send_file_job

async def send_random_txt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    ensure_user(user_id)
    vip_level, daily_limit = get_user_vip_level(user_id)
    if get_today_sent_count(user_id) >= daily_limit:
        await update.message.reply_text(f'每天最多只能领取{daily_limit}本，明天再来吧！')
        return
    file_info = get_unsent_files(user_id)
    if not file_info:
        await update.message.reply_text('你已经收到了所有文件！')
        return
    prep_message = await update.message.reply_text('正在准备发送文件...')
    context.job_queue.run_once(
        send_file_job,
        when=1,
        data={
            'chat_id': update.effective_chat.id,
            'file_id_or_path': file_info.get('tg_file_id') or file_info.get('file_path'),
            'user_id': user_id,
            'prep_message_id': prep_message.message_id,
            'source': file_info['source']
        }
    )

async def getfile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text('用法：/getfile <tg_file_id>')
        return
    tg_file_id = context.args[0]
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

async def reload_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN_USER_ID:
        await update.message.reply_text('无权限，仅管理员可用。')
        return
    inserted, skipped = reload_txt_files()
    await update.message.reply_text(f'刷新完成，新增 {inserted} 个文件，跳过 {skipped} 个已存在。')

HOT_PAGE_SIZE = 10

async def hot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_hot_page(update, context, page=0, edit=False)

async def hot_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data.split('|')
    if len(data) == 2 and data[0] == 'hotpage':
        page = int(data[1])
        await send_hot_page(update, context, page=page, edit=True)

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

async def feedback_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data.split('|')
    if len(data) == 3 and data[0] == 'feedback':
        file_id = int(data[1])
        feedback = int(data[2])
        record_feedback(user_id, file_id, feedback)
        with SessionLocal() as session:
            file = session.query(File).filter_by(file_id=file_id).first()
            tg_file_id = file.tg_file_id if file else ''
        if feedback == 1:
            keyboard = [
                [
                    InlineKeyboardButton("👍 已选", callback_data=f"feedback|{file_id}|1"),
                    InlineKeyboardButton("👎", callback_data=f"feedback|{file_id}|-1"),
                ]
            ]
        else:
            keyboard = [
                [
                    InlineKeyboardButton("👍", callback_data=f"feedback|{file_id}|1"),
                    InlineKeyboardButton("👎 已选", callback_data=f"feedback|{file_id}|-1"),
                ]
            ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        try:
            await query.edit_message_caption(
                caption=f"file id: `{tg_file_id}`",
                reply_markup=reply_markup
            )
        except Exception as e:
            if 'Message is not modified' in str(e):
                pass
            else:
                raise
