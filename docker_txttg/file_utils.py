import os
import random
from orm_utils import SessionLocal
from orm_models import File, UploadedDocument, SentFile
from db_utils import get_or_create_file, mark_file_sent

TXT_ROOT = os.getenv('TXT_ROOT', '/app/share_folder')
TXT_EXTS = [x.strip() for x in os.getenv('TXT_EXTS', '.txt,.pdf').split(',') if x.strip()]

def reload_txt_files():
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

def get_unsent_files(user_id):
    with SessionLocal() as session:
        file_ids = {row.file_id for row in session.query(File.file_id).all()}
        uploaded_ids = {doc.id for doc in session.query(UploadedDocument).filter_by(status='approved').all()}
        sent_file_ids = {record.file_id for record in session.query(SentFile).filter_by(user_id=user_id, source='file').all()}
        sent_uploaded_ids = {record.file_id for record in session.query(SentFile).filter_by(user_id=user_id, source='uploaded').all()}
        unsent_file_ids = list(file_ids - sent_file_ids)
        unsent_uploaded_ids = list(uploaded_ids - sent_uploaded_ids)
        if not unsent_file_ids and not unsent_uploaded_ids:
            return None
        if unsent_file_ids and unsent_uploaded_ids:
            if random.random() < 0.7:
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
