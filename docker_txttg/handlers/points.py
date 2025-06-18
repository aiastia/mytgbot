import random
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from utils.db import SessionLocal, User
from config import ADMIN_IDS, VIP_PACKAGES, VIP_DAYS
from utils.calculations import (
    calculate_points_for_days,
    get_package_points,
    get_user_points,
    add_points
)
from .vip import get_vip_info, exchange_callback, cancel_callback

def can_checkin(user_id: int) -> bool:
    with SessionLocal() as session:
        user = session.query(User).filter_by(user_id=user_id).first()
        if not user or not user.last_checkin:
            return True
        last_checkin = datetime.strptime(user.last_checkin, '%Y-%m-%d')
        return datetime.now().date() > last_checkin.date()

def update_last_checkin(user_id: int):
    with SessionLocal() as session:
        user = session.query(User).filter_by(user_id=user_id).first()
        if user:
            user.last_checkin = datetime.now().strftime('%Y-%m-%d')
            session.commit()

async def checkin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not can_checkin(user_id):
        await update.message.reply_text("今天已经签到过了，明天再来吧！")
        return
    
    points = random.randint(1, 5)
    new_points = add_points(user_id, points)
    update_last_checkin(user_id)
    
    await update.message.reply_text(
        f"签到成功！获得 {points} 积分\n当前积分：{new_points}"
    )

async def points_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    points = get_user_points(user_id)
    
    # 获取用户当前VIP状态
    vip_info = get_vip_info(user_id)
    
    # 构建消息
    msg = f"💰 当前积分：{points}\n\n"
    if vip_info['level'] > 0 and vip_info['is_active']:
        msg += f"⭐ 当前VIP等级：{vip_info['level']}\n"
        if vip_info['expiry_date']:
            expiry_date = datetime.strptime(vip_info['expiry_date'], '%Y-%m-%d')
            remaining_days = (expiry_date - datetime.now()).days
            msg += f"⏰ 剩余天数：{remaining_days}天\n\n"
    
    msg += "📦 可兑换套餐：\n"
    
    # 生成按钮
    keyboard = []
    current_row = []
    
    # 根据套餐配置生成按钮
    for level, days, points, desc in VIP_PACKAGES:
        # 检查是否应该显示这个套餐
        should_show = (
            vip_info['level'] == 0 or  # 非VIP用户
            not vip_info['is_active'] or  # VIP已过期
            level == vip_info['level'] or  # 同等级续费
            level > vip_info['level']      # 升级到更高级别
        )
        
        if should_show:
            button_text = f"{desc} ({points}积分)"
            callback_data = f"exchange|vip|{level}|{days}"
            current_row.append(InlineKeyboardButton(button_text, callback_data=callback_data))
            
            # 每行最多2个按钮
            if len(current_row) == 2:
                keyboard.append(current_row)
                current_row = []
    
    # 添加剩余按钮
    if current_row:
        keyboard.append(current_row)
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(msg, reply_markup=reply_markup)

# 使用vip.py中的回调处理函数
async def exchange_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from .vip import exchange_callback as vip_exchange
    return await vip_exchange(update, context)

async def cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from .vip import cancel_callback as vip_cancel
    return await vip_cancel(update, context)

def upgrade_vip_level(user_id: int, target_level: int, target_days: int) -> tuple[bool, str]:
    """升级或续费VIP等级"""
    with SessionLocal() as session:
        user = session.query(User).filter_by(user_id=user_id).first()
        if not user:
            return False, "用户不存在"
        
        # 验证目标等级
        if target_level not in [1, 2, 3]:
            return False, "无效的VIP等级"
        
        # 验证目标天数
        if target_days not in VIP_PACKAGES:
            return False, "无效的套餐天数"
        
        # 不能降级
        if user.vip_level and target_level < user.vip_level:
            return False, "不能降级VIP等级"
        
        # 计算目标套餐所需积分
        target_points = calculate_points_for_days(target_level, target_days, user.vip_level if user.vip_level else 0)
        if target_points == 0:
            return False, "无效的套餐组合"
        
        # 计算需要扣除的积分
        points_to_deduct = target_points
        current_points = 0
        current_expiry = None
        remaining_days = 0
        
        # 如果当前是VIP且未过期，计算抵扣
        if user.vip_level and user.vip_expiry_date:
            current_expiry = datetime.strptime(user.vip_expiry_date, '%Y-%m-%d')
            if datetime.now().date() <= current_expiry.date():
                # 计算剩余天数
                remaining_days = (current_expiry - datetime.now()).days
                # 计算当前等级剩余时间的等效积分
                current_points = calculate_points_for_days(user.vip_level, remaining_days, user.vip_level)
                # 如果是升级，检查天数是否合法
                if target_level > user.vip_level:
                    # 不允许降级天数
                    if target_days < remaining_days:
                        return False, f"升级后的套餐天数不能少于当前剩余天数({remaining_days}天)"
                    # 计算差价：完整套餐积分 - 当前等级剩余价值
                    points_to_deduct = target_points - current_points
        
        # 检查用户积分是否足够
        if user.points < points_to_deduct:
            return False, f"积分不足，需要{points_to_deduct}积分"
        
        now = datetime.now()
        # 计算新过期时间
        if target_level == user.vip_level:
            # 续费：
            if not user.vip_level or not user.vip_expiry_date:
                # VIP0 或无过期时间，从当前时间算起
                base_time = now
            else:
                current_expiry = datetime.strptime(user.vip_expiry_date, '%Y-%m-%d')
                base_time = current_expiry if current_expiry > now else now
            new_expiry = base_time + timedelta(days=target_days)
        else:
            # 升级：从当前时间开始计算新套餐时间
            new_expiry = now + timedelta(days=target_days)
        
        # 扣除积分并更新VIP状态
        user.points -= points_to_deduct
        user.vip_level = target_level
        user.vip_expiry_date = new_expiry.strftime('%Y-%m-%d')
        session.commit()
        
        # 构建返回消息
        if target_level == user.vip_level:
            message = f"续费成功！已续费VIP{target_level} {target_days}天，有效期至{new_expiry.strftime('%Y-%m-%d')}，本次消耗{points_to_deduct}积分"
        else:
            if current_points > 0:
                message = f"升级成功！已升级为VIP{target_level}，有效期至{new_expiry.strftime('%Y-%m-%d')}，原VIP剩余价值{current_points}积分，本次消耗{points_to_deduct}积分"
            else:
                message = f"升级成功！已升级为VIP{target_level}，有效期至{new_expiry.strftime('%Y-%m-%d')}，本次消耗{points_to_deduct}积分"
        
        return True, message

def is_vip_active(user_id: int) -> bool:
    with SessionLocal() as session:
        user = session.query(User).filter_by(user_id=user_id).first()
        if not user or not user.vip_expiry_date:
            return False
        expiry_date = datetime.strptime(user.vip_expiry_date, '%Y-%m-%d')
        return datetime.now().date() <= expiry_date.date()

def get_package_points(level: int, days: int) -> int:
    """获取指定等级和天数的套餐积分"""
    for pkg_level, pkg_days, points, _ in VIP_PACKAGES:
        if pkg_level == level and pkg_days == days:
            return points
    return 0  # 无效的套餐组合 