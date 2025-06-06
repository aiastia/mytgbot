import os
import random
import sqlite3
from datetime import datetime, timedelta
from telegram import Update, Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, CallbackQueryHandler
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()
TOKEN = os.getenv('BOT_TOKEN')
TXT_ROOT = os.getenv('TXT_ROOT', '/app/share_folder')
DB_PATH = './data/sent_files.db'

# 数据库初始化
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()
# users表
c.execute('''CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY
)''')
# files表
c.execute('''CREATE TABLE IF NOT EXISTS files (
    file_id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path TEXT UNIQUE,
    tg_file_id TEXT
)''')
# sent_files中间表
c.execute('''CREATE TABLE IF NOT EXISTS sent_files (
    user_id INTEGER,
    file_id INTEGER,
    date TEXT,
    PRIMARY KEY (user_id, file_id),
    FOREIGN KEY (user_id) REFERENCES users(user_id),
    FOREIGN KEY (file_id) REFERENCES files(file_id)
)''')
# 新增反馈表
c.execute('''CREATE TABLE IF NOT EXISTS file_feedback (
    user_id INTEGER,
    file_id INTEGER,
    feedback INTEGER, -- 1=👍, -1=👎
    date TEXT,
    PRIMARY KEY (user_id, file_id),
    FOREIGN KEY (user_id) REFERENCES users(user_id),
    FOREIGN KEY (file_id) REFERENCES files(file_id)
)''')
conn.commit()
conn.close()

ADMIN_USER_ID = [int(x) for x in os.environ.get('ADMIN_USER_ID', '12345678').split(',') if x.strip().isdigit()]
print(f"Admin User IDs: {ADMIN_USER_ID}")
# 文件表操作

