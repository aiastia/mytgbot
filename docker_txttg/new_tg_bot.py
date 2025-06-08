import os
import random
from datetime import datetime, timedelta
from telegram import Update, Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, CallbackQueryHandler
from dotenv import load_dotenv
from search_file import search_command, search_callback, ss_command, set_bot_username
from db_utils import (
    get_db_conn, get_user_vip_level, get_file_by_id, search_files_by_name, update_file_tg_id
)
import sqlite3  # 仅用于升级表结构和部分未迁移代码

# 加载环境变量
load_dotenv()
TOKEN = os.getenv('BOT_TOKEN')
TXT_ROOT = os.getenv('TXT_ROOT', '/app/share_folder')
DB_PATH = './data/sent_files.db'
TXT_EXTS = [x.strip() for x in os.getenv('TXT_EXTS', '.txt,.pdf').split(',') if x.strip()]

# 数据库初始化
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
conn = get_db_conn()
c = conn.cursor()
# users表
c.execute('''CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    vip_level INTEGER DEFAULT 0,
    vip_date TEXT
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

# 检查并升级 files 表结构，添加 file_size 字段（如无）
def upgrade_files_table():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("PRAGMA table_info(files)")
    columns = [row[1] for row in c.fetchall()]
    if 'file_size' not in columns:
        c.execute("ALTER TABLE files ADD COLUMN file_size INTEGER")
        conn.commit()
    conn.close()

# 检查并升级 users 表结构，添加 vip_level 和 vip_date 字段（如无）
def upgrade_users_table():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("PRAGMA table_info(users)")
    columns = [row[1] for row in c.fetchall()]
    if 'vip_level' not in columns:
        c.execute("ALTER TABLE users ADD COLUMN vip_level INTEGER DEFAULT 0")
    if 'vip_date' not in columns:
        c.execute("ALTER TABLE users ADD COLUMN vip_date TEXT")
    conn.commit()
    conn.close()

# 文件表操作

def get_or_create_file(file_path, tg_file_id=None):
    conn = get_db_conn()
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
    try:
        file_size = os.path.getsize(file_path)
    except Exception:
        file_size = None
    c.execute('INSERT INTO files (file_path, tg_file_id, file_size) VALUES (?, ?, ?)', (file_path, tg_file_id, file_size))
    conn.commit()
    file_id = c.lastrowid
    conn.close()
    return file_id

# 用户表操作

def ensure_user(user_id):
    conn = get_db_conn()
    c = conn.cursor()
    c.execute('INSERT OR IGNORE INTO users (user_id) VALUES (?)', (user_id,))
    conn.commit()
    conn.close()

def set_user_vip_level(user_id, vip_level):
    conn = get_db_conn()
    c = conn.cursor()
    vip_date = datetime.now().strftime('%Y-%m-%d') if vip_level > 0 else None
    if vip_level > 0:
        c.execute('UPDATE users SET vip_level=?, vip_date=? WHERE user_id=?', (vip_level, vip_date, user_id))
    else:
        c.execute('UPDATE users SET vip_level=0, vip_date=NULL WHERE user_id=?', (user_id,))
    conn.commit()
    conn.close()

def get_user_daily_limit(user_id):
    level = get_user_vip_level(user_id)
    if level == 3:
        return 100
    elif level == 2:
        return 50
    elif level == 1:
        return 30
    else:
        return 10

# sent_files表操作

def get_sent_file_ids(user_id):
    conn = get_db_conn()
    c = conn.cursor()
    c.execute('SELECT file_id FROM sent_files WHERE user_id=?', (user_id,))
    ids = [row[0] for row in c.fetchall()]
    conn.close()
    return ids

def mark_file_sent(user_id, file_id):
    conn = get_db_conn()
    c = conn.cursor()
    date = datetime.now().strftime('%Y-%m-%d')
    c.execute('INSERT OR IGNORE INTO sent_files (user_id, file_id, date) VALUES (?, ?, ?)', (user_id, file_id, date))
    conn.commit()
    conn.close()

def get_today_sent_count(user_id):
    conn = get_db_conn()
    c = conn.cursor()
    today = datetime.now().strftime('%Y-%m-%d')
    c.execute('SELECT COUNT(*) FROM sent_files WHERE user_id=? AND date=?', (user_id, today))
    count = c.fetchone()[0]
    conn.close()
    return count

def reload_txt_files():
    """扫描TXT_ROOT下所有txt/pdf文件，插入到数据库files表（已存在则跳过），并维护文件大小"""
    upgrade_files_table()
    txt_files = []
    for root, dirs, files in os.walk(TXT_ROOT):
        for file in files:
            if any(file.endswith(ext) for ext in TXT_EXTS):
                txt_files.append(os.path.join(root, file))
    conn = get_db_conn()
    c = conn.cursor()
    inserted, skipped = 0, 0
    for file_path in txt_files:
        try:
            file_size = os.path.getsize(file_path)
            c.execute('INSERT OR IGNORE INTO files (file_path, file_size) VALUES (?, ?)', (file_path, file_size))
            if c.rowcount == 0:
                # 已存在则尝试更新文件大小
                c.execute('UPDATE files SET file_size=? WHERE file_path=?', (file_size, file_path))
                skipped += 1
            else:
                inserted += 1
        except Exception:
            skipped += 1
    conn.commit()
    conn.close()
    return inserted, skipped

def get_all_txt_files():
    conn = get_db_conn()
    c = conn.cursor()
    c.execute('SELECT file_path FROM files')
    files = [row[0] for row in c.fetchall()]
    conn.close()
    return files

# 记录反馈
def record_feedback(user_id, file_id, feedback):
    conn = get_db_conn()
    c = conn.cursor()
    date = datetime.now().strftime('%Y-%m-%d')
    c.execute('''INSERT OR REPLACE INTO file_feedback (user_id, file_id, feedback, date)
                 VALUES (?, ?, ?, ?)''', (user_id, file_id, feedback, date))
    conn.commit()
    conn.close()

def get_unsent_files(user_id):
    all_files = get_all_txt_files()
    conn = get_db_conn()
    c = conn.cursor()
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
    daily_limit = get_user_daily_limit(user_id)
    if get_today_sent_count(user_id) >= daily_limit:
        await update.message.reply_text(f'每天最多只能领取{daily_limit}本，明天再来吧！')
        return
    unsent_files = get_unsent_files(user_id)
    if not unsent_files:
        await update.message.reply_text('你已经收到了所有文件！')
        return
    file_path = random.choice(unsent_files)
    ext = os.path.splitext(file_path)[1].lower()
    image_exts = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']
    with open(file_path, 'rb') as f:
        if ext == '.mp4':
            msg = await update.message.reply_video(
                f,
                caption="正在生成文件ID..."
            )
            tg_file_id = msg.video.file_id
        elif ext in image_exts:
            msg = await update.message.reply_photo(
                f,
                caption="正在生成文件ID..."
            )
            tg_file_id = msg.photo[-1].file_id if msg.photo else None
        else:
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
    if ext == '.mp4' or ext in image_exts:
        try:
            await msg.edit_caption(
                caption=f"文件tg_file_id: {tg_file_id}"
            )
        except Exception:
            pass
    else:
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
    conn = get_db_conn()
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
    # 直接判断 file_id 前缀类型，优先用 file_id 秒传
    if tg_file_id.startswith('BQAC') or tg_file_id.startswith('CAAC') or tg_file_id.startswith('HDAA'):
        # 文档
        await update.message.reply_document(tg_file_id, caption=f'文件tg_file_id: {tg_file_id}')
        return
    elif tg_file_id.startswith('BAAC'):
        # 视频
        await update.message.reply_video(tg_file_id, caption=f'文件tg_file_id: {tg_file_id}')
        return
    elif tg_file_id.startswith('AgAC'):
        # 图片
        await update.message.reply_photo(tg_file_id, caption=f'文件tg_file_id: {tg_file_id}')
        return
    # 兼容旧逻辑：查数据库找本地文件
    conn = get_db_conn()
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
        conn = get_db_conn()
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

# 新增命令：设置用户VIP
async def setvip_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN_USER_ID:
        await update.message.reply_text('无权限，仅管理员可用。')
        return
    if len(context.args) != 2:
        await update.message.reply_text('用法：/setvip <user_id> <0/1>')
        return
    try:
        target_id = int(context.args[0])
        vip = int(context.args[1])
        if vip not in (0, 1):
            raise ValueError
    except Exception:
        await update.message.reply_text('参数错误。')
        return
    set_user_vip_level(target_id, vip)
    await update.message.reply_text(f'用户 {target_id} VIP 状态已设置为 {vip}')

# 新增命令：设置用户VIP等级
async def setviplevel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN_USER_ID:
        await update.message.reply_text('无权限，仅管理员可用。')
        return
    if len(context.args) != 2:
        await update.message.reply_text('用法：/setviplevel <user_id> <level> (0=普通, 1=vip1, 2=vip2, 3=vip3)')
        return
    try:
        target_id = int(context.args[0])
        level = int(context.args[1])
        if level not in (0, 1, 2, 3):
            raise ValueError
    except Exception:
        await update.message.reply_text('参数错误。')
        return
    set_user_vip_level(target_id, level)
    await update.message.reply_text(f'用户 {target_id} VIP 等级已设置为 {level}')

async def on_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args and update.message:
        # 兼容 /start 无参数
        await update.message.reply_text('欢迎使用本bot！')
        return
    # 支持 deep link
    if update.message:
        start_param = update.message.text.split(' ', 1)[1] if ' ' in update.message.text else ''
    elif update.callback_query:
        start_param = update.callback_query.data.split(' ', 1)[1] if ' ' in update.callback_query.data else ''
    else:
        start_param = ''
    if start_param.startswith('book_'):
        # 只解析 file_id
        try:
            parts = start_param.split('_')
            file_id = int(parts[1])
        except Exception:
            await update.message.reply_text('参数错误。')
            return
        conn = get_db_conn()
        c = conn.cursor()
        c.execute('SELECT tg_file_id, file_path FROM files WHERE file_id=?', (file_id,))
        row = c.fetchone()
        conn.close()
        if not row:
            await update.message.reply_text('文件不存在。')
            return
        tg_file_id, file_path = row
        # 发送文件（与 search_callback 逻辑一致）
        try:
            if tg_file_id and (tg_file_id.startswith('BQAC') or tg_file_id.startswith('CAAC') or tg_file_id.startswith('HDAA')):
                await update.message.reply_document(tg_file_id, caption=f'文件tg_file_id: {tg_file_id}')
            elif tg_file_id and tg_file_id.startswith('BAAC'):
                await update.message.reply_video(tg_file_id, caption=f'文件tg_file_id: {tg_file_id}')
            elif tg_file_id and tg_file_id.startswith('AgAC'):
                await update.message.reply_photo(tg_file_id, caption=f'文件tg_file_id: {tg_file_id}')
            elif tg_file_id is None or tg_file_id == '':
                ext = os.path.splitext(file_path)[1].lower()
                if ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']:
                    with open(file_path, 'rb') as f:
                        msg = await update.message.reply_photo(f, caption='本地图片直传')
                        new_file_id = msg.photo[-1].file_id if msg.photo else None
                elif ext in ['.mp4', '.mov', '.avi', '.mkv', '.webm']:
                    with open(file_path, 'rb') as f:
                        msg = await update.message.reply_video(f, caption='本地视频直传')
                        new_file_id = msg.video.file_id
                elif os.path.exists(file_path):
                    with open(file_path, 'rb') as f:
                        msg = await update.message.reply_document(f, caption='本地文件直传')
                        new_file_id = msg.document.file_id
                else:
                    await update.message.reply_text('文件丢失。')
                    return
                # 关键：本地直传后写入tg_file_id
                if new_file_id:
                    update_file_tg_id(file_id, new_file_id)
            elif os.path.exists(file_path):
                ext = os.path.splitext(file_path)[1].lower()
                if ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']:
                    with open(file_path, 'rb') as f:
                        await update.message.reply_photo(f, caption=f'文件tg_file_id: {tg_file_id}')
                elif ext in ['.mp4', '.mov', '.avi', '.mkv', '.webm']:
                    with open(file_path, 'rb') as f:
                        await update.message.reply_video(f, caption=f'文件tg_file_id: {tg_file_id}')
                else:
                    with open(file_path, 'rb') as f:
                        await update.message.reply_document(f, caption=f'文件tg_file_id: {tg_file_id}')
            else:
                await update.message.reply_text('文件丢失。')
        except Exception as e:
            await update.message.reply_text(f'发送失败: {e}')

def main():
    upgrade_users_table()  # 启动时自动升级users表结构
    base_url = os.getenv('TELEGRAM_API_URL')
    builder = ApplicationBuilder().token(TOKEN)
    if base_url:
        builder = builder.base_url(f"{base_url}/bot").base_file_url(f"{base_url}/file/bot")
    app = builder.build()

    # 用 post_init 钩子自动注入 bot 用户名
    async def set_username(app):
        me = await app.bot.get_me()
        set_bot_username(me.username)
    app.post_init = set_username

    app.add_handler(CommandHandler('random', send_random_txt))
    app.add_handler(CommandHandler('stats', stats))
    app.add_handler(CommandHandler('hot', hot))
    app.add_handler(CommandHandler('getfile', getfile))
    app.add_handler(CommandHandler('reload', reload_command))
    app.add_handler(CommandHandler('setviplevel', setviplevel_command))
    app.add_handler(CommandHandler('start', on_start))
    app.add_handler(CommandHandler('s', search_command))
    app.add_handler(CommandHandler('ss', ss_command))
    app.add_handler(CallbackQueryHandler(search_callback, pattern=r'^(spage|sget)\|'))
    app.add_handler(CallbackQueryHandler(feedback_callback, pattern=r'^feedback\|'))
    app.run_polling()

if __name__ == '__main__':
    main()
