import os
import random
from datetime import datetime
from utils.db import SessionLocal, File, SentFile, UploadedDocument

def mark_file_sent(user_id, file_id, source='file'):
    """记录文件发送历史，使用 merge 避免重复记录"""
    with SessionLocal() as session:
        date = datetime.now().strftime('%Y-%m-%d')
        session.merge(SentFile(user_id=user_id, file_id=file_id, date=date, source=source))
        session.commit()

def get_unsent_files(user_id):
    """获取未发送的文件
    返回格式: {'id': file_id, 'source': 'file'/'uploaded', 'tg_file_id': '...'} 或 {'id': file_id, 'source': 'file'/'uploaded', 'file_path': '...'}
    """
    with SessionLocal() as session:
        # 获取所有文件ID
        file_ids = {row.file_id for row in session.query(File.file_id).all()}
        uploaded_ids = {doc.id for doc in session.query(UploadedDocument).filter_by(status='approved').all()}
        
        # 获取已发送的文件ID，直接按source分类查询
        sent_file_ids = {record.file_id for record in session.query(SentFile).filter_by(user_id=user_id, source='file').all()}
        sent_uploaded_ids = {record.file_id for record in session.query(SentFile).filter_by(user_id=user_id, source='uploaded').all()}
        
        # 获取未发送的文件ID
        unsent_file_ids = list(file_ids - sent_file_ids)
        unsent_uploaded_ids = list(uploaded_ids - sent_uploaded_ids)
        
        # 如果两个列表都为空，返回None
        if not unsent_file_ids and not unsent_uploaded_ids:
            return None
            
        # 随机选择一个未发送的文件ID
        if unsent_file_ids and unsent_uploaded_ids:
            # 如果两个列表都有内容，随机选择一个列表
            if random.random() < 0.7:  # 70%概率选择普通文件
                file_id = random.choice(unsent_file_ids)
                source = 'file'
            else:
                file_id = random.choice(unsent_uploaded_ids)
                source = 'uploaded'
        elif unsent_file_ids:
            file_id = random.choice(unsent_file_ids)
            source = 'file'
        else:
            file_id = random.choice(unsent_uploaded_ids)
            source = 'uploaded'
        
        # 根据source和file_id获取文件信息
        if source == 'file':
            file = session.query(File).filter_by(file_id=file_id).first()
            if file:
                if file.tg_file_id:
                    return {'id': file_id, 'source': source, 'tg_file_id': file.tg_file_id}
                elif file.file_path and os.path.exists(file.file_path):
                    return {'id': file_id, 'source': source, 'file_path': file.file_path}
        else:
            doc = session.query(UploadedDocument).filter_by(id=file_id).first()
            if doc:
                if doc.tg_file_id:
                    return {'id': file_id, 'source': source, 'tg_file_id': doc.tg_file_id}
                elif doc.download_path and os.path.exists(doc.download_path):
                    return {'id': file_id, 'source': source, 'file_path': doc.download_path}
        
        return None 