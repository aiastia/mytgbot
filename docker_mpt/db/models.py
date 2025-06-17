from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, create_engine, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime

Base = declarative_base()

class Message(Base):
    __tablename__ = 'messages'
    
    id = Column(Integer, primary_key=True)
    message_id = Column(Integer, nullable=False)
    chat_id = Column(Integer, nullable=False)
    chat_title = Column(String)
    sender_id = Column(Integer)
    timestamp = Column(DateTime, default=datetime.utcnow)
    content = Column(String)
    media_type = Column(String)
    file_name = Column(String)
    file_path = Column(String)
    tg_file_id = Column(String)
    access_hash = Column(String)
    reference = Column(String)
    is_forwarded = Column(Boolean, default=False)
    detected_keywords = Column(String)

    # Add unique constraint for chat_id + message_id
    __table_args__ = (
        Index('idx_chat_message', 'chat_id', 'message_id', unique=True),
    )

class Keyword(Base):
    __tablename__ = 'keywords'
    
    id = Column(Integer, primary_key=True)
    pattern = Column(String, nullable=False)
    is_regex = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class ForwardRule(Base):
    __tablename__ = 'forward_rules'
    
    id = Column(Integer, primary_key=True)
    source_chat_id = Column(Integer, nullable=False)
    target_user_id = Column(Integer, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Add index for source_chat_id
    __table_args__ = (
        Index('idx_source_chat', 'source_chat_id'),
    ) 