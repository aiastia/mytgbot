import os
import random
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, CallbackQueryHandler, MessageHandler, filters
from dotenv import load_dotenv
from search_file import search_command, search_callback, ss_command, set_bot_username
from search_file import ss_callback
from orm_utils import SessionLocal, init_db
from orm_models import User, File, SentFile, FileFeedback, UploadedDocument
from db_migrate import migrate_db  # 导入数据库迁移函数
from document_handler import handle_document, handle_document_callback, batch_approve_command
from telegram.request import HTTPXRequest
from points_system import checkin_command, points_command, exchange_callback, cancel_callback  # 添加导入
from license_handler import redeem_command  # 添加导入
import logging
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.engine import Engine
import time

# 配置 SQL 查询日志
logging.basicConfig()
logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)

# 添加查询计时器
@event.listens_for(Engine, "before_cursor_execute")
def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    conn.info.setdefault('query_start_time', []).append(time.time())

@event.listens_for(Engine, "after_cursor_execute")
def after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    total = time.time() - conn.info['query_start_time'].pop(-1)
    print(f"执行 SQL 查询: {statement}")
    print(f"参数: {parameters}")
    print(f"耗时: {total:.3f} 秒")
    print("-" * 50)

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
    """获取或创建文件记录，返回文件ID"""
    with SessionLocal() as session:
        # 首先检查是否是上传的文档
        uploaded_doc = session.query(UploadedDocument).filter_by(download_path=file_path).first()
        if uploaded_doc:
            # 如果文件已经存在于 File 表中，更新 tg_file_id
            file = session.query(File).filter_by(file_path=file_path).first()
            if file:
                if tg_file_id and tg_file_id != file.tg_file_id:
                    file.tg_file_id = tg_file_id
                    session.commit()
                return file.file_id
            # 如果文件不存在于 File 表中，创建新记录
            file_size = os.path.getsize(file_path)
            new_file = File(
                file_path=file_path,
                tg_file_id=uploaded_doc.tg_file_id or tg_file_id,
                file_size=file_size
            )
            session.add(new_file)
            session.commit()
            return new_file.file_id

        # 处理普通文件
        file = session.query(File).filter_by(file_path=file_path).first()
        if file:
            if tg_file_id and tg_file_id != file.tg_file_id:
                file.tg_file_id = tg_file_id
                session.commit()
            return file.file_id
            
        # 创建新文件记录
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

def set_user_vip_level(user_id, vip_level, days=30):
    with SessionLocal() as session:
        user = session.query(User).filter_by(user_id=user_id).first()
        if user:
            now = datetime.now()
            if vip_level > 0:
                # 如果是首次成为VIP，设置vip_date
                if not user.vip_date:
                    user.vip_date = now.strftime('%Y-%m-%d')
                user.vip_level = vip_level
                # 只有在没有过期时间或过期时间小于30天时才设置新的过期时间
                if not user.vip_expiry_date:
                    user.vip_expiry_date = (now + timedelta(days=days)).strftime('%Y-%m-%d')
                else:
                    expiry_date = datetime.strptime(user.vip_expiry_date, '%Y-%m-%d')
                    if (expiry_date - now).days < 30:
                        user.vip_expiry_date = (now + timedelta(days=days)).strftime('%Y-%m-%d')
            else:
                user.vip_level = 0
                user.vip_expiry_date = None
                # 不清除vip_date，保留首次成为VIP的记录
            session.commit()

def get_user_vip_level(user_id):
    with SessionLocal() as session:
        user = session.query(User).filter_by(user_id=user_id).first()
        if not user or not user.vip_level:
            return 0, 10  # 返回等级和每日限制
        
        # 检查VIP是否过期
        if user.vip_expiry_date:
            expiry_date = datetime.strptime(user.vip_expiry_date, '%Y-%m-%d')
            if datetime.now().date() > expiry_date.date():
                # VIP已过期，重置等级
                user.vip_level = 0
                session.commit()
                return 0, 10  # 返回等级和每日限制
        
        # 根据等级返回每日限制
        if user.vip_level == 3:
            return user.vip_level, 100
        elif user.vip_level == 2:
            return user.vip_level, 50
        elif user.vip_level == 1:
            return user.vip_level, 30
        else:
            return user.vip_level, 10

