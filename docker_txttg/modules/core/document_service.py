from modules.db.orm_utils import SessionLocal
from modules.db.orm_models import UploadedDocument, File
from datetime import datetime
from .points_system import add_points
import os
from ..config.config import DOWNLOAD_DIR

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

def approve_document(session, doc_id, admin_id):
    doc = session.query(UploadedDocument).filter_by(id=doc_id).first()
    if not doc:
        return None, "文档不存在"
    doc.status = 'approved'
    doc.approved_by = admin_id
    new_points = add_points(doc.user_id, 5)
    session.commit()
    return doc, new_points

def reject_document(session, doc_id, admin_id):
    doc = session.query(UploadedDocument).filter_by(id=doc_id).first()
    if not doc:
        return None
    doc.status = 'rejected'
    session.commit()
    return doc

async def approve_and_download_document(session, doc_id, admin_id, bot):
    doc = session.query(UploadedDocument).filter_by(id=doc_id).first()
    if not doc:
        return None, "文档不存在"
    if doc.is_downloaded and doc.download_path and os.path.exists(doc.download_path):
        return None, "文件已经被其他管理员下载过了"
    doc.status = 'approved'
    doc.approved_by = admin_id
    doc.is_downloaded = True
    try:
        file_info = await bot.get_file(doc.tg_file_id)
        if not file_info:
            return None, "无法获取文件信息"
        download_path = os.path.join(DOWNLOAD_DIR, doc.file_name).replace('\\', '/')
        await file_info.download_to_drive(custom_path=download_path)
        doc.download_path = download_path
        new_points = add_points(doc.user_id, 5)
        session.commit()
        return doc, new_points
    except Exception as e:
        session.commit()
        return doc, f"下载失败: {str(e)}"

def batch_approve_documents(session, admin_id):
    pending_docs = session.query(UploadedDocument).filter(
        UploadedDocument.status == 'pending'
    ).all()
    approved_count = 0
    for doc in pending_docs:
        doc.status = 'approved'
        doc.approved_by = admin_id
        add_points(doc.user_id, 5)
        approved_count += 1
    session.commit()
    return approved_count, pending_docs

def get_pending_documents(session, page, page_size):
    total_count = session.query(UploadedDocument).filter(
        UploadedDocument.status == 'approved',
        UploadedDocument.is_downloaded == False
    ).count()
    total_pages = (total_count + page_size - 1) // page_size
    docs = session.query(UploadedDocument).filter(
        UploadedDocument.status == 'approved',
        UploadedDocument.is_downloaded == False
    ).order_by(
        UploadedDocument.file_size.asc()
    ).offset(
        (page - 1) * page_size
    ).limit(page_size).all()
    return docs, total_count, total_pages

async def batch_download_documents(session, docs, bot, download_dir):
    successful = 0
    failed = 0
    for doc in docs:
        try:
            file = await bot.get_file(doc.tg_file_id)
            file_name = doc.file_name
            os.makedirs(download_dir, exist_ok=True)
            download_path = os.path.join(download_dir, file_name).replace('\\', '/')
            await file.download_to_drive(custom_path=download_path)
            doc.download_path = download_path
            doc.is_downloaded = True
            session.commit()
            successful += 1
        except Exception as e:
            failed += 1
            continue
    return successful, failed
