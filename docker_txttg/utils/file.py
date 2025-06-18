import os
from datetime import datetime
from utils.db import SessionLocal, File, UploadedDocument
from config import TXT_ROOT, TXT_EXTS

def get_or_create_file(file_path, tg_file_id=None):
    """获取或创建文件记录，返回文件ID"""
    with SessionLocal() as session:
        # 首先检查是否是上传的文档
        uploaded_doc = session.query(UploadedDocument).filter_by(download_path=file_path).first()
        if uploaded_doc:
            # 如果文件已经存在于 File 表中，更新 tg_file_id
            file = session.query(File).filter_by(file_path=file_path).first()
            if file:
                if tg_file_id and tg_file_id != file.tg_file_id:
                    file.tg_file_id = tg_file_id
                    session.commit()
                return file.file_id
            # 如果文件不存在于 File 表中，创建新记录
            file_size = os.path.getsize(file_path)
            new_file = File(
                file_path=file_path,
                tg_file_id=uploaded_doc.tg_file_id or tg_file_id,
                file_size=file_size
            )
            session.add(new_file)
            session.commit()
            return new_file.file_id

        # 处理普通文件
        file = session.query(File).filter_by(file_path=file_path).first()
        if file:
            if tg_file_id and tg_file_id != file.tg_file_id:
                file.tg_file_id = tg_file_id
                session.commit()
            return file.file_id
            
        # 创建新文件记录
        file_size = None
        try:
            file_size = os.path.getsize(file_path)
        except Exception:
            pass
        new_file = File(file_path=file_path, tg_file_id=tg_file_id, file_size=file_size)
        session.add(new_file)
        session.commit()
        return new_file.file_id

def reload_txt_files():
    """扫描TXT_ROOT下所有txt/pdf文件，插入到数据库files表（已存在则跳过），并维护文件大小"""
    txt_files = []
    for root, dirs, files in os.walk(TXT_ROOT):
        for file in files:
            if any(file.endswith(ext) for ext in TXT_EXTS):
                txt_files.append(os.path.join(root, file))
    inserted, skipped = 0, 0
    with SessionLocal() as session:
        for file_path in txt_files:
            try:
                file_size = os.path.getsize(file_path)
                file = session.query(File).filter_by(file_path=file_path).first()
                if file:
                    if file.file_size != file_size:
                        file.file_size = file_size
                        session.commit()
                    skipped += 1
                else:
                    new_file = File(file_path=file_path, file_size=file_size)
                    session.add(new_file)
                    session.commit()
                    inserted += 1
            except Exception:
                skipped += 1
    return inserted, skipped 