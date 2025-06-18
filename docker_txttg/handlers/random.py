from services.user_service import ensure_user, get_sent_file_ids, get_user_vip_level
from services.file_service import get_unsent_files, mark_file_sent
from config import ADMIN_IDS
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from orm_utils import SessionLocal
from orm_models import File, UploadedDocument
from utils.calculations import get_today_sent_count

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