def get_sent_file_ids(user_id):
    with SessionLocal() as session:
        ids = [row.file_id for row in session.query(SentFile.file_id).filter_by(user_id=user_id).all()]
    return ids

def mark_file_sent(user_id, file_id, source='file'):
    """记录文件发送历史，使用 merge 避免重复记录"""
    with SessionLocal() as session:
        date = datetime.now().strftime('%Y-%m-%d')
        session.merge(SentFile(user_id=user_id, file_id=file_id, date=date, source=source))
        session.commit()

def get_today_sent_count(user_id):
    """获取用户今日已发送文件数量，使用 count 优化查询"""
    with SessionLocal() as session:
        today = datetime.now().strftime('%Y-%m-%d')
        count = session.query(SentFile).filter_by(
            user_id=user_id, 
            date=today
        ).count()
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

# 此函数已被 get_unsent_files 中的直接查询替代，保留注释以供参考
# def get_all_txt_files():
#     with SessionLocal() as session:
#         files = [row.file_path for row in session.query(File.file_path).all()]
#     return files

# 记录反馈
def record_feedback(user_id, file_id, feedback):
    with SessionLocal() as session:
        date = datetime.now().strftime('%Y-%m-%d')
        session.merge(FileFeedback(user_id=user_id, file_id=file_id, feedback=feedback, date=date))
        session.commit()

def get_unsent_files(user_id):
    """获取未发送的文件
    返回格式: {'id': file_id, 'source': 'file'/'uploaded', 'tg_file_id': '...'} 或 {'id': file_id, 'source': 'file'/'uploaded', 'file_path': '...'}
    """
    with SessionLocal() as session:
        # 获取所有文件ID
        file_ids = {row.file_id for row in session.query(File.file_id).all()}
        uploaded_ids = {doc.id for doc in session.query(UploadedDocument).filter_by(status='approved').all()}
        
        # 获取已发送的文件ID
        sent_records = session.query(SentFile).filter_by(user_id=user_id).all()
        sent_file_ids = {record.file_id for record in sent_records if record.source == 'file'}
        sent_uploaded_ids = {record.file_id for record in sent_records if record.source == 'uploaded'}
        
        # 获取未发送的文件ID
        unsent_file_ids = list(file_ids - sent_file_ids)
        unsent_uploaded_ids = list(uploaded_ids - sent_uploaded_ids)
        
        # 如果两个列表都为空，返回None
        if not unsent_file_ids and not unsent_uploaded_ids:
            return None
            
        # 随机选择一个未发送的文件ID
        if unsent_file_ids and unsent_uploaded_ids:
            # 如果两个列表都有内容，随机选择一个列表
            if random.random() < 0.7:  # 70%概率选择普通文件
                file_id = random.choice(unsent_file_ids)
                source = 'file'
            else:
                file_id = random.choice(unsent_uploaded_ids)
                source = 'uploaded'
        elif unsent_file_ids:
            file_id = random.choice(unsent_file_ids)
            source = 'file'
        else:
            file_id = random.choice(unsent_uploaded_ids)
            source = 'uploaded'
        
        # 根据source和file_id获取文件信息
        if source == 'file':
            file = session.query(File).filter_by(file_id=file_id).first()
            if file:
                if file.tg_file_id:
                    return {'id': file_id, 'source': source, 'tg_file_id': file.tg_file_id}
                elif file.file_path and os.path.exists(file.file_path):
                    return {'id': file_id, 'source': source, 'file_path': file.file_path}
        else:
            doc = session.query(UploadedDocument).filter_by(id=file_id).first()
            if doc:
                if doc.tg_file_id:
                    return {'id': file_id, 'source': source, 'tg_file_id': doc.tg_file_id}
                elif doc.download_path and os.path.exists(doc.download_path):
                    return {'id': file_id, 'source': source, 'file_path': doc.download_path}
        
        return None

