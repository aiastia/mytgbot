import sqlite3
import os

DB_PATH = './data/sent_files.db'

def get_db_conn():
    return sqlite3.connect(DB_PATH)

def get_user_vip_level(user_id):
    conn = get_db_conn()
    c = conn.cursor()
    c.execute('SELECT vip_level FROM users WHERE user_id=?', (user_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else 0

def get_file_by_id(file_id):
    conn = get_db_conn()
    c = conn.cursor()
    c.execute('SELECT tg_file_id, file_path FROM files WHERE file_id=?', (file_id,))
    row = c.fetchone()
    conn.close()
    return row

def search_files_by_name(keyword):
    conn = get_db_conn()
    c = conn.cursor()
    c.execute("SELECT file_id, file_path, tg_file_id FROM files WHERE file_path LIKE ? ORDER BY file_id DESC", (f"%{keyword}%",))
    results = c.fetchall()
    conn.close()
    return results

def update_file_tg_id(file_id, tg_file_id):
    conn = get_db_conn()
    c = conn.cursor()
    c.execute('UPDATE files SET tg_file_id=? WHERE file_id=?', (tg_file_id, file_id))
    conn.commit()
    conn.close()
