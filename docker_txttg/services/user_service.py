from utils.db import SessionLocal, User, SentFile
from telegram import Update
from telegram.ext import  ContextTypes
from datetime import datetime, timedelta
from utils.calculations import get_today_sent_count


def ensure_user(user_id):
    """确保用户存在"""
    with SessionLocal() as session:
        user = session.query(User).filter_by(user_id=user_id).first()
        if not user:
            user = User(user_id=user_id)
            session.add(user)
            session.commit()

def get_user_vip_level(user_id):
    """获取用户VIP等级"""
    with SessionLocal() as session:
        user = session.query(User).filter_by(user_id=user_id).first()
        return user.vip_level if user else 0

def get_sent_file_ids(user_id):
    """获取用户已发送的文件数量"""
    with SessionLocal() as session:
        return session.query(SentFile).filter_by(user_id=user_id).count()

def set_user_vip_level(user_id, vip_level):
    """设置用户VIP等级"""
    with SessionLocal() as session:
        user = session.query(User).filter_by(user_id=user_id).first()
        if user:
            user.vip_level = vip_level
            session.commit() 


async def user_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    ensure_user(user_id)
    
    with SessionLocal() as session:
        user = session.query(User).filter_by(user_id=user_id).first()
        if not user:
            await update.message.reply_text('用户信息不存在。')
            return
            
        # 获取用户VIP信息
        vip_level, daily_limit = get_user_vip_level(user_id)
        vip_date = user.vip_date
        vip_expiry_date = user.vip_expiry_date
        
        # 检查VIP是否有效
        is_vip_active = False
        if vip_expiry_date:
            expiry_date = datetime.strptime(vip_expiry_date, '%Y-%m-%d')
            is_vip_active = datetime.now().date() <= expiry_date.date()
        
        # 获取今日已接收文件数
        today_count = get_today_sent_count(user_id)
        
        # 获取总接收文件数
        total_files = len(get_sent_file_ids(user_id))
        
        # 构建消息
        msg = f'📊 <b>用户统计信息</b>\n\n'
        msg += f'👤 用户ID: <code>{user_id}</code>\n'
        msg += f'⭐ VIP等级: {vip_level}\n'
        msg += f'📊 VIP状态: {"有效" if is_vip_active else "已过期"}\n'
        if vip_date:
            msg += f'📅 VIP开始日期: {vip_date}\n'
        if vip_expiry_date:
            msg += f'⏰ VIP过期日期: {vip_expiry_date}\n'
        msg += f'📚 今日已接收: {today_count}/{daily_limit}\n'
        msg += f'📦 总接收文件: {total_files}\n'
        msg += f'🎯 当前积分: {user.points}\n'
        
        await update.message.reply_text(msg, parse_mode='HTML') 