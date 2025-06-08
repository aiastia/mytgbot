import os
import random
from datetime import datetime, timedelta
from telegram import Update, Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram import InputFile
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, CallbackQueryHandler
from dotenv import load_dotenv
from search_file import search_command, search_callback, ss_command, set_bot_username, split_message
from search_file import ss_callback
from orm_utils import SessionLocal, init_db
from orm_models import User, File, SentFile, FileFeedback
from db_migrate import migrate_db  # 导入数据库迁移函数

# 加载环境变量
load_dotenv()
TOKEN = os.getenv('BOT_TOKEN')
TXT_ROOT = os.getenv('TXT_ROOT', '/app/share_folder')
DB_PATH = './data/sent_files.db'
TXT_EXTS = [x.strip() for x in os.getenv('TXT_EXTS', '.txt,.pdf').split(',') if x.strip()]

# 数据库初始化和迁移
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
init_db()
print("正在检查数据库更新...")
migrate_db()  # 执行数据库迁移
print("数据库检查完成")

ADMIN_USER_ID = [int(x) for x in os.environ.get('ADMIN_USER_ID', '12345678').split(',') if x.strip().isdigit()]
print(f"Admin User IDs: {ADMIN_USER_ID}")

# ORM操作示例函数

def get_or_create_file(file_path, tg_file_id=None):
    with SessionLocal() as session:
        file = session.query(File).filter_by(file_path=file_path).first()
        if file:
            if tg_file_id and tg_file_id != file.tg_file_id:
                file.tg_file_id = tg_file_id
                session.commit()
            return file.file_id
        file_size = None
        try:
            file_size = os.path.getsize(file_path)
        except Exception:
            pass
        new_file = File(file_path=file_path, tg_file_id=tg_file_id, file_size=file_size)
        session.add(new_file)
        session.commit()
        return new_file.file_id

def ensure_user(user_id):
    with SessionLocal() as session:
        user = session.query(User).filter_by(user_id=user_id).first()
        if not user:
            session.add(User(user_id=user_id))
            session.commit()

def set_user_vip_level(user_id, vip_level):
    with SessionLocal() as session:
        user = session.query(User).filter_by(user_id=user_id).first()
        if user:
            vip_date = datetime.now().strftime('%Y-%m-%d') if vip_level > 0 else None
            if vip_level > 0:
                user.vip_level = vip_level
                user.vip_date = vip_date
            else:
                user.vip_level = 0
                user.vip_date = None
            session.commit()

def get_user_vip_level(user_id):
    with SessionLocal() as session:
        user = session.query(User).filter_by(user_id=user_id).first()
        return user.vip_level if user else 0

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

def get_sent_file_ids(user_id):
    with SessionLocal() as session:
        ids = [row.file_id for row in session.query(SentFile.file_id).filter_by(user_id=user_id).all()]
    return ids

def mark_file_sent(user_id, file_id):
    with SessionLocal() as session:
        date = datetime.now().strftime('%Y-%m-%d')
        session.merge(SentFile(user_id=user_id, file_id=file_id, date=date))

def get_today_sent_count(user_id):
    with SessionLocal() as session:
        today = datetime.now().strftime('%Y-%m-%d')
        count = session.query(SentFile).filter_by(user_id=user_id, date=today).count()
    return count

def upgrade_files_table():
    pass  # ORM自动管理表结构，无需手动升级

def upgrade_users_table():
    pass  # ORM自动管理表结构，无需手动升级

def reload_txt_files():
    """扫描TXT_ROOT下所有txt/pdf文件，插入到数据库files表（已存在则跳过），并维护文件大小"""
    txt_files = []
    for root, dirs, files in os.walk(TXT_ROOT):
        for file in files:
            if any(file.endswith(ext) for ext in TXT_EXTS):
                txt_files.append(os.path.join(root, file))
    inserted, skipped = 0, 0
    with SessionLocal() as session:
        for file_path in txt_files:
            try:
                file_size = os.path.getsize(file_path)
                file = session.query(File).filter_by(file_path=file_path).first()
                if file:
                    if file.file_size != file_size:
                        file.file_size = file_size
                        session.commit()
                    skipped += 1
                else:
                    new_file = File(file_path=file_path, file_size=file_size)
                    session.add(new_file)
                    session.commit()
                    inserted += 1
            except Exception:
                skipped += 1
    return inserted, skipped

def get_all_txt_files():
    with SessionLocal() as session:
        files = [row.file_path for row in session.query(File.file_path).all()]
    return files

# 记录反馈
def record_feedback(user_id, file_id, feedback):
    with SessionLocal() as session:
        date = datetime.now().strftime('%Y-%m-%d')
        session.merge(FileFeedback(user_id=user_id, file_id=file_id, feedback=feedback, date=date))

def get_unsent_files(user_id):
    all_files = get_all_txt_files()
    with SessionLocal() as session:
        file_map = {row.file_path: row.file_id for row in session.query(File.file_id, File.file_path).all()}
        sent_ids = set(get_sent_file_ids(user_id))
    unsent = []
    for file_path in all_files:
        file_id = file_map.get(file_path)
        if file_id is None:
            unsent.append(file_path)
        elif file_id not in sent_ids:
            unsent.append(file_path)
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

