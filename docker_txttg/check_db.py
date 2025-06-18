import sqlite3
from config import DATABASE_URL

def check_database():
    # 从 DATABASE_URL 中提取数据库文件路径
    db_path = DATABASE_URL.replace('sqlite:///', '')
    
    # 连接到数据库
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # 获取所有表
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    print("Tables in database:", [table[0] for table in tables])
    
    # 检查 users 表结构
    cursor.execute("PRAGMA table_info(users);")
    columns = cursor.fetchall()
    print("\nUsers table structure:")
    for col in columns:
        print(f"Column: {col[1]}, Type: {col[2]}, NotNull: {col[3]}, Default: {col[4]}, PK: {col[5]}")
    
    # 检查 sent_files 表结构
    cursor.execute("PRAGMA table_info(sent_files);")
    columns = cursor.fetchall()
    print("\nSent_files table structure:")
    for col in columns:
        print(f"Column: {col[1]}, Type: {col[2]}, NotNull: {col[3]}, Default: {col[4]}, PK: {col[5]}")
    
    # 检查是否有数据
    cursor.execute("SELECT COUNT(*) FROM users;")
    count = cursor.fetchone()[0]
    print(f"\nNumber of records in users table: {count}")
    
    # 如果有数据，显示第一条记录
    if count > 0:
        cursor.execute("SELECT * FROM users LIMIT 1;")
        record = cursor.fetchone()
        print("\nFirst record in users table:")
        for col, val in zip([col[1] for col in columns], record):
            print(f"{col}: {val}")
    
    conn.close()

if __name__ == "__main__":
    check_database() 