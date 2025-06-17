from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, create_engine, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime

Base = declarative_base()

class Account(Base):
    """Account model for multi-account support"""
    __tablename__ = 'accounts'
    
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    session_name = Column(String, unique=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)

class Message(Base):
    """Message model"""
    __tablename__ = 'messages'
    
    id = Column(Integer, primary_key=True)
    account_id = Column(Integer, ForeignKey('accounts.id'), nullable=False)  # 添加账户关联
    message_id = Column(Integer, nullable=False)
    chat_id = Column(Integer, nullable=False)
    chat_title = Column(String)
    sender_id = Column(Integer)
    sender_username = Column(String)  # 添加发送者用户名
    is_bot = Column(Boolean, default=False)  # 添加是否是机器人的标记
    content = Column(String)
    media_type = Column(String)
    file_name = Column(String)
    file_path = Column(String)
    tg_file_id = Column(String)
    access_hash = Column(String)
    reference = Column(String)
    detected_keywords = Column(String)
    is_forwarded = Column(Boolean, default=False)
    timestamp = Column(DateTime, default=datetime.utcnow)

    # Add unique constraint for chat_id + message_id
    __table_args__ = (
        Index('ix_messages_account_chat_message', 'account_id', 'chat_id', 'message_id', unique=True),
    )

class Keyword(Base):
    """Keyword model"""
    __tablename__ = 'keywords'
    
    id = Column(Integer, primary_key=True)
    account_id = Column(Integer, ForeignKey('accounts.id'), nullable=False)  # 添加账户关联
    pattern = Column(String, nullable=False)
    is_regex = Column(Boolean, default=False, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Add unique constraint for pattern
    __table_args__ = (
        Index('ix_keywords_account_pattern', 'account_id', 'pattern', unique=True),
    )

class ForwardRule(Base):
    """Forward rule model"""
    __tablename__ = 'forward_rules'
    
    id = Column(Integer, primary_key=True)
    account_id = Column(Integer, ForeignKey('accounts.id'), nullable=False)  # 添加账户关联
    source_chat_id = Column(Integer, nullable=False)
    target_user_id = Column(Integer, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Add unique constraint for source_chat_id and target_user_id
    __table_args__ = (
        Index('ix_forward_rules_account_source_target', 'account_id', 'source_chat_id', 'target_user_id', unique=True),
    ) 