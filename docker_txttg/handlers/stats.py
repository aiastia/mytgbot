from telegram import Update
from telegram.ext import ContextTypes
from utils.db import SessionLocal, File, SentFile, User
from config import ADMIN_IDS
from services.user_service import ensure_user, get_sent_file_ids
# async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     """处理统计命令"""
#     user_id = update.effective_user.id
    
#     # 检查是否是管理员
#     if user_id not in ADMIN_IDS:
#         await update.message.reply_text("此命令仅限管理员使用！")
#         return
    
#     session = SessionLocal()
    
#     # 获取统计数据
#     total_files = session.query(File).count()
#     total_users = session.query(User).count()
#     total_sent = session.query(SentFile).count()
    
#     # 获取今日数据
#     from datetime import datetime, timedelta
#     today = datetime.now().date()
#     today_sent = session.query(SentFile).filter(
#         SentFile.sent_at >= today
#     ).count()
    
#     # 构建统计信息
#     stats_text = f"""
# 📊 系统统计信息：

# 📁 文件统计：
# - 总文件数：{total_files}
# - 今日发送：{today_sent}
# - 总发送次数：{total_sent}

# 👥 用户统计：
# - 总用户数：{total_users}
# """
    
#     await update.message.reply_text(stats_text) 

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    ensure_user(user_id)
    count = get_sent_file_ids(user_id)
    await update.message.reply_text(f'你已收到 {count} 个文件。')
