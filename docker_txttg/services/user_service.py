from utils.db import SessionLocal, User, SentFile

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