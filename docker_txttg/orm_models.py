from sqlalchemy import Column, Integer, String, Text, Date, ForeignKey, UniqueConstraint
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    user_id = Column(Integer, primary_key=True)
    vip_level = Column(Integer, default=0)
    vip_date = Column(String(32))

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

class FileFeedback(Base):
    __tablename__ = 'file_feedback'
    user_id = Column(Integer, ForeignKey('users.user_id'), primary_key=True)
    file_id = Column(Integer, ForeignKey('files.file_id'), primary_key=True)
    feedback = Column(Integer)  # 1=👍, -1=👎
    date = Column(String(32))
