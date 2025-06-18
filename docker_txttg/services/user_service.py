from utils.db import SessionLocal, User, SentFile
from telegram import Update
from telegram.ext import  ContextTypes
from datetime import datetime, timedelta
from utils.calculations import get_today_sent_count


def ensure_user(user_id):
    with SessionLocal() as session:
        user = session.query(User).filter_by(user_id=user_id).first()
        if not user:
            session.add(User(user_id=user_id))
            session.commit()

def get_user_vip_level(user_id):
    with SessionLocal() as session:
        user = session.query(User).filter_by(user_id=user_id).first()
        if not user or not user.vip_level:
            return 0, 10  # 返回等级和每日限制
        
        # 检查VIP是否过期
        if user.vip_expiry_date:
            expiry_date = datetime.strptime(user.vip_expiry_date, '%Y-%m-%d')
            if datetime.now().date() > expiry_date.date():
                # VIP已过期，重置等级
                user.vip_level = 0
                session.commit()
                return 0, 10  # 返回等级和每日限制
        
        # 根据等级返回每日限制
        if user.vip_level == 3:
            return user.vip_level, 100
        elif user.vip_level == 2:
            return user.vip_level, 50
        elif user.vip_level == 1:
            return user.vip_level, 30
        else:
            return user.vip_level, 10

def get_sent_file_ids(user_id):
    """获取用户已发送的文件数量"""
    with SessionLocal() as session:
        return session.query(SentFile).filter_by(user_id=user_id).count()

def set_user_vip_level(user_id, vip_level, days=30):
    with SessionLocal() as session:
        user = session.query(User).filter_by(user_id=user_id).first()
        if user:
            now = datetime.now()
            if vip_level > 0:
                # 如果是首次成为VIP，设置vip_date
                if not user.vip_date:
                    user.vip_date = now.strftime('%Y-%m-%d')
                user.vip_level = vip_level
                # 只有在没有过期时间或过期时间小于30天时才设置新的过期时间
                if not user.vip_expiry_date:
                    user.vip_expiry_date = (now + timedelta(days=days)).strftime('%Y-%m-%d')
                else:
                    expiry_date = datetime.strptime(user.vip_expiry_date, '%Y-%m-%d')
                    if (expiry_date - now).days < 30:
                        user.vip_expiry_date = (now + timedelta(days=days)).strftime('%Y-%m-%d')
            else:
                user.vip_level = 0
                user.vip_expiry_date = None
                # 不清除vip_date，保留首次成为VIP的记录
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
        total_files = get_sent_file_ids(user_id)
        
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
