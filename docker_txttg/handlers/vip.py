from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from utils.db import SessionLocal, User
from config import VIP_PACKAGES, VIP_DAYS
from utils.calculations import (
    calculate_points_for_days,
    get_package_points,
    get_user_points,
    add_points
)

def is_vip_active(user_id: int) -> bool:
    with SessionLocal() as session:
        user = session.query(User).filter_by(user_id=user_id).first()
        if not user or not user.vip_expiry_date:
            return False
        expiry_date = datetime.strptime(user.vip_expiry_date, '%Y-%m-%d')
        return datetime.now().date() <= expiry_date.date()

def get_vip_info(user_id: int) -> dict:
    with SessionLocal() as session:
        user = session.query(User).filter_by(user_id=user_id).first()
        if not user:
            return {
                'level': 0,
                'is_active': False,
                'expiry_date': None
            }
        
        is_active = user.vip_expiry_date and datetime.now() < datetime.strptime(user.vip_expiry_date, '%Y-%m-%d')
        return {
            'level': user.vip_level if is_active else 0,
            'is_active': is_active,
            'expiry_date': user.vip_expiry_date
        }

def get_package_points(level: int, days: int) -> int:
    """获取指定等级和天数的套餐积分"""
    for pkg_level, pkg_days, points, _ in VIP_PACKAGES:
        if pkg_level == level and pkg_days == days:
            return points
    return 0  # 无效的套餐组合

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
        if target_days not in VIP_DAYS:
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

async def vip_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理VIP命令"""
    user_id = update.effective_user.id
    vip_info = get_vip_info(user_id)
    
    # 构建消息
    msg = "⭐ VIP信息：\n"
    if vip_info['level'] > 0 and vip_info['is_active']:
        expiry_date = datetime.strptime(vip_info['expiry_date'], '%Y-%m-%d')
        remaining_days = (expiry_date - datetime.now()).days
        msg += f"当前等级：VIP{vip_info['level']}\n"
        msg += f"剩余天数：{remaining_days}天\n"
        msg += f"到期时间：{vip_info['expiry_date']}\n"
    else:
        msg += "您当前不是VIP用户\n"
    
    msg += "\n📦 可购买套餐：\n"
    
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

async def exchange_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理VIP兑换回调"""
    query = update.callback_query
    await query.answer()
    
    # 解析回调数据
    _, _, level, days = query.data.split('|')
    level = int(level)
    days = int(days)
    
    user_id = query.from_user.id
    current_points = get_user_points(user_id)
    required_points = get_package_points(level, days)
    
    if current_points < required_points:
        await query.edit_message_text(
            f"积分不足！\n需要：{required_points}积分\n当前：{current_points}积分"
        )
        return
    
    # 获取当前VIP信息
    vip_info = get_vip_info(user_id)
    current_level = vip_info['level']
    
    # 计算实际需要的积分
    actual_points = calculate_points_for_days(level, days, current_level)
    
    # 扣除积分
    new_points = add_points(user_id, -actual_points)
    
    # 升级VIP
    success, expiry_date = upgrade_vip_level(user_id, level, days)
    
    if success:
        await query.edit_message_text(
            f"兑换成功！\n"
            f"VIP等级：{level}\n"
            f"到期时间：{expiry_date}\n"
            f"剩余积分：{new_points}"
        )
    else:
        # 如果升级失败，退还积分
        add_points(user_id, actual_points)
        await query.edit_message_text(f"兑换失败：{expiry_date}")

async def cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理取消兑换回调"""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("已取消兑换")

async def setvip_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """设置用户VIP等级（仅管理员）"""
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("您没有权限执行此操作！")
        return
    
    # 解析命令参数
    try:
        _, user_id, level, days = update.message.text.split()
        user_id = int(user_id)
        level = int(level)
        days = int(days)
    except ValueError:
        await update.message.reply_text("格式错误！请使用：/setvip 用户ID 等级 天数")
        return
    
    # 验证参数
    if level not in [1, 2, 3]:
        await update.message.reply_text("无效的VIP等级！")
        return
    
    if days not in VIP_DAYS:
        await update.message.reply_text("无效的套餐天数！")
        return
    
    # 设置VIP
    success, message = upgrade_vip_level(user_id, level, days)
    await update.message.reply_text(message)

async def setviplevel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理设置VIP等级命令（别名）"""
    await setvip_command(update, context) 