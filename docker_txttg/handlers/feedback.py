from datetime import datetime, timedelta
from telegram import Update , InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from services.user_service import ensure_user
from utils.db import SessionLocal, File , FileFeedback
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

def record_feedback(user_id, file_id, feedback):
    with SessionLocal() as session:
        date = datetime.now().strftime('%Y-%m-%d')
        session.merge(FileFeedback(user_id=user_id, file_id=file_id, feedback=feedback, date=date))
        session.commit()