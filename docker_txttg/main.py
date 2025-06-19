import os
import random
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, CallbackQueryHandler, MessageHandler, filters
from dotenv import load_dotenv
from modules.db.orm_utils import SessionLocal, init_db
from modules.db.orm_models import User, File, SentFile, FileFeedback, UploadedDocument
from modules.db.db_utils import *
from modules.core.document_handler import handle_document, handle_document_callback, batch_approve_command
from modules.core.points_system import checkin_command, points_command, exchange_callback, cancel_callback
from modules.core.license_handler import redeem_command
from modules.core.search_file import search_command, search_callback, ss_command, ss_callback, set_bot_username
from modules.core.file_utils import *
from modules.core.bot_tasks import send_file_job
from modules.handlers.handlers_user import user_stats, stats, on_start
from modules.handlers.handlers_file import send_random_txt, getfile, reload_command, hot, hot_callback, send_hot_page, feedback_callback
from modules.handlers.handlers_vip import setvip_command, setviplevel_command
from modules.handlers.handlers_help import help_command
from modules.db_migrate import migrate_db
from modules.config.config import ADMIN_USER_ID, TXT_ROOT, TXT_EXTS
from telegram.request import HTTPXRequest
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

# 只保留命令注册和主流程，所有 handler 通过 import 调用。
def main():
    # upgrade_users_table()  # 启动时自动升级users表结构
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
