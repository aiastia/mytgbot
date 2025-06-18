import os
import logging
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from telegram.request import HTTPXRequest
from telegram.error import TelegramError, NetworkError
from telegram import Update
from config import TOKEN, TELEGRAM_API_URL, CONNECT_TIMEOUT, READ_TIMEOUT, WRITE_TIMEOUT, POOL_TIMEOUT, MEDIA_WRITE_TIMEOUT
from utils.db import upgrade_users_table
from handlers.start import on_start
from handlers.search import search_callback, search_command, ss_command, ss_callback, set_bot_username
from handlers.random import send_random_txt
from handlers.feedback import feedback_callback
from handlers.help import help_command
from handlers.stats import stats
from handlers.getfile import getfile
from handlers.reload import reload_command
from handlers.vip import setvip_command, setviplevel_command
from handlers.document import handle_document, handle_document_callback, batch_approve_command
from handlers.points import checkin_command, points_command, exchange_callback, cancel_callback
from handlers.license import redeem_command
from handlers.hot import hot, hot_callback

# 配置日志
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def main():
    """主函数"""
    # 升级数据库结构
    upgrade_users_table()  # 启动时自动升级users表结构
    
    # 检查必要的配置
    if not TOKEN:
        logger.error("BOT_TOKEN 未设置！请在 .env 文件中设置 BOT_TOKEN")
        return
    
    if not TELEGRAM_API_URL:
        logger.error("TELEGRAM_API_URL 未设置！请在 .env 文件中设置 TELEGRAM_API_URL")
        return
    
    # 配置请求参数
    request = HTTPXRequest(
        connect_timeout=CONNECT_TIMEOUT,   # Connection timeout
        read_timeout=READ_TIMEOUT,    # Should be > TDLIB_UPLOAD_FILE_TIMEOUT
        write_timeout=WRITE_TIMEOUT,   # Should be > TDLIB_UPLOAD_FILE_TIMEOUT
        pool_timeout=POOL_TIMEOUT,       # Pool timeout
        media_write_timeout=MEDIA_WRITE_TIMEOUT
    )
    
    # 创建应用
    try:
        builder = Application.builder().token(TOKEN).request(request)
        print(f"Using TELEGRAM_API_URL: {TELEGRAM_API_URL}")
        if TELEGRAM_API_URL:
            builder.base_url(f"{TELEGRAM_API_URL}/bot")
            builder.base_file_url(f"{TELEGRAM_API_URL}/file/bot")
        
        application = builder.build()
        
        # 添加处理器
        application.add_handler(CommandHandler("start", on_start))
        application.add_handler(CommandHandler("help", help_command))
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
        application.add_handler(CommandHandler('checkin', checkin_command))
        application.add_handler(CommandHandler('points', points_command))
        application.add_handler(CommandHandler('redeem', redeem_command))
        application.add_handler(CommandHandler('batchapprove', batch_approve_command))

        # 注册回调处理器
        application.add_handler(CallbackQueryHandler(search_callback, pattern=r'^(spage\||upload_)'))
        application.add_handler(CallbackQueryHandler(ss_callback, pattern=r'^sspage\|'))
        application.add_handler(CallbackQueryHandler(feedback_callback, pattern=r'^feedback\|'))
        application.add_handler(CallbackQueryHandler(hot_callback, pattern=r'^hotpage\|'))
        application.add_handler(CallbackQueryHandler(handle_document_callback, pattern="^doc_"))
        application.add_handler(CallbackQueryHandler(exchange_callback, pattern="^exchange\|"))
        application.add_handler(CallbackQueryHandler(cancel_callback, pattern="^cancel$"))
        
        # 注册文档处理器
        application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
        
        # 设置机器人用户名
        async def set_username(app):
            try:
                me = await app.bot.get_me()
                set_bot_username(me.username)
                logger.info(f"Bot username set to: {me.username}")
            except Exception as e:
                logger.error(f"Failed to set bot username: {e}")
        application.post_init = set_username
        
        # 添加错误处理器
        async def error_handler(update, context):
            logger.error(f"Update {update} caused error {context.error}")
            if isinstance(context.error, NetworkError):
                logger.error("Network error occurred, retrying...")
            elif isinstance(context.error, TelegramError):
                logger.error(f"Telegram error: {context.error}")
            else:
                logger.error(f"Unexpected error: {context.error}")
        
        application.add_error_handler(error_handler)
        
        # 启动机器人
        logger.info("Starting bot...")
        application.run_polling(allowed_updates=Update.ALL_TYPES)
        
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")
        raise

if __name__ == '__main__':
    main()
