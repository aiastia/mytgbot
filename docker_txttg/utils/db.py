from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey, Boolean, Float, Text, Date, UniqueConstraint, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
import os
from config import DATABASE_URL

# 数据库配置
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

# 数据库模型
class User(Base):
    __tablename__ = 'users'
    user_id = Column(Integer, primary_key=True)
    vip_level = Column(Integer, default=0)
    vip_date = Column(String(32))  # VIP开始日期
    vip_expiry_date = Column(String(32))  # VIP过期日期
    points = Column(Integer, default=0)
    last_checkin = Column(String(32))

class File(Base):
    __tablename__ = 'files'
    file_id = Column(Integer, primary_key=True, autoincrement=True)
    file_path = Column(Text, unique=True)
    tg_file_id = Column(Text)
    file_size = Column(Integer)

class SentFile(Base):
    __tablename__ = 'sent_files'
    user_id = Column(Integer, ForeignKey('users.user_id'), primary_key=True)
    file_id = Column(Integer, ForeignKey('files.file_id'), primary_key=True)
    date = Column(String(32))
    source = Column(String(20), default='file')  # 'file' 表示来自 files 表，'uploaded' 表示来自 uploaded_documents 表

class FileFeedback(Base):
    __tablename__ = 'file_feedback'
    user_id = Column(Integer, ForeignKey('users.user_id'), primary_key=True)
    file_id = Column(Integer, ForeignKey('files.file_id'), primary_key=True)
    feedback = Column(Integer)  # 1=👍, -1=👎
    date = Column(String(32))

class UploadedDocument(Base):
    __tablename__ = 'uploaded_documents'
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.user_id'))
    file_name = Column(String(255))
    file_size = Column(Integer)
    tg_file_id = Column(String(255))
    upload_time = Column(String(32))
    status = Column(String(20), default='pending')  # pending, approved, rejected
    approved_by = Column(Integer, ForeignKey('users.user_id'), nullable=True)
    is_downloaded = Column(Boolean, default=False)
    download_path = Column(String(255), nullable=True)
    
    __table_args__ = (
        UniqueConstraint('file_name', 'file_size', name='uix_file_name_size'),
    )

class LicenseCode(Base):
    __tablename__ = 'license_codes'
    
    id = Column(Integer, primary_key=True)
    code = Column(String, unique=True, nullable=False)
    user_id = Column(Integer, nullable=False)
    points = Column(Integer, nullable=False)
    redeemed_at = Column(String, nullable=False)
    license_info = Column(String, nullable=True)
    
    def __repr__(self):
        return f"<LicenseCode(code='{self.code}', user_id={self.user_id}, points={self.points})>"

def upgrade_users_table():
    """升级users表结构"""
    with SessionLocal() as session:
        try:
            # 检查表是否存在
            session.execute(text("SELECT 1 FROM users LIMIT 1"))
        except Exception:
            # 如果表不存在，创建表
            Base.metadata.tables['users'].create(engine)
            return

        # 检查并添加必要的列
        columns_to_add = [
            ('vip_date', 'VARCHAR(32)'),
            ('vip_expiry_date', 'VARCHAR(32)'),
            ('last_checkin', 'VARCHAR(32)')
        ]

        for column_name, column_def in columns_to_add:
            try:
                session.execute(text(f"SELECT {column_name} FROM users LIMIT 1"))
            except Exception:
                try:
                    session.execute(text(f"ALTER TABLE users ADD COLUMN {column_name} {column_def}"))
                    session.commit()
                    print(f"Added column {column_name} to users table")
                except Exception as e:
                    print(f"Error adding column {column_name}: {e}")
                    session.rollback()

# 创建表
Base.metadata.create_all(engine) 