HOT_PAGE_SIZE = 10

async def hot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_hot_page(update, context, page=0, edit=False)

async def hot_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data.split('|')
    if len(data) == 2 and data[0] == 'hotpage':
        page = int(data[1])
        await send_hot_page(update, context, page=page, edit=True)

async def send_hot_page(update, context, page=0, edit=False):
    with SessionLocal() as session:
        from sqlalchemy import func
        seven_days_ago = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
        likes_subq = session.query(
            FileFeedback.file_id,
            func.count().label('likes')
        ).filter(
            FileFeedback.feedback == 1,
            FileFeedback.date >= seven_days_ago
        ).group_by(FileFeedback.file_id).subquery()
        rows = (
            session.query(
                File.file_path,
                File.tg_file_id,
                func.coalesce(likes_subq.c.likes, 0)
            )
            .outerjoin(likes_subq, File.file_id == likes_subq.c.file_id)
            .filter(likes_subq.c.likes != None)
            .order_by(likes_subq.c.likes.desc(), File.file_path)
            .all()
        )
    total = len(rows)
    if total == 0:
        msg = '最近7天还没有文件收到，快去评分吧！'
        if edit and update.callback_query:
            await update.callback_query.edit_message_text(msg)
        else:
            await update.message.reply_text(msg)
        return
    start = page * HOT_PAGE_SIZE
    end = start + HOT_PAGE_SIZE
    page_rows = rows[start:end]
    msg = '🔥 <b>热榜（近7天👍最多的文件）</b> 🔥\n\n'
    for idx, (file_path, tg_file_id, likes) in enumerate(page_rows, start+1):
        filename = os.path.basename(file_path)
        msg += f'<b>{idx}. {filename}</b>\n📄 <code>{tg_file_id}</code>\n👍 <b>{likes}</b>\n\n'
    # 分页按钮
    buttons = []
    if page > 0:
        buttons.append(InlineKeyboardButton('上一页', callback_data=f'hotpage|{page-1}'))
    if end < total:
        buttons.append(InlineKeyboardButton('下一页', callback_data=f'hotpage|{page+1}'))
    reply_markup = InlineKeyboardMarkup([buttons]) if buttons else None
    if edit and update.callback_query:
        await update.callback_query.edit_message_text(msg, parse_mode='HTML', reply_markup=reply_markup)
    else:
        await update.message.reply_text(msg, parse_mode='HTML', reply_markup=reply_markup)

# 新增命令：用户输入tg_file_id获取文件
async def getfile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text('用法：/getfile <tg_file_id>')
        return
    tg_file_id = context.args[0]
    if tg_file_id.startswith('BQAC') or tg_file_id.startswith('CAAC') or tg_file_id.startswith('HDAA'):
        await update.message.reply_document(tg_file_id, caption=f'文件tg_file_id: {tg_file_id}')
        return
    elif tg_file_id.startswith('BAAC'):
        await update.message.reply_video(tg_file_id, caption=f'文件tg_file_id: {tg_file_id}')
        return
    elif tg_file_id.startswith('AgAC'):
        await update.message.reply_photo(tg_file_id, caption=f'文件tg_file_id: {tg_file_id}')
        return
    with SessionLocal() as session:
        file = session.query(File).filter_by(tg_file_id=tg_file_id).first()
        if not file:
            await update.message.reply_text('未找到该文件。')
            return
        file_path = file.file_path
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
        with SessionLocal() as session:
            file = session.query(File).filter_by(file_id=file_id).first()
            tg_file_id = file.tg_file_id if file else ''
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
        except Exception as e:
            if 'Message is not modified' in str(e):
                pass
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
        # 检查用户权限
        user_id = update.effective_user.id
        vip_level = get_user_vip_level(user_id)
        if vip_level < 1:
            if update.message:
                await update.message.reply_text('只有VIP1及以上用户才能使用此功能。')
            elif update.callback_query:
                await update.callback_query.answer('只有VIP1及以上用户才能使用此功能。', show_alert=True)
            return
            
        # 只解析 file_id
        try:
            parts = start_param.split('_')
            file_id = int(parts[1])
        except Exception:
            await update.message.reply_text('参数错误。')
            return
        with SessionLocal() as session:
            file = session.query(File).filter_by(file_id=file_id).first()
        if not file:
            await update.message.reply_text('文件不存在。')
            return
        tg_file_id, file_path = file.tg_file_id, file.file_path
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
                        input_file = InputFile(f, read_file_handle=False)
                        msg = await update.message.reply_document(input_file, caption='本地文件直传', timeout=120)
                        #msg = await update.message.reply_document(f, caption='本地文件直传')
                        new_file_id = msg.document.file_id
                else:
                    await update.message.reply_text('文件丢失。')
                    return
                # 关键：本地直传后写入tg_file_id
                if new_file_id:
                    with SessionLocal() as session:
                        file = session.query(File).filter_by(file_id=file_id).first()
                        if file:
                            file.tg_file_id = new_file_id
                            session.commit()
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
    app.add_handler(CallbackQueryHandler(hot_callback, pattern=r'^hotpage\|'))
    app.add_handler(CallbackQueryHandler(ss_callback, pattern=r'^sspage\|'))
    app.run_polling()

if __name__ == '__main__':
    main()