async def send_file_job(context: ContextTypes.DEFAULT_TYPE):
    """异步任务：发送文件"""
    job_data = context.job.data
    chat_id = job_data['chat_id']
    file_id_or_path = job_data['file_id_or_path']
    user_id = job_data['user_id']
    prep_message_id = job_data['prep_message_id']
    source = job_data.get('source', 'file')  # 默认为 'file'
    
    try:
        # 检查是否是 tg_file_id
        if file_id_or_path.startswith(('BQAC', 'CAAC', 'HDAA', 'BAAC', 'AgAC')):
            # 根据文件ID前缀选择发送方法
            try:
                if file_id_or_path.startswith(('BQAC', 'CAAC', 'HDAA')):
                    msg = await context.bot.send_document(
                        chat_id=chat_id,
                        document=file_id_or_path,
                        caption=f"file id: `{file_id_or_path}`",
                        parse_mode='Markdown'
                    )
                elif file_id_or_path.startswith('BAAC'):
                    msg = await context.bot.send_video(
                        chat_id=chat_id,
                        video=file_id_or_path,
                        caption=f"file id: `{file_id_or_path}`",
                        parse_mode='Markdown'
                    )
                elif file_id_or_path.startswith('AgAC'):
                    msg = await context.bot.send_photo(
                        chat_id=chat_id,
                        photo=file_id_or_path,
                        caption=f"file id: `{file_id_or_path}`",
                        parse_mode='Markdown'
                    )
                
                # 记录发送
                with SessionLocal() as session:
                    if source == 'file':
                        file = session.query(File).filter_by(tg_file_id=file_id_or_path).first()
                        if file:
                            mark_file_sent(user_id, file.file_id, source='file')
                    else:
                        uploaded_doc = session.query(UploadedDocument).filter_by(tg_file_id=file_id_or_path).first()
                        if uploaded_doc:
                            mark_file_sent(user_id, uploaded_doc.id, source='uploaded')
            except Exception as e:
                await context.bot.send_message(chat_id=chat_id, text=f'发送文件失败: {str(e)}')
                return
        else:
            # 处理本地文件
            file_path = file_id_or_path
            ext = os.path.splitext(file_path)[1].lower()
            
            # 根据文件扩展名选择发送方法
            try:
                with open(file_path, 'rb') as f:
                    if ext == '.mp4':
                        msg = await context.bot.send_video(
                            chat_id=chat_id,
                            video=f,
                            caption="正在生成文件ID..."
                        )
                        tg_file_id = msg.video.file_id
                    elif ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']:
                        msg = await context.bot.send_photo(
                            chat_id=chat_id,
                            photo=f,
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
                        msg = await context.bot.send_document(
                            chat_id=chat_id,
                            document=f,
                            caption="正在生成文件ID...",
                            reply_markup=reply_markup
                        )
                        tg_file_id = msg.document.file_id
                
                # 使用 get_or_create_file 处理本地文件
                file_id = get_or_create_file(file_path, tg_file_id)
                mark_file_sent(user_id, file_id, source='file')
                
                # 更新消息
                try:
                    if ext == '.mp4' or ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']:
                        await msg.edit_caption(caption=f"file id: `{tg_file_id}`", parse_mode='Markdown')
                    else:
                        keyboard = [
                            [
                                InlineKeyboardButton("👍", callback_data=f"feedback|{file_id}|1"),
                                InlineKeyboardButton("👎", callback_data=f"feedback|{file_id}|-1"),
                            ]
                        ]
                        reply_markup = InlineKeyboardMarkup(keyboard)
                        await msg.edit_caption(
                            caption=f"file id: `{tg_file_id}`",
                            parse_mode='Markdown',
                            reply_markup=reply_markup
                        )
                except Exception:
                    pass
            except Exception as e:
                await context.bot.send_message(chat_id=chat_id, text=f'发送文件失败: {str(e)}')
                return
        
        # 删除准备消息
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=prep_message_id)
        except Exception:
            pass  # 如果删除失败，忽略错误
            
    except Exception as e:
        await context.bot.send_message(chat_id=chat_id, text=f'发送文件时出错：{str(e)}')
        # 发生错误时也尝试删除准备消息
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=prep_message_id)
        except Exception:
            pass

