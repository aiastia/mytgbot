from telegram import Update
from telegram.ext import ContextTypes
from services.user_service import ensure_user, get_sent_file_ids, get_user_vip_level
from services.file_service import get_unsent_files, mark_file_sent
from config import ADMIN_IDS

async def send_random_txt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """发送随机文件"""
    user_id = update.effective_user.id
    message = update.effective_message
    ensure_user(user_id)
    
    # 检查用户VIP等级
    vip_level = get_user_vip_level(user_id)
    if vip_level < 1 and user_id not in ADMIN_IDS:
        await message.reply_text("您需要VIP1才能使用此功能！")
        return
    
    # 检查用户今日发送数量
    count = get_sent_file_ids(user_id)
    if count >= 5:
        await message.reply_text("您今日已发送5个文件，请明天再来！")
        return
    
    # 获取未发送的文件
    file_info = get_unsent_files(user_id)
    if not file_info:
        await message.reply_text("没有可用的文件了！")
        return
    
    # 发送文件
    if 'tg_file_id' in file_info:
        # 如果文件已经在Telegram中，直接发送
        if file_info['source'] == 'file':
            await message.reply_document(
                document=file_info['tg_file_id'],
                caption=f"file id: `{file_info['tg_file_id']}`",
                parse_mode='Markdown'
            )
        else:
            await message.reply_document(
                document=file_info['tg_file_id'],
                caption=f"file id: `{file_info['tg_file_id']}`",
                parse_mode='Markdown'
            )
    else:
        # 如果是本地文件，需要先上传
        if file_info['source'] == 'file':
            with open(file_info['file_path'], 'rb') as f:
                sent_message = await message.reply_document(
                    document=f,
                    caption="正在生成文件ID..."
                )
                # 获取文件ID并更新数据库
                file_id = sent_message.document.file_id
                mark_file_sent(user_id, file_info['id'], 'file')
                # 更新消息
                await sent_message.edit_caption(
                    caption=f"file id: `{file_id}`",
                    parse_mode='Markdown'
                )
        else:
            with open(file_info['file_path'], 'rb') as f:
                sent_message = await message.reply_document(
                    document=f,
                    caption="正在生成文件ID..."
                )
                # 获取文件ID并更新数据库
                file_id = sent_message.document.file_id
                mark_file_sent(user_id, file_info['id'], 'uploaded')
                # 更新消息
                await sent_message.edit_caption(
                    caption=f"file id: `{file_id}`",
                    parse_mode='Markdown'
                ) 