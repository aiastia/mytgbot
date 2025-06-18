from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from services.user_service import ensure_user, get_sent_file_ids, get_user_vip_level
from services.file_service import mark_file_sent
from utils.db import SessionLocal, File, UploadedDocument
from config import ADMIN_IDS

# 全局变量存储机器人用户名
BOT_USERNAME = None

def set_bot_username(username):
    """设置机器人用户名"""
    global BOT_USERNAME
    BOT_USERNAME = username

async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理搜索命令"""
    user_id = update.effective_user.id
    ensure_user(user_id)
    
    # 检查用户VIP等级
    vip_level = get_user_vip_level(user_id)
    if vip_level < 1 and user_id not in ADMIN_IDS:
        await update.message.reply_text("您需要VIP1才能使用此功能！")
        return
    
    # 检查用户今日发送数量
    count = get_sent_file_ids(user_id)
    if count >= 5:
        await update.message.reply_text("您今日已发送5个文件，请明天再来！")
        return
    
    # 获取搜索关键词
    if not context.args:
        await update.message.reply_text("请提供搜索关键词！")
        return
    
    keyword = ' '.join(context.args)
    
    # 搜索文件
    session = SessionLocal()
    files = session.query(File).filter(File.file_name.ilike(f'%{keyword}%')).all()
    uploaded_docs = session.query(UploadedDocument).filter(UploadedDocument.file_name.ilike(f'%{keyword}%')).all()
    
    if not files and not uploaded_docs:
        await update.message.reply_text("未找到相关文件！")
        return
    
    # 构建回复消息
    message = "搜索结果：\n\n"
    keyboard = []
    
    # 添加文件结果
    for file in files:
        message += f"📄 {file.file_name}\n"
        keyboard.append([InlineKeyboardButton(
            f"📄 {file.file_name}",
            callback_data=f"spage|{file.file_id}_file"
        )])
    
    # 添加上传文件结果
    for doc in uploaded_docs:
        message += f"📤 {doc.file_name}\n"
        keyboard.append([InlineKeyboardButton(
            f"📤 {doc.file_name}",
            callback_data=f"spage|{doc.id}_uploaded"
        )])
    
    # 发送消息
    await update.message.reply_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def ss_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理ss命令"""
    user_id = update.effective_user.id
    ensure_user(user_id)
    
    # 检查用户VIP等级
    vip_level = get_user_vip_level(user_id)
    if vip_level < 1 and user_id not in ADMIN_IDS:
        await update.message.reply_text("您需要VIP1才能使用此功能！")
        return
    
    # 检查用户今日发送数量
    count = get_sent_file_ids(user_id)
    if count >= 5:
        await update.message.reply_text("您今日已发送5个文件，请明天再来！")
        return
    
    # 获取搜索关键词
    if not context.args:
        await update.message.reply_text("请提供搜索关键词！")
        return
    
    keyword = ' '.join(context.args)
    
    # 搜索文件
    session = SessionLocal()
    files = session.query(File).filter(File.file_name.ilike(f'%{keyword}%')).all()
    
    if not files:
        await update.message.reply_text("未找到相关文件！")
        return
    
    # 构建回复消息
    message = "搜索结果：\n\n"
    keyboard = []
    
    # 添加文件结果
    for file in files:
        message += f"📄 {file.file_name}\n"
        keyboard.append([InlineKeyboardButton(
            f"📄 {file.file_name}",
            callback_data=f"sspage|{file.file_id}"
        )])
    
    # 发送消息
    await update.message.reply_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def ss_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理ss回调"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    ensure_user(user_id)
    
    # 检查用户VIP等级
    vip_level = get_user_vip_level(user_id)
    if vip_level < 1 and user_id not in ADMIN_IDS:
        await query.message.reply_text("您需要VIP1才能使用此功能！")
        return
    
    # 检查用户今日发送数量
    count = get_sent_file_ids(user_id)
    if count >= 5:
        await query.message.reply_text("您今日已发送5个文件，请明天再来！")
        return
    
    # 获取文件信息
    file_id = int(query.data.split('|')[1])
    
    file = SessionLocal().query(File).filter_by(file_id=file_id).first()
    if not file:
        await query.message.reply_text("文件不存在！")
        return
    
    if file.tg_file_id:
        await query.message.reply_document(
            document=file.tg_file_id,
            caption=f"file id: `{file.tg_file_id}`",
            parse_mode='Markdown'
        )
    else:
        with open(file.file_path, 'rb') as f:
            message = await query.message.reply_document(
                document=f,
                caption="正在生成文件ID..."
            )
            # 获取文件ID并更新数据库
            file_id = message.document.file_id
            mark_file_sent(user_id, file.file_id, 'file')
            # 更新消息
            await message.edit_caption(
                caption=f"file id: `{file_id}`",
                parse_mode='Markdown'
            )

async def search_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理搜索回调"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    ensure_user(user_id)
    
    # 检查用户VIP等级
    vip_level = get_user_vip_level(user_id)
    if vip_level < 1 and user_id not in ADMIN_IDS:
        await query.message.reply_text("您需要VIP1才能使用此功能！")
        return
    
    # 检查用户今日发送数量
    count = get_sent_file_ids(user_id)
    if count >= 5:
        await query.message.reply_text("您今日已发送5个文件，请明天再来！")
        return
    
    # 获取文件信息
    file_id = int(query.data.split('_')[1])
    source = query.data.split('_')[2]
    
    if source == 'file':
        file = SessionLocal().query(File).filter_by(file_id=file_id).first()
        if not file:
            await query.message.reply_text("文件不存在！")
            return
        
        if file.tg_file_id:
            await query.message.reply_document(
                document=file.tg_file_id,
                caption=f"file id: `{file.tg_file_id}`",
                parse_mode='Markdown'
            )
        else:
            with open(file.file_path, 'rb') as f:
                message = await query.message.reply_document(
                    document=f,
                    caption="正在生成文件ID..."
                )
                # 获取文件ID并更新数据库
                file_id = message.document.file_id
                mark_file_sent(user_id, file.file_id, 'file')
                # 更新消息
                await message.edit_caption(
                    caption=f"file id: `{file_id}`",
                    parse_mode='Markdown'
                )
    else:
        doc = SessionLocal().query(UploadedDocument).filter_by(id=file_id).first()
        if not doc:
            await query.message.reply_text("文件不存在！")
            return
        
        if doc.tg_file_id:
            await query.message.reply_document(
                document=doc.tg_file_id,
                caption=f"file id: `{doc.tg_file_id}`",
                parse_mode='Markdown'
            )
        else:
            with open(doc.download_path, 'rb') as f:
                message = await query.message.reply_document(
                    document=f,
                    caption="正在生成文件ID..."
                )
                # 获取文件ID并更新数据库
                file_id = message.document.file_id
                mark_file_sent(user_id, doc.id, 'uploaded')
                # 更新消息
                await message.edit_caption(
                    caption=f"file id: `{file_id}`",
                    parse_mode='Markdown'
                ) 