async def send_random_txt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    ensure_user(user_id)
    
    # 获取VIP等级和每日限制
    vip_level, daily_limit = get_user_vip_level(user_id)
    if get_today_sent_count(user_id) >= daily_limit:
        await update.message.reply_text(f'每天最多只能领取{daily_limit}本，明天再来吧！')
        return
    
    file_info = get_unsent_files(user_id)
    if not file_info:
        await update.message.reply_text('你已经收到了所有文件！')
        return
    
    # 发送准备消息
    prep_message = await update.message.reply_text('正在准备发送文件...')
    
    # 创建异步任务
    context.job_queue.run_once(
        send_file_job,
        when=1,  # 1秒后开始执行
        data={
            'chat_id': update.effective_chat.id,
            'file_id_or_path': file_info.get('tg_file_id') or file_info.get('file_path'),
            'user_id': user_id,
            'prep_message_id': prep_message.message_id,
            'source': file_info['source']
        }
    )

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
    
    # 直接使用 tg_file_id 发送文件，不需要查询数据库
    try:
        if tg_file_id.startswith('BQAC') or tg_file_id.startswith('CAAC') or tg_file_id.startswith('HDAA'):
            await update.message.reply_document(tg_file_id, caption=f'file id: `{tg_file_id}`')
        elif tg_file_id.startswith('BAAC'):
            await update.message.reply_video(tg_file_id, caption=f'file id: `{tg_file_id}`')
        elif tg_file_id.startswith('AgAC'):
            await update.message.reply_photo(tg_file_id, caption=f'file id: `{tg_file_id}`')
        else:
            await update.message.reply_text('无效的文件ID格式。')
    except Exception as e:
        await update.message.reply_text(f'发送文件失败: {str(e)}')

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
                caption=f"file id: `{tg_file_id}`",
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
    if len(context.args) != 3:
        await update.message.reply_text('用法：/setvip <user_id> <0/1/2/3> <天数>')
        return
    try:
        target_id = int(context.args[0])
        vip_level = int(context.args[1])
        days = int(context.args[2])
        if vip_level not in (0, 1, 2, 3):
            raise ValueError
        if days <= 0:
            raise ValueError
    except Exception:
        await update.message.reply_text('参数错误。')
        return
    
    # 获取用户当前VIP信息
    with SessionLocal() as session:
        user = session.query(User).filter_by(user_id=target_id).first()
        if not user:
            await update.message.reply_text('用户不存在。')
            return
        
        now = datetime.now()
        new_expiry_date = (now + timedelta(days=days)).strftime('%Y-%m-%d')
        
        if vip_level > 0:
            # 如果是首次成为VIP，设置vip_date
            if not user.vip_date:
                user.vip_date = now.strftime('%Y-%m-%d')
            
            # 检查当前VIP状态
            if user.vip_level > 0 and user.vip_expiry_date:
                current_expiry = datetime.strptime(user.vip_expiry_date, '%Y-%m-%d')
                new_expiry = datetime.strptime(new_expiry_date, '%Y-%m-%d')
                
                # 如果当前到期时间小于新设置的天数，使用新设置的天数
                if current_expiry < new_expiry:
                    user.vip_expiry_date = new_expiry_date
                    await update.message.reply_text(f'用户 {target_id} VIP等级已设置为 {vip_level}，有效期更新为 {days} 天')
                else:
                    # 保持原到期时间不变
                    await update.message.reply_text(f'用户 {target_id} VIP等级已设置为 {vip_level}，保持原到期时间不变')
            else:
                # 用户不是VIP，直接设置新的到期时间
                user.vip_expiry_date = new_expiry_date
                await update.message.reply_text(f'用户 {target_id} VIP等级已设置为 {vip_level}，有效期 {days} 天')
            
            user.vip_level = vip_level
        else:
            # 取消VIP
            user.vip_level = 0
            user.vip_expiry_date = None
            await update.message.reply_text(f'用户 {target_id} VIP状态已取消')
        
        session.commit()

