from datetime import datetime
from config import VIP_DAYS, VIP_PACKAGES
from utils.db import SessionLocal, User ,SentFile


def get_user_points(user_id: int) -> int:
    """获取用户积分"""
    with SessionLocal() as session:
        user = session.query(User).filter_by(user_id=user_id).first()
        return user.points if user else 0

def add_points(user_id: int, points: int) -> int:
    """添加或扣除用户积分"""
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
            is_new_or_upgrade = (current_level != 0 and level > current_level)
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

def get_package_points(level: int, days: int) -> int:
    """获取指定等级和天数的套餐积分"""
    for pkg_level, pkg_days, points, _ in VIP_PACKAGES:
        if pkg_level == level and pkg_days == days:
            return points
    return 0  # 无效的套餐组合 

def get_today_sent_count(user_id):
    """获取用户今日已发送文件数量，使用 count 优化查询"""
    with SessionLocal() as session:
        today = datetime.now().strftime('%Y-%m-%d')
        count = session.query(SentFile).filter_by(
            user_id=user_id, 
            date=today
        ).count()
    return count
