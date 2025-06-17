import random
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from orm_utils import SessionLocal
from orm_models import User

# VIP套餐配置
VIP_DAYS = [3, 7, 15, 30, 90, 180, 365]  # 所有有效的VIP套餐天数

# VIP套餐配置
VIP_PACKAGES = [
    # 格式: (等级, 天数, 积分, 描述)
    # 短期套餐
    (1, 3, 15, "3天VIP1"),
    (1, 7, 25, "7天VIP1"),
    
    # 月度套餐
    (1, 30, 120, "30天VIP1"),
    (2, 30, 240, "30天VIP2"),
    (3, 30, 400, "30天VIP3"),
    
    # 季度套餐
    (1, 90, 300, "90天VIP1"),
    (2, 90, 600, "90天VIP2"),
    (3, 90, 1000, "90天VIP3"),
    
    # 半年套餐
    (1, 180, 500, "180天VIP1"),
    (2, 180, 1000, "180天VIP2"),
    (3, 180, 1800, "180天VIP3"),
    
    # 年度套餐
    (1, 365, 1000, "365天VIP1"),
    (2, 365, 2000, "365天VIP2"),
    (3, 365, 3500, "365天VIP3"),
]

def get_user_points(user_id: int) -> int:
    with SessionLocal() as session:
        user = session.query(User).filter_by(user_id=user_id).first()
        return user.points if user else 0

def add_points(user_id: int, points: int) -> int:
    with SessionLocal() as session:
        user = session.query(User).filter_by(user_id=user_id).first()
        if not user:
            user = User(user_id=user_id, points=points)
            session.add(user)
        else:
            if user.points is None:
                user.points = points
            else:
                user.points += points
        session.commit()
        return user.points

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


