from alembic import op
import sqlalchemy as sa
from datetime import datetime

# 创建账户表
def create_accounts_table():
    op.create_table(
        'accounts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('session_name', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(), default=datetime.utcnow),
        sa.Column('is_active', sa.Boolean(), default=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
        sa.UniqueConstraint('session_name')
    )

# 修改消息表
def modify_messages_table():
    # 添加账户ID列
    op.add_column('messages', sa.Column('account_id', sa.Integer(), nullable=True))
    
    # 创建外键约束
    op.create_foreign_key(
        'fk_messages_account_id',
        'messages', 'accounts',
        ['account_id'], ['id']
    )
    
    # 创建复合唯一索引
    op.create_index(
        'ix_messages_account_chat_message',
        'messages',
        ['account_id', 'chat_id', 'message_id'],
        unique=True
    )

# 修改关键词表
def modify_keywords_table():
    # 添加账户ID列
    op.add_column('keywords', sa.Column('account_id', sa.Integer(), nullable=True))
    
    # 创建外键约束
    op.create_foreign_key(
        'fk_keywords_account_id',
        'keywords', 'accounts',
        ['account_id'], ['id']
    )
    
    # 创建复合唯一索引
    op.create_index(
        'ix_keywords_account_pattern',
        'keywords',
        ['account_id', 'pattern'],
        unique=True
    )

# 修改转发规则表
def modify_forward_rules_table():
    # 添加账户ID列
    op.add_column('forward_rules', sa.Column('account_id', sa.Integer(), nullable=True))
    
    # 创建外键约束
    op.create_foreign_key(
        'fk_forward_rules_account_id',
        'forward_rules', 'accounts',
        ['account_id'], ['id']
    )
    
    # 创建复合唯一索引
    op.create_index(
        'ix_forward_rules_account_source_target',
        'forward_rules',
        ['account_id', 'source_chat_id', 'target_user_id'],
        unique=True
    )

def upgrade():
    """执行数据库升级"""
    create_accounts_table()
    modify_messages_table()
    modify_keywords_table()
    modify_forward_rules_table()

def downgrade():
    """回滚数据库更改"""
    # 删除索引和外键
    op.drop_index('ix_forward_rules_account_source_target', 'forward_rules')
    op.drop_index('ix_keywords_account_pattern', 'keywords')
    op.drop_index('ix_messages_account_chat_message', 'messages')
    
    op.drop_constraint('fk_forward_rules_account_id', 'forward_rules')
    op.drop_constraint('fk_keywords_account_id', 'keywords')
    op.drop_constraint('fk_messages_account_id', 'messages')
    
    # 删除账户ID列
    op.drop_column('forward_rules', 'account_id')
    op.drop_column('keywords', 'account_id')
    op.drop_column('messages', 'account_id')
    
    # 删除账户表
    op.drop_table('accounts') 