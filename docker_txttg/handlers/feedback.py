from telegram import Update
from telegram.ext import ContextTypes
from services.user_service import ensure_user
from utils.db import SessionLocal, FileFeedback

async def feedback_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理反馈回调"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    ensure_user(user_id)
    
    # 获取反馈信息
    file_id = int(query.data.split('_')[1])
    rating = int(query.data.split('_')[2])
    
    # 记录反馈
    with SessionLocal() as session:
        feedback = FileFeedback(
            file_id=file_id,
            user_id=user_id,
            rating=rating
        )
        session.add(feedback)
        session.commit()
    
    await query.message.reply_text("感谢您的反馈！") 