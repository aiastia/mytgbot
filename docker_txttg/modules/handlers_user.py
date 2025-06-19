from docker_txttg.modules.db_utils import *
from docker_txttg.modules.file_utils import *
from orm_utils import SessionLocal
from orm_models import User, File, UploadedDocument
from telegram import Update
from telegram.ext import ContextTypes
from datetime import datetime
import os

async def user_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    ensure_user(user_id)
    with SessionLocal() as session:
        user = session.query(User).filter_by(user_id=user_id).first()
        if not user:
            await update.message.reply_text('用户信息不存在。')
            return
        vip_level, daily_limit = get_user_vip_level(user_id)
        vip_date = user.vip_date
        vip_expiry_date = user.vip_expiry_date
        is_vip_active = False
        if vip_expiry_date:
            expiry_date = datetime.strptime(vip_expiry_date, '%Y-%m-%d')
            is_vip_active = datetime.now().date() <= expiry_date.date()
        today_count = get_today_sent_count(user_id)
        total_files = get_sent_file_ids(user_id)
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

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    ensure_user(user_id)
    count = get_sent_file_ids(user_id)
    await update.message.reply_text(f'你已收到 {count} 个文件。')

async def on_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args and update.message:
        welcome_text = """👋 欢迎使用文件分享机器人！\n\n🤖 这是一个文件分享机器人，你可以：\n• 搜索和获取文件\n• 每日签到获取积分\n• 使用积分兑换VIP\n\n📚 发送 /help 查看完整使用指南\n🎯 发送 /checkin 进行每日签到\n🔍 发送 /search 搜索文件\n\n如有问题，请联系管理员。"""
        await update.message.reply_text(welcome_text)
        return
    if update.message:
        start_param = update.message.text.split(' ', 1)[1] if ' ' in update.message.text else ''
    elif update.callback_query:
        start_param = update.callback_query.data.split(' ', 1)[1] if ' ' in update.callback_query.data else ''
    else:
        start_param = ''
    if start_param.startswith('upload_'):
        try:
            doc_id = int(start_param.split('_')[1])
            with SessionLocal() as session:
                doc = session.query(UploadedDocument).filter_by(id=doc_id).first()
                if doc and doc.tg_file_id:
                    info_text = f"""📄 文件信息：\n• 文件名：{doc.file_name}\n• 上传时间：{doc.upload_time}\n• 文件大小：{doc.file_size} bytes\n\n正在发送文件..."""
                    await update.message.reply_text(info_text)
                    await update.message.reply_document(doc.tg_file_id)
                    mark_file_sent(update.effective_user.id, doc_id, source='uploaded')
                else:
                    await update.message.reply_text('文件不存在或已被删除。')
        except Exception as e:
            await update.message.reply_text(f'获取文件失败: {str(e)}')
    elif start_param.startswith('file_'):
        try:
            file_id = int(start_param.split('_')[1])
            with SessionLocal() as session:
                file = session.query(File).filter_by(file_id=file_id).first()
                if file:
                    if file.tg_file_id:
                        caption = f"file id: `{file.tg_file_id}`"
                        await update.message.reply_document(file.tg_file_id, caption=caption, parse_mode='Markdown')
                    elif file.file_path and os.path.exists(file.file_path):
                        with open(file.file_path, 'rb') as f:
                            msg = await update.message.reply_document(
                                f,
                                caption="正在生成文件ID..."
                            )
                            if msg.document:
                                tg_file_id = msg.document.file_id
                                file.tg_file_id = tg_file_id
                                session.commit()
                                await msg.edit_caption(caption=f"file id: `{tg_file_id}`", parse_mode='Markdown')
                    else:
                        await update.message.reply_text('文件不存在或已被删除。')
                    mark_file_sent(update.effective_user.id, file_id, source='file')
                else:
                    await update.message.reply_text('文件不存在或已被删除。')
        except Exception as e:
            await update.message.reply_text(f'获取文件失败: {str(e)}')