# 新增命令：设置用户VIP等级
async def setviplevel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN_USER_ID:
        await update.message.reply_text('无权限，仅管理员可用。')
        return
    if len(context.args) != 2:
        await update.message.reply_text('用法：/setviplevel <user_id> <0/1/2/3>')
        return
    try:
        target_id = int(context.args[0])
        vip_level = int(context.args[1])
        if vip_level not in (0, 1, 2, 3):
            raise ValueError
    except Exception:
        await update.message.reply_text('参数错误。')
        return
    
    # 获取用户当前VIP信息
    with SessionLocal() as session:
        user = session.query(User).filter_by(user_id=target_id).first()
        if not user:
            await update.message.reply_text('用户不存在。')
            return
        
        # 如果用户当前是VIP且未过期，检查剩余天数
        if user.vip_level > 0 and user.vip_expiry_date:
            expiry_date = datetime.strptime(user.vip_expiry_date, '%Y-%m-%d')
            remaining_days = (expiry_date - datetime.now()).days
            if remaining_days >= 30:
                # 如果剩余天数大于等于30天，只更新等级
                user.vip_level = vip_level
                session.commit()
                await update.message.reply_text(f'用户 {target_id} VIP等级已更新为 {vip_level}，过期时间保持不变')
                return
    
    # 如果用户不是VIP或剩余天数小于30天，使用默认的set_user_vip_level函数
    set_user_vip_level(target_id, vip_level)
    await update.message.reply_text(f'用户 {target_id} VIP等级已设置为 {vip_level}')

async def on_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args and update.message:
        # 显示欢迎信息
        welcome_text = """👋 欢迎使用文件分享机器人！

🤖 这是一个文件分享机器人，你可以：
• 搜索和获取文件
• 每日签到获取积分
• 使用积分兑换VIP

📚 发送 /help 查看完整使用指南
🎯 发送 /checkin 进行每日签到
🔍 发送 /search 搜索文件

如有问题，请联系管理员。"""
        await update.message.reply_text(welcome_text)
        return

    # 处理 deep link 参数
    if update.message:
        start_param = update.message.text.split(' ', 1)[1] if ' ' in update.message.text else ''
    elif update.callback_query:
        start_param = update.callback_query.data.split(' ', 1)[1] if ' ' in update.callback_query.data else ''
    else:
        start_param = ''
    
    if start_param.startswith('upload_'):
        # 处理上传文档
        try:
            doc_id = int(start_param.split('_')[1])
            with SessionLocal() as session:
                doc = session.query(UploadedDocument).filter_by(id=doc_id).first()
                if doc and doc.tg_file_id:
                    # 先发送文件信息
                    info_text = f"""📄 文件信息：
• 文件名：{doc.file_name}
• 上传时间：{doc.upload_time}
• 文件大小：{doc.file_size} bytes

正在发送文件..."""
                    await update.message.reply_text(info_text)
                    # 然后发送文件
                    await update.message.reply_document(doc.tg_file_id)
                    mark_file_sent(update.effective_user.id, doc_id, source='uploaded')
                else:
                    await update.message.reply_text('文件不存在或已被删除。')
        except Exception as e:
            await update.message.reply_text(f'获取文件失败: {str(e)}')
    elif start_param.startswith('file_'):
        # 处理普通文件
        try:
            file_id = int(start_param.split('_')[1])
            with SessionLocal() as session:
                file = session.query(File).filter_by(file_id=file_id).first()
                if file:
                    if file.tg_file_id:
                        # 如果有 tg_file_id，直接发送带说明的文件
                        caption = f"file id: `{file.tg_file_id}`"
                        await update.message.reply_document(file.tg_file_id, caption=caption, parse_mode='Markdown')
                    elif file.file_path and os.path.exists(file.file_path):
                        # 如果是本地文件，先发送带临时说明的文件
                        with open(file.file_path, 'rb') as f:
                            msg = await update.message.reply_document(
                                f,
                                caption="正在生成文件ID..."
                            )
                            # 获取新生成的 tg_file_id
                            if msg.document:
                                tg_file_id = msg.document.file_id
                                # 更新数据库中的 tg_file_id
                                file.tg_file_id = tg_file_id
                                session.commit()
                                # 更新消息说明
                                await msg.edit_caption(caption=f"file id: `{tg_file_id}`", parse_mode='Markdown')
                    else:
                        await update.message.reply_text('文件不存在或已被删除。')
                    mark_file_sent(update.effective_user.id, file_id, source='file')
                else:
                    await update.message.reply_text('文件不存在或已被删除。')
        except Exception as e:
            await update.message.reply_text(f'获取文件失败: {str(e)}')

