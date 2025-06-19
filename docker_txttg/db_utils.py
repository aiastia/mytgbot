import os
from datetime import datetime, timedelta
from orm_utils import SessionLocal
from orm_models import User, File, SentFile, FileFeedback, UploadedDocument

# 用户、文件、VIP、反馈等数据库操作

def get_or_create_file(file_path, tg_file_id=None):
    with SessionLocal() as session:
        # 首先检查是否是上传的文档
        uploaded_doc = session.query(UploadedDocument).filter_by(download_path=file_path).first()
        if uploaded_doc:
            file = session.query(File).filter_by(file_path=file_path).first()
            if file:
                if tg_file_id and tg_file_id != file.tg_file_id:
                    file.tg_file_id = tg_file_id
                    session.commit()
                return file.file_id
            file_size = os.path.getsize(file_path)
            new_file = File(
                file_path=file_path,
                tg_file_id=uploaded_doc.tg_file_id or tg_file_id,
                file_size=file_size
            )
            session.add(new_file)
            session.commit()
            return new_file.file_id
        file = session.query(File).filter_by(file_path=file_path).first()
        if file:
            if tg_file_id and tg_file_id != file.tg_file_id:
                file.tg_file_id = tg_file_id
                session.commit()
            return file.file_id
        file_size = None
        try:
            file_size = os.path.getsize(file_path)
        except Exception:
            pass
        new_file = File(file_path=file_path, tg_file_id=tg_file_id, file_size=file_size)
        session.add(new_file)
        session.commit()
        return new_file.file_id

def ensure_user(user_id):
    with SessionLocal() as session:
        user = session.query(User).filter_by(user_id=user_id).first()
        if not user:
            session.add(User(user_id=user_id))
            session.commit()

def set_user_vip_level(user_id, vip_level, days=30):
    with SessionLocal() as session:
        user = session.query(User).filter_by(user_id=user_id).first()
        if user:
            now = datetime.now()
            if vip_level > 0:
                if not user.vip_date:
                    user.vip_date = now.strftime('%Y-%m-%d')
                user.vip_level = vip_level
                if not user.vip_expiry_date:
                    user.vip_expiry_date = (now + timedelta(days=days)).strftime('%Y-%m-%d')
                else:
                    expiry_date = datetime.strptime(user.vip_expiry_date, '%Y-%m-%d')
                    if (expiry_date - now).days < 30:
                        user.vip_expiry_date = (now + timedelta(days=days)).strftime('%Y-%m-%d')
            else:
                user.vip_level = 0
                user.vip_expiry_date = None
            session.commit()

def get_user_vip_level(user_id):
    with SessionLocal() as session:
        user = session.query(User).filter_by(user_id=user_id).first()
        if not user or not user.vip_level:
            return 0, 10
        if user.vip_expiry_date:
            expiry_date = datetime.strptime(user.vip_expiry_date, '%Y-%m-%d')
            if datetime.now().date() > expiry_date.date():
                user.vip_level = 0
                session.commit()
                return 0, 10
        if user.vip_level == 3:
            return user.vip_level, 100
        elif user.vip_level == 2:
            return user.vip_level, 50
        elif user.vip_level == 1:
            return user.vip_level, 30
        else:
            return user.vip_level, 10

def get_sent_file_ids(user_id):
    with SessionLocal() as session:
        return session.query(SentFile).filter_by(user_id=user_id).count()

def mark_file_sent(user_id, file_id, source='file'):
    with SessionLocal() as session:
        date = datetime.now().strftime('%Y-%m-%d')
        session.merge(SentFile(user_id=user_id, file_id=file_id, date=date, source=source))
        session.commit()

def get_today_sent_count(user_id):
    with SessionLocal() as session:
        today = datetime.now().strftime('%Y-%m-%d')
        count = session.query(SentFile).filter_by(
            user_id=user_id, 
            date=today
        ).count()
    return count

def record_feedback(user_id, file_id, feedback):
    with SessionLocal() as session:
        date = datetime.now().strftime('%Y-%m-%d')
        session.merge(FileFeedback(user_id=user_id, file_id=file_id, feedback=feedback, date=date))
        session.commit()
