from modules.db.orm_utils import SessionLocal
from modules.db.orm_models import UploadedDocument, File
from datetime import datetime

# 文档查重和保存业务逻辑

def check_duplicate_and_save(session, document, user_id):
    # 检查文件名和大小
    existing = session.query(UploadedDocument).filter_by(
        file_name=document.file_name,
        file_size=document.file_size
    ).first()
    if existing:
        return "duplicate"
    # 检查 tg_file_id
    existing_by_tg_id = session.query(UploadedDocument).filter_by(
        tg_file_id=document.file_id
    ).first()
    if existing_by_tg_id:
        return "duplicate"
    # 检查 files 表中是否存在相同文件
    existing_file = session.query(File).filter(
        (File.file_size == document.file_size) |
        (File.file_path.like(f"%{document.file_name}"))
    ).first()
    if existing_file:
        return "exists_in_system"
    # 创建新记录
    new_doc = UploadedDocument(
        user_id=user_id,
        file_name=document.file_name,
        file_size=document.file_size,
        tg_file_id=document.file_id,
        upload_time=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    )
    session.add(new_doc)
    session.commit()
    return new_doc