def calculate_points_for_days(level: int, days: int, current_level: int = 0) -> int:
    """根据套餐配置计算指定等级和天数的积分价值"""
    # 找到大于或等于days的最小天数作为匹配天数
    closest_days = None
    for d in sorted(VIP_DAYS):  # 按顺序遍历天数列表
        if d >= days:
            closest_days = d
            break
    if closest_days is None:  # 如果没有比days大的天数，选择最大的天数
        closest_days = max(VIP_DAYS)
    
    # 找到对应套餐的积分
    for pkg_level, pkg_days, points, _ in VIP_PACKAGES:
        if pkg_level == level and pkg_days == closest_days:
            # 判断是否为新购（current_level = 0）或升级（level > current_level）
            is_new_or_upgrade = (level > current_level)
            # 按比例计算积分
            if closest_days <= 7:  # 短期套餐（3天和7天）
                if is_new_or_upgrade:  # 新购或升级时按9折计算
                    return int(points * 0.9)
                else:  # 续期或降级时按原价计算
                    return points
            else:  # 长期套餐（30天及以上）
                if is_new_or_upgrade:  # 新购或升级时可以添加额外的优惠逻辑（如有）
                    return int(points * (days / closest_days))
                else:  # 续期或降级时按比例计算
                    return int(points * (days / closest_days))
    return 0  # 无效的组合返回0

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
    with SessionLocal() as session:
        user = session.query(User).filter_by(user_id=user_id).first()
        if not user:
            await update.message.reply_text("用户信息不存在")
            return
        
        current_level = user.vip_level if user.vip_level else 0
        vip_expiry = user.vip_expiry_date
        
        # 检查VIP是否过期
        is_vip_expired = True
        remaining_days = 0
        if vip_expiry:
            expiry_date = datetime.strptime(vip_expiry, '%Y-%m-%d')
            is_vip_expired = datetime.now().date() > expiry_date.date()
            if not is_vip_expired:
                remaining_days = (expiry_date - datetime.now()).days
        
        # 构建消息
        msg = f"💰 当前积分：{points}\n\n"
        if current_level > 0 and not is_vip_expired:
            msg += f"⭐ 当前VIP等级：{current_level}\n"
            msg += f"⏰ 剩余天数：{remaining_days}天\n\n"
        
        msg += "📦 可兑换套餐：\n"
        
        # 生成按钮
        keyboard = []
        current_row = []
        
        # 根据套餐配置生成按钮
        for level, days, points, desc in VIP_PACKAGES:
            # 检查是否应该显示这个套餐
            should_show = (
                current_level == 0 or  # 非VIP用户
                is_vip_expired or      # VIP已过期
                level == current_level or  # 同等级续费
                level > current_level      # 升级到更高级别
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
    query = update.callback_query
    await query.answer()
    
    # 解析回调数据
    data = query.data.split('|')
    if len(data) < 4:  # 修改为小于4，因为确认操作会有5个部分
        await query.message.edit_text("无效的兑换选项")
        return
    
    action_type = data[1]
    if action_type == 'vip':
        try:
            level = int(data[2])
            days = int(data[3])
            
            # 检查是否是确认操作
            if len(data) == 5 and data[4] == 'confirm':
                # 执行升级
                success, message = upgrade_vip_level(query.from_user.id, level, days)
                if success:
                    # 禁用确认按钮，防止重复点击
                    keyboard = [
                        [
                            InlineKeyboardButton("↩️ 返回", callback_data="cancel")
                        ]
                    ]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    await query.message.edit_text(message, reply_markup=reply_markup)
                else:
                    await query.message.edit_text(message)
                return
            
            # 获取用户当前积分和VIP状态
            points = get_user_points(query.from_user.id)
            with SessionLocal() as session:
                user = session.query(User).filter_by(user_id=query.from_user.id).first()
                if not user:
                    await query.message.edit_text("用户信息不存在")
                    return
                
                current_level = user.vip_level if user.vip_level else 0
                current_points = 0
                
                # 如果用户是VIP且未过期，计算当前VIP的积分价值
                if current_level > 0 and user.vip_expiry_date:
                    expiry_date = datetime.strptime(user.vip_expiry_date, '%Y-%m-%d')
                    if datetime.now().date() <= expiry_date.date():
                        remaining_days = (expiry_date - datetime.now()).days
                        current_points = calculate_points_for_days(current_level, remaining_days, current_level)
                
                # 计算目标套餐所需积分
                target_points = calculate_points_for_days(level, days, current_level)
                
                # 计算实际需要扣除的积分
                if level == current_level:
                    # 同等级套餐直接扣除新套餐积分
                    actual_points = target_points
                    operation_type = "续费"
                else:
                    # 不同等级计算差价
                    actual_points = max(0, target_points - current_points)
                    operation_type = "升级"
            
            # 构建确认消息
            confirm_msg = f"⚠️ 确认{operation_type}VIP{level} {days}天？\n\n"
            
            if current_level > 0:
                confirm_msg += f"当前VIP等级：{current_level}\n"
                if current_points > 0:
                    confirm_msg += f"当前VIP剩余积分价值：{current_points}\n"
            
            if level != current_level:
                confirm_msg += f"目标套餐积分：{target_points}\n"
                if current_points > 0:
                    confirm_msg += f"实际需要扣除：{actual_points}（已抵扣{current_points}积分）\n"
            else:
                confirm_msg += f"需要扣除：{actual_points}\n"
                
            confirm_msg += f"当前积分余额：{points}\n\n"
            confirm_msg += "请确认是否继续？"
            
            # 创建确认按钮
            keyboard = [
                [
                    InlineKeyboardButton("✅ 确认", callback_data=f"exchange|vip|{level}|{days}|confirm"),
                    InlineKeyboardButton("❌ 取消", callback_data="cancel")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.message.edit_text(confirm_msg, reply_markup=reply_markup)
        except ValueError:
            await query.message.edit_text("无效的VIP等级或天数")
    else:
        await query.message.edit_text("无效的兑换选项")

async def cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理取消操作的回调"""
    query = update.callback_query
    await query.answer()
    
    # 获取用户当前积分和VIP状态
    user_id = query.from_user.id
    points = get_user_points(user_id)
    
    with SessionLocal() as session:
        user = session.query(User).filter_by(user_id=user_id).first()
        if not user:
            await query.message.edit_text("用户信息不存在")
            return
        
        current_level = user.vip_level if user.vip_level else 0
        vip_expiry = user.vip_expiry_date
        
        # 检查VIP是否过期
        is_vip_expired = True
        remaining_days = 0
        if vip_expiry:
            expiry_date = datetime.strptime(vip_expiry, '%Y-%m-%d')
            is_vip_expired = datetime.now().date() > expiry_date.date()
            if not is_vip_expired:
                remaining_days = (expiry_date - datetime.now()).days
        
        # 构建消息
        msg = f"💰 当前积分：{points}\n\n"
        if current_level > 0 and not is_vip_expired:
            msg += f"⭐ 当前VIP等级：{current_level}\n"
            msg += f"⏰ 剩余天数：{remaining_days}天\n\n"
        
        msg += "📦 可兑换套餐：\n"
        
        # 生成按钮
        keyboard = []
        current_row = []
        
        # 根据套餐配置生成按钮
        for level, days, points, desc in VIP_PACKAGES:
            # 检查是否应该显示这个套餐
            should_show = (
                current_level == 0 or  # 非VIP用户
                is_vip_expired or      # VIP已过期
                level == current_level or  # 同等级续费
                level > current_level      # 升级到更高级别
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
        await query.message.edit_text(msg, reply_markup=reply_markup)

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
                'start_date': None,
                'expiry_date': None
            }
        
        is_active = False
        if user.vip_expiry_date:
            expiry_date = datetime.strptime(user.vip_expiry_date, '%Y-%m-%d')
            is_active = datetime.now().date() <= expiry_date.date()
        
        return {
            'level': user.vip_level,
            'is_active': is_active,
            'start_date': user.vip_date,
            'expiry_date': user.vip_expiry_date
        }

def get_package_points(level: int, days: int) -> int:
    """获取指定等级和天数的套餐积分"""
    for pkg_level, pkg_days, points, _ in VIP_PACKAGES:
        if pkg_level == level and pkg_days == days:
            return points
    return 0  # 无效的套餐组合 
