import os
from orm_utils import get_engine, init_db
from sqlalchemy import text

def migrate_db():
    """数据库迁移工具"""
    engine = get_engine()
    
    # 检查并创建新字段
    def add_column_if_not_exists(table_name, column_name, column_type):
        with engine.connect() as conn:
            # 检查字段是否存在
            if engine.url.drivername == 'sqlite':
                result = conn.execute(text(f"PRAGMA table_info({table_name})"))
                columns = [row[1] for row in result.fetchall()]
                if column_name not in columns:
                    # SQLite添加字段
                    conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"))
                    print(f"已添加字段: {table_name}.{column_name}")
            else:
                # MySQL添加字段
                result = conn.execute(text(f"SHOW COLUMNS FROM {table_name} LIKE '{column_name}'"))
                if not result.fetchone():
                    conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"))
                    print(f"已添加字段: {table_name}.{column_name}")

    try:
        # 确保表存在
        init_db()
        print("表结构已更新")

        # 在这里添加新字段
        # 例如: add_column_if_not_exists('users', 'email', 'VARCHAR(255)')
        add_column_if_not_exists('users', 'email', 'VARCHAR(255)')
        add_column_if_not_exists('users', 'vio', 'VARCHAR(255)')
        
        print("数据库迁移完成")
    except Exception as e:
        print(f"迁移出错: {e}")

if __name__ == '__main__':
    migrate_db()