def get_or_create_file(file_path, tg_file_id=None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT file_id, tg_file_id FROM files WHERE file_path=?', (file_path,))
    row = c.fetchone()
    if row:
        file_id, old_tg_file_id = row
        if tg_file_id and tg_file_id != old_tg_file_id:
            c.execute('UPDATE files SET tg_file_id=? WHERE file_id=?', (tg_file_id, file_id))
            conn.commit()
        conn.close()
        return file_id
    c.execute('INSERT INTO files (file_path, tg_file_id) VALUES (?, ?)', (file_path, tg_file_id))
    conn.commit()
    file_id = c.lastrowid
    conn.close()
    return file_id

# 用户表操作

def ensure_user(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('INSERT OR IGNORE INTO users (user_id) VALUES (?)', (user_id,))
    conn.commit()
    conn.close()

# sent_files表操作

def get_sent_file_ids(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT file_id FROM sent_files WHERE user_id=?', (user_id,))
    ids = [row[0] for row in c.fetchall()]
    conn.close()
    return ids

def mark_file_sent(user_id, file_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    date = datetime.now().strftime('%Y-%m-%d')
    c.execute('INSERT OR IGNORE INTO sent_files (user_id, file_id, date) VALUES (?, ?, ?)', (user_id, file_id, date))
    conn.commit()
    conn.close()

def get_today_sent_count(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    today = datetime.now().strftime('%Y-%m-%d')
    c.execute('SELECT COUNT(*) FROM sent_files WHERE user_id=? AND date=?', (user_id, today))
    count = c.fetchone()[0]
    conn.close()
    return count

def reload_txt_files():
    """扫描TXT_ROOT下所有txt文件，插入到数据库files表（已存在则跳过）"""
    txt_files = []
    for root, dirs, files in os.walk(TXT_ROOT):
        for file in files:
            if file.endswith('.pdf') or file.endswith('.txt'):
                txt_files.append(os.path.join(root, file))
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    inserted, skipped = 0, 0
    for file_path in txt_files:
        try:
            c.execute('INSERT OR IGNORE INTO files (file_path) VALUES (?)', (file_path,))
            if c.rowcount:
                inserted += 1
            else:
                skipped += 1
        except Exception:
            skipped += 1
    conn.commit()
    conn.close()
    return inserted, skipped

def get_all_txt_files():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT file_path FROM files')
    files = [row[0] for row in c.fetchall()]
    conn.close()
    return files

# 记录反馈
def record_feedback(user_id, file_id, feedback):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    date = datetime.now().strftime('%Y-%m-%d')
    c.execute('''INSERT OR REPLACE INTO file_feedback (user_id, file_id, feedback, date)
                 VALUES (?, ?, ?, ?)''', (user_id, file_id, feedback, date))
    conn.commit()
    conn.close()

def get_unsent_files(user_id):
    all_files = get_all_txt_files()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # 获取所有file_id和file_path
    c.execute('SELECT file_id, file_path FROM files')
    file_map = {row[1]: row[0] for row in c.fetchall()}
    sent_ids = set(get_sent_file_ids(user_id))
    unsent = []
    for file_path in all_files:
        file_id = file_map.get(file_path)
        if file_id is None:
            unsent.append(file_path)
        elif file_id not in sent_ids:
            unsent.append(file_path)
    conn.close()
    return unsent

async def send_random_txt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    ensure_user(user_id)
    if get_today_sent_count(user_id) >= 5:
        await update.message.reply_text('每天最多只能领取5本，明天再来吧！')
        return
    unsent_files = get_unsent_files(user_id)
    if not unsent_files:
        await update.message.reply_text('你已经收到了所有文件！')
        return
    file_path = random.choice(unsent_files)
    # 只发送一次文件，带按钮和caption
    with open(file_path, 'rb') as f:
        # 评分按钮，初始无高亮
        keyboard = [
            [
                InlineKeyboardButton("👍", callback_data=f"feedback|{{file_id}}|1"),
                InlineKeyboardButton("👎", callback_data=f"feedback|{{file_id}}|-1"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        msg = await update.message.reply_document(
            f,
            caption="正在生成文件ID...",
            reply_markup=reply_markup
        )
    tg_file_id = msg.document.file_id
    file_id = get_or_create_file(file_path, tg_file_id)
    mark_file_sent(user_id, file_id)
    # 发送后立即更新caption和按钮（防止file_id为None）
    keyboard = [
        [
            InlineKeyboardButton("👍", callback_data=f"feedback|{file_id}|1"),
            InlineKeyboardButton("👎", callback_data=f"feedback|{file_id}|-1"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    try:
        await msg.edit_caption(
            caption=f"文件tg_file_id: {tg_file_id}",
            reply_markup=reply_markup
        )
    except Exception:
        pass

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    ensure_user(user_id)
    count = len(get_sent_file_ids(user_id))
    await update.message.reply_text(f'你已收到 {count} 个文件。')

# 热榜展示 tg_file_id
async def hot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    seven_days_ago = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
    c.execute('''
        SELECT f.file_path, f.tg_file_id, COUNT(*) as likes
        FROM file_feedback fb
        JOIN files f ON fb.file_id = f.file_id
        WHERE fb.feedback=1 AND fb.date >= ?
        GROUP BY fb.file_id
        ORDER BY likes DESC, f.file_path ASC
        LIMIT 10
    ''', (seven_days_ago,))
    rows = c.fetchall()
    conn.close()
    if not rows:
        await update.message.reply_text('最近7天还没有文件收到👍，快去评分吧！')
        return
    msg = '🔥 <b>热榜（近7天👍最多的文件）</b> 🔥\n\n'
    for idx, (file_path, tg_file_id, likes) in enumerate(rows, 1):
        filename = os.path.basename(file_path)
        msg += f'<b>{idx}. {filename}</b>\n📄 <code>{tg_file_id}</code>\n👍 <b>{likes}</b>\n\n'
    await update.message.reply_text(msg, parse_mode='HTML')

# 新增命令：用户输入tg_file_id获取文件
async def getfile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text('用法：/getfile <tg_file_id>')
        return
    tg_file_id = context.args[0]
    # 查询文件名
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT file_path FROM files WHERE tg_file_id=?', (tg_file_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        await update.message.reply_text('未找到该文件。')
        return
    file_path = row[0]
    if not os.path.exists(file_path):
        await update.message.reply_text('文件已丢失或被删除。')
        return
    with open(file_path, 'rb') as f:
        await update.message.reply_document(f, caption=f'文件tg_file_id: {tg_file_id}')

# 处理评分回调，按钮高亮
import telegram
async def feedback_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data.split('|')
    if len(data) == 3 and data[0] == 'feedback':
        file_id = int(data[1])
        feedback = int(data[2])
        record_feedback(user_id, file_id, feedback)
        # 查找tg_file_id
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('SELECT tg_file_id FROM files WHERE file_id=?', (file_id,))
        row = c.fetchone()
        conn.close()
        tg_file_id = row[0] if row else ''
        # 按钮高亮
        if feedback == 1:
            keyboard = [
                [
                    InlineKeyboardButton("👍 已选", callback_data=f"feedback|{file_id}|1"),
                    InlineKeyboardButton("👎", callback_data=f"feedback|{file_id}|-1"),
                ]
            ]
        else:
            keyboard = [
                [
                    InlineKeyboardButton("👍", callback_data=f"feedback|{file_id}|1"),
                    InlineKeyboardButton("👎 已选", callback_data=f"feedback|{file_id}|-1"),
                ]
            ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        try:
            await query.edit_message_caption(
                caption=f"文件tg_file_id: {tg_file_id}",
                reply_markup=reply_markup
            )
        except telegram.error.BadRequest as e:
            if 'Message is not modified' in str(e):
                pass  # 用户重复点击同一按钮，忽略即可
            else:
                raise

from telegram.ext import CommandHandler
async def reload_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN_USER_ID:
        await update.message.reply_text('无权限，仅管理员可用。')
        return
    inserted, skipped = reload_txt_files()
    await update.message.reply_text(f'刷新完成，新增 {inserted} 个文件，跳过 {skipped} 个已存在。')

def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler('random', send_random_txt))
    app.add_handler(CommandHandler('stats', stats))
    app.add_handler(CommandHandler('hot', hot))
    app.add_handler(CommandHandler('getfile', getfile))
    app.add_handler(CommandHandler('reload', reload_command))
    app.add_handler(CallbackQueryHandler(feedback_callback, pattern=r'^feedback\\|'))
    app.run_polling()

if __name__ == '__main__':
    main()