async def user_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    ensure_user(user_id)
    
    with SessionLocal() as session:
        user = session.query(User).filter_by(user_id=user_id).first()
        if not user:
            await update.message.reply_text('用户信息不存在。')
            return
            
        # 获取用户VIP信息
        vip_level, daily_limit = get_user_vip_level(user_id)
        vip_date = user.vip_date
        vip_expiry_date = user.vip_expiry_date
        
        # 检查VIP是否有效
        is_vip_active = False
        if vip_expiry_date:
            expiry_date = datetime.strptime(vip_expiry_date, '%Y-%m-%d')
            is_vip_active = datetime.now().date() <= expiry_date.date()
        
        # 获取今日已接收文件数
        today_count = get_today_sent_count(user_id)
        
        # 获取总接收文件数
        total_files = len(get_sent_file_ids(user_id))
        
        # 构建消息
        msg = f'📊 <b>用户统计信息</b>\n\n'
        msg += f'👤 用户ID: <code>{user_id}</code>\n'
        msg += f'⭐ VIP等级: {vip_level}\n'
        msg += f'📊 VIP状态: {"有效" if is_vip_active else "已过期"}\n'
        if vip_date:
            msg += f'📅 VIP开始日期: {vip_date}\n'
        if vip_expiry_date:
            msg += f'⏰ VIP过期日期: {vip_expiry_date}\n'
        msg += f'📚 今日已接收: {today_count}/{daily_limit}\n'
        msg += f'📦 总接收文件: {total_files}\n'
        msg += f'🎯 当前积分: {user.points}\n'
        
        await update.message.reply_text(msg, parse_mode='HTML')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """🤖 <b>机器人使用指南</b>

<b>基础命令：</b>
/start - 开始使用机器人
/help - 显示此帮助信息
/user - 查看个人统计信息
/stats - 查看已接收文件数量

<b>文件相关：</b>
/random - 随机获取一个文件
/search - 搜索文件
/s - 搜索文件（快捷命令）
/getfile - 通过文件ID获取文件
/hot - 查看热门文件排行榜

<b>VIP系统：</b>
/checkin - 每日签到获取积分
/points - 查看积分和兑换VIP
/ss - 高级搜索（仅VIP可用）
/redeem - 兑换积分码

<b>VIP等级说明：</b>
VIP0 - 每日限制10个文件
VIP1 - 每日限制30个文件
VIP2 - 每日限制50个文件
VIP3 - 每日限制100个文件

<b>管理员命令：</b>
/reload - 重新加载文件列表
/setvip - 设置用户VIP状态
/setviplevel - 设置用户VIP等级
/batchapprove - 批量批准上传的文件
<b>使用提示：</b>
• 每日签到可获得1-5积分
• 文件评分可帮助其他用户找到优质内容
• VIP等级越高，每日可获取的文件数量越多

如有问题，请联系管理员。"""

    # 创建购买积分的按钮
    keyboard = [
        [InlineKeyboardButton("💎 购买积分", url="https://t.me/iDataRiver_Bot?start=M_685017ebfaa790cf11d677bd")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(help_text, parse_mode='HTML', reply_markup=reply_markup)

def main():
    upgrade_users_table()  # 启动时自动升级users表结构
    base_url = os.getenv('TELEGRAM_API_URL')
    request = HTTPXRequest(
        connect_timeout=60,   # Connection timeout
        read_timeout=1810,    # Should be > TDLIB_UPLOAD_FILE_TIMEOUT
        write_timeout=1810,   # Should be > TDLIB_UPLOAD_FILE_TIMEOUT
        pool_timeout=60,       # Pool timeout
        media_write_timeout=1810
    )
    builder = ApplicationBuilder().token(TOKEN).request(request)
    if base_url:
        builder.base_url(f"{base_url}/bot")
        builder.base_file_url(f"{base_url}/file/bot")
        # builder.local_mode(True)
    application = builder.build()
    
    # 设置管理员ID列表
    application.bot_data['admin_ids'] = ADMIN_USER_ID
    
    # 注册命令处理器
    application.add_handler(CommandHandler("start", on_start))
    application.add_handler(CommandHandler("help", help_command))  # 添加帮助命令
    application.add_handler(CommandHandler("search", search_command))
    application.add_handler(CommandHandler("ss", ss_command))
    application.add_handler(CommandHandler('s', search_command))
    application.add_handler(CommandHandler("getfile", getfile))
    application.add_handler(CommandHandler("reload", reload_command))
    application.add_handler(CommandHandler("setvip", setvip_command))
    application.add_handler(CommandHandler("setviplevel", setviplevel_command))
    application.add_handler(CommandHandler('random', send_random_txt))
    application.add_handler(CommandHandler('stats', stats))
    application.add_handler(CommandHandler('hot', hot))

    application.add_handler(CommandHandler('user', user_stats))  # 添加用户统计命令
    application.add_handler(CommandHandler('checkin', checkin_command))  # 添加签到命令
    application.add_handler(CommandHandler('points', points_command))    # 添加积分命令
    application.add_handler(CommandHandler('redeem', redeem_command))    # 添加兑换码命令
    application.add_handler(CommandHandler('batchapprove', batch_approve_command))  # 添加批量批准命令
    
    # 注册回调处理器
    application.add_handler(CallbackQueryHandler(search_callback, pattern=r'^(spage\||upload_)'))
    application.add_handler(CallbackQueryHandler(ss_callback, pattern=r'^sspage\|'))
    application.add_handler(CallbackQueryHandler(feedback_callback, pattern=r'^feedback\|'))
    application.add_handler(CallbackQueryHandler(hot_callback, pattern=r'^hotpage\|'))
    application.add_handler(CallbackQueryHandler(handle_document_callback, pattern="^doc_"))
    application.add_handler(CallbackQueryHandler(exchange_callback, pattern="^exchange\|"))  # 修改为匹配 exchange| 格式
    application.add_handler(CallbackQueryHandler(cancel_callback, pattern="^cancel$"))
    
    # 注册文档处理器
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    
    # 设置机器人用户名
    async def set_username(app):
        me = await app.bot.get_me()
        set_bot_username(me.username)
    application.post_init = set_username
    
    # 启动机器人
    application.run_polling()

if __name__ == '__main__':
    main()
