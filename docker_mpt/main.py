import os
import yaml
import logging
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.types import MessageMediaDocument, MessageMediaPhoto, MessageMediaWebPage
from db.base import init_db
from db.models import Message, Keyword, ForwardRule, Account
from sqlalchemy.orm import Session
from db.base import SessionLocal
import re
import asyncio
from telethon.errors import SessionPasswordNeededError
from datetime import datetime, timedelta
import time
from sqlalchemy.exc import IntegrityError
from sqlalchemy.sql import select

# Configure logging
logging.basicConfig(
    level=logging.INFO, # 可以暂时设置为 DEBUG 级别以获取更多信息
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load configuration
try:
    with open('config.yaml', 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    logger.info("config.yaml loaded successfully.")
    # 打印部分关键配置，确认是否加载正确
    logger.info(f"API ID: {config.get('api_id')}")
    logger.info(f"API Hash: {'*' * (len(config.get('api_hash', '')) - 4) + config.get('api_hash', '')[-4:]}") # 只显示后四位
    # IMPORTANT: Ensure admin_ids is a list in config.yaml, e.g., admin_ids: [123456789]
    logger.info(f"Admin IDs: {config.get('admin_ids')}") 
except FileNotFoundError:
    logger.critical("config.yaml not found! Please create it based on the example.")
    exit(1)
except Exception as e:
    logger.critical(f"Error loading config.yaml: {e}")
    exit(1)

# Initialize database
try:
    init_db()
    logger.info("Database initialized successfully.")
except Exception as e:
    logger.critical(f"Error initializing database: {e}")
    exit(1)

# =====================
# 下面是无类的纯函数式实现
# =====================

def load_persisted_rules(account_config):
    text_watch_rules = {}
    media_watch_rules = {}
    text_rules = account_config.get('text_watch_rules', [])
    for rule in text_rules:
        text_watch_rules[(str(rule['source_id']), rule['keyword'])] = str(rule['target_id'])
    media_rules = account_config.get('media_watch_rules', [])
    for rule in media_rules:
        if isinstance(rule, dict):
            media_watch_rules[str(rule['source_id'])] = {'target_id': str(rule['target_id']), 'type': rule.get('type')}
        else:
            media_watch_rules[str(rule['source_id'])] = {'target_id': str(rule), 'type': None}
    return text_watch_rules, media_watch_rules

def persist_rules(account_name, text_watch_rules, media_watch_rules):
    config_path = 'config.yaml'
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            full_config = yaml.safe_load(f)
        found = False
        for acc in full_config['accounts']:
            if acc['name'] == account_name:
                acc['text_watch_rules'] = [
                    {'source_id': sid, 'keyword': keyword, 'target_id': tid}
                    for (sid, keyword), tid in text_watch_rules.items()
                ]
                acc['media_watch_rules'] = [
                    {'source_id': sid, 'target_id': v['target_id'], 'type': v['type']} if isinstance(v, dict) else {'source_id': sid, 'target_id': v, 'type': None}
                    for sid, v in media_watch_rules.items()
                ]
                found = True
                break
        if not found:
            logger.warning(f"Could not find account '{account_name}' in config.yaml to persist rules.")
            return
        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(full_config, f, allow_unicode=True, indent=2)
        logger.info(f"Rules for account {account_name} persisted to config.yaml.")
    except Exception as e:
        logger.error(f"Error persisting rules for account {account_name}: {e}")

def persist_config_changes_to_file(account_name, account_config, text_watch_rules, media_watch_rules):
    config_path = 'config.yaml'
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            full_config = yaml.safe_load(f)
        found = False
        for i, acc in enumerate(full_config['accounts']):
            if acc['name'] == account_name:
                full_config['accounts'][i]['monitoring'] = account_config.get('monitoring', {})
                full_config['accounts'][i]['storage'] = account_config.get('storage', {})
                full_config['accounts'][i]['text_watch_rules'] = [
                    {'source_id': sid, 'keyword': keyword, 'target_id': tid}
                    for (sid, keyword), tid in text_watch_rules.items()
                ]
                full_config['accounts'][i]['media_watch_rules'] = [
                    {'source_id': sid, 'target_id': v['target_id'], 'type': v.get('type')}
                    if isinstance(v, dict) else {'source_id': sid, 'target_id': v, 'type': None}
                    for sid, v in media_watch_rules.items()
                ]
                found = True
                break
        if not found:
            logger.warning(f"Could not find account '{account_name}' in full_config to persist general config changes.")
            return
        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(full_config, f, allow_unicode=True, indent=2)
        logger.info(f"General config changes for account {account_name} persisted to config.yaml.")
    except Exception as e:
        logger.error(f"Error persisting general config changes for account {account_name}: {e}")

def get_db_account(account_name, session_name):
    db = SessionLocal()
    try:
        db_account = db.query(Account).filter(
            Account.name == account_name,
            Account.session_name == session_name
        ).first()
        if not db_account:
            db_account = Account(
                name=account_name,
                session_name=session_name,
                is_active=True
            )
            db.add(db_account)
            db.commit()
            db.refresh(db_account)
        else:
            if not db_account.is_active:
                db_account.is_active = True
                db.commit()
                db.refresh(db_account)
        logger.info(f"Database account initialized: {db_account.id}, Name: {db_account.name}, Session: {db_account.session_name}")
        return db_account
    except Exception as e:
        logger.error(f"Error initializing database account: {e}")
        db.rollback()
        raise
    finally:
        db.close()

def setup_handlers(client, account_config, account_name, db_account, text_watch_rules, media_watch_rules):
    logger.info(f"Setting up event handlers for account {account_name}...")
    
    # 使用 lambda 函数包装 async 方法，确保它们能在内部类中被正确引用
    @client.on(events.NewMessage)
    async def _handle_new_message(event):
        await handle_message(event, client, account_config, account_name, db_account, text_watch_rules, media_watch_rules)
    
    @client.on(events.NewMessage(pattern='/watch_text'))
    async def _handle_watch_text_command(event):
        await handle_watch_text_command(event, client, account_config, account_name, text_watch_rules, media_watch_rules)
    
    @client.on(events.NewMessage(pattern='/watch_media'))
    async def _handle_watch_media_command(event):
        await handle_watch_media_command(event, client, account_config, account_name, text_watch_rules, media_watch_rules)
    
    @client.on(events.NewMessage(pattern='/batch_forward'))
    async def _handle_batch_forward_command(event):
        await handle_batch_forward_command(event, client, account_config, account_name, db_account, text_watch_rules, media_watch_rules)
    
    @client.on(events.NewMessage(pattern='/help'))
    async def _handle_help_command(event):
        await handle_help_command(event, client, account_config, account_name)
    
    @client.on(events.NewMessage(pattern='/status'))
    async def _handle_account_command(event):
        await handle_account_command(event, client, account_config, account_name, db_account, text_watch_rules, media_watch_rules)
    
    @client.on(events.NewMessage(pattern='/config'))
    async def _handle_config_command(event):
        await handle_config_command(event, client, account_config, account_name, text_watch_rules, media_watch_rules)
    
    @client.on(events.NewMessage(pattern='/msginfo'))
    async def _handle_msginfo_command(event):
        await handle_msginfo_command(event, client, account_config, account_name)
    
    logger.info(f"Event handlers for account {account_name} are now active.")

async def handle_message(event, client, account_config, account_name, db_account, text_watch_rules, media_watch_rules):
    """处理新消息，支持群组、频道和私聊"""
    logger.debug(f"[DEBUG] handle_message triggered for chat_id: {event.chat_id}, message_id: {event.message.id}")
    
    # 判断是否为私聊、群组或频道
    is_private = event.is_private
    is_group = event.is_group
    is_channel = event.is_channel

    logger.debug(f"[DEBUG] Message type: private={is_private}, group={is_group}, channel={is_channel}")

    # 只处理配置中允许的群组/频道/私聊
    enabled_chats = [str(cid) for cid in account_config['monitoring'].get('enabled_chats', [])] # 确保都是字符串
    logger.debug(f"[DEBUG] Configured enabled_chats: {enabled_chats}")

    # 获取消息来源的 chat_id (统一为字符串)
    source_id = str(event.chat_id)

    if is_group or is_channel:
        if enabled_chats and source_id not in enabled_chats:
            logger.debug(f"[DEBUG] Skipping disabled group/channel chat_id: {source_id}")
            return
        else:
            logger.debug(f"[DEBUG] Processing group/channel message from chat_id: {source_id}")
    elif is_private:
        monitor_private_bots = account_config['monitoring'].get('monitor_private_bots', False)
        bot_usernames = account_config['monitoring'].get('bot_usernames', [])
        logger.debug(f"[DEBUG] Private chat monitoring config: monitor_private_bots={monitor_private_bots}, bot_usernames={bot_usernames}")

        if monitor_private_bots:
            sender_is_bot = getattr(event.message.sender, 'bot', False)
            sender_username = getattr(event.message.sender, 'username', None)
            logger.debug(f"[DEBUG] Private message sender: is_bot={sender_is_bot}, username={sender_username}")

            if not sender_is_bot:
                logger.debug(f"[DEBUG] Skipping non-bot private message: sender={event.message.sender_id}")
                return
            if bot_usernames and sender_username not in bot_usernames:
                logger.debug(f"[DEBUG] Skipping unmonitored bot: {sender_username}")
                return
            logger.debug(f"[DEBUG] Processing private bot message from sender: {sender_username} ({event.message.sender_id})")
        else:
            logger.debug(f"[DEBUG] monitor_private_bots is False, skipping all private messages (unless specifically enabled for users).")
            # 如果 monitor_private_bots 为 False，且没有其他逻辑来处理非机器人私聊，则跳过
            return
    else:
        # 既不是私聊也不是群组/频道 (例如，可能是未知类型的更新)
        logger.debug(f"[DEBUG] Skipping unknown message type from chat_id: {source_id}")
        return

    try:
        # 记录消息
        message = Message(
            account_id=db_account.id,
            message_id=event.message.id,
            chat_id=event.chat_id,
            chat_title=event.chat.title if hasattr(event.chat, 'title') and event.chat.title else "Chat",
            sender_id=event.message.sender_id,
            sender_username=getattr(event.message.sender, 'username', None),
            content=event.message.text or event.message.caption or "",
            timestamp=datetime.now(),
            is_bot=getattr(event.message.sender, 'bot', False),
            is_forwarded=event.message.forward is not None
        )

        # 保存消息
        with SessionLocal() as session:
            session.add(message)
            session.commit()
        logger.debug(f"[DEBUG] Message {event.message.id} from {event.chat_id} saved to DB.")

        logger.debug(f"[DEBUG] Current text watch rules: {text_watch_rules}")
        logger.debug(f"[DEBUG] Current media watch rules: {media_watch_rules}")

        # 处理媒体文件
        if event.message.media:
            logger.debug(f"[DEBUG] Message contains media. Calling handle_media.")
            await handle_media(event.message, account_config)
        # 文字监控
        if event.message.text:
            text_processed = False
            for (sid, keyword), target_id in text_watch_rules.items():
                if sid == source_id and (keyword == '*' or keyword in event.message.text): # source_id 已经是字符串
                    logger.info(f"命中文字规则: ({sid}, '{keyword}') -> {target_id}. 转发消息: '{event.message.text[:50]}...'")
                    await safe_forward_message(event.message, target_id, client)
                    text_processed = True
                    break # 命中一个规则后停止，避免重复转发
            if not text_processed:
                logger.debug(f"[DEBUG] No text rule hit for chat_id={source_id}, text='{event.message.text[:50]}...'")
        # 媒体监控
        if event.message.media: # 再次检查是否有媒体，因为之前可能只是下载
            if source_id in media_watch_rules:
                rule = media_watch_rules[source_id]
                target_id_media = rule['target_id']
                media_type = rule.get('type')
                should_forward = False
                doc = getattr(event.message.media, 'document', None)
                mime = doc.mime_type if doc and hasattr(doc, 'mime_type') else None
                if media_type == 'all':
                    should_forward = True
                elif media_type == 'all-txt':
                    # 新增：所有消息（包括纯文字和所有媒体）
                    should_forward = True
                elif media_type in (None, '', 'media'):
                    # 默认：常见媒体
                    if event.message.photo or (mime and (mime.startswith('image/') or mime.startswith('video/') or mime.startswith('audio/'))):
                        should_forward = True
                elif media_type == 'photo' or media_type == 'image':
                    if event.message.photo or (mime and mime.startswith('image/')):
                        should_forward = True
                elif media_type == 'video':
                    if (mime and mime.startswith('video/')):
                        should_forward = True
                elif media_type == 'audio':
                    if (mime and mime.startswith('audio/')):
                        should_forward = True
                elif media_type == 'document':
                    if doc and not (mime and (mime.startswith('image/') or mime.startswith('video/') or mime.startswith('audio/'))):
                        should_forward = True
                elif media_type == 'text':
                    if doc and mime and (mime == 'text/plain' or (doc.attributes and any(getattr(attr, 'file_name', '').endswith('.txt') for attr in doc.attributes))):
                        should_forward = True
                if should_forward:
                    logger.info(f"命中媒体规则: {source_id} -> {target_id_media} 类型: {media_type or 'media'} 转发媒体消息 {event.message.id}.")
                    await safe_forward_message(event.message, target_id_media, client)
                else:
                    logger.debug(f"[DEBUG] Media rule hit but type not match: {media_type}, mime: {mime}")
            else:
                logger.debug(f"[DEBUG] No media rule hit for chat_id={source_id}.")
    except Exception as e:
        logger.error(f"处理消息时发生未预期错误: {str(e)}", exc_info=True) # 打印完整堆栈
        # 注意：这里不能await event.respond，因为handle_message是通用监听，可能来自不应回复的群组
        # 或者可以只在私聊中回复错误
        if is_private and await check_admin(event, account_config): # 仅管理员私聊时回复错误
            await event.respond(f"处理消息时发生错误: {str(e)}")

async def handle_media(message, account_config):
    """处理媒体文件"""
    logger.debug(f"[DEBUG] handle_media triggered for message_id: {message.id}")
    try:
        if not account_config['storage'].get('auto_download', False): # 确保 auto_download 配置存在且为True
            logger.debug("Auto download is disabled in config. Skipping media download.")
            return

        download_path_base = account_config['storage'].get('download_path', './downloads')
        os.makedirs(download_path_base, exist_ok=True) # 确保下载路径存在
        logger.debug(f"Download path base: {download_path_base}")

        file_name = None
        ext = None
        mime = None
        if message.media:
            if isinstance(message.media, MessageMediaDocument) and message.media.document:
                doc = message.media.document
                # 优先从 attributes 获取文件名
                for attr in doc.attributes:
                    if hasattr(attr, 'file_name') and attr.file_name:
                        file_name = attr.file_name
                        break
                mime = getattr(doc, 'mime_type', None)
                logger.debug(f"Media is document, original file_name: {file_name}, mime_type: {mime}")
                # 如果没有 file_name，尝试用 mime_type 推断扩展名
                if not file_name:
                    ext = None
                    if mime:
                        if mime.startswith('image/'):
                            ext = '.' + mime.split('/')[-1]
                        elif mime.startswith('video/'):
                            ext = '.' + mime.split('/')[-1]
                        elif mime.startswith('audio/'):
                            ext = '.' + mime.split('/')[-1]
                        elif mime == 'application/pdf':
                            ext = '.pdf'
                        elif mime == 'text/plain':
                            ext = '.txt'
                    file_name = f"document_{message.id}{ext or '.file'}"
                else:
                    # 如果 file_name 没有扩展名但 mime_type 有，补全扩展名
                    if '.' not in file_name and mime:
                        if mime.startswith('image/'):
                            file_name += '.' + mime.split('/')[-1]
                        elif mime.startswith('video/'):
                            file_name += '.' + mime.split('/')[-1]
                        elif mime.startswith('audio/'):
                            file_name += '.' + mime.split('/')[-1]
                        elif mime == 'application/pdf':
                            file_name += '.pdf'
                        elif mime == 'text/plain':
                            file_name += '.txt'
            elif isinstance(message.media, MessageMediaPhoto):
                file_name = f"photo_{message.id}.jpg"
                logger.debug(f"Media is photo, generated file_name: {file_name}")
            elif isinstance(message.media, MessageMediaWebPage) and message.media.webpage.document:
                doc = message.media.webpage.document
                for attr in doc.attributes:
                    if hasattr(attr, 'file_name') and attr.file_name:
                        file_name = attr.file_name
                        break
                mime = getattr(doc, 'mime_type', None)
                if not file_name:
                    ext = None
                    if mime:
                        if mime.startswith('image/'):
                            ext = '.' + mime.split('/')[-1]
                        elif mime.startswith('video/'):
                            ext = '.' + mime.split('/')[-1]
                        elif mime.startswith('audio/'):
                            ext = '.' + mime.split('/')[-1]
                        elif mime == 'application/pdf':
                            ext = '.pdf'
                        elif mime == 'text/plain':
                            ext = '.txt'
                    file_name = f"webmedia_{message.id}{ext or '.file'}"
                else:
                    if '.' not in file_name and mime:
                        if mime.startswith('image/'):
                            file_name += '.' + mime.split('/')[-1]
                        elif mime.startswith('video/'):
                            file_name += '.' + mime.split('/')[-1]
                        elif mime.startswith('audio/'):
                            file_name += '.' + mime.split('/')[-1]
                        elif mime == 'application/pdf':
                            file_name += '.pdf'
                        elif mime == 'text/plain':
                            file_name += '.txt'
                logger.debug(f"Media is webpage document, generated file_name: {file_name}, mime_type: {mime}")
            else:
                file_name = f"media_{message.id}.unknown" # 通用回退
                logger.debug(f"Media is unknown type, generated file_name: {file_name}")

            if file_name:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                formatted_name_pattern = account_config['storage'].get('file_naming', "{timestamp}_{chat_id}_{message_id}_{filename}")
                formatted_name = formatted_name_pattern.format(
                    chat_id=message.chat_id,
                    message_id=message.id,
                    timestamp=timestamp,
                    filename=file_name
                )

                download_path_full = os.path.join(download_path_base, formatted_name)
                logger.info(f"准备下载媒体文件到: {download_path_full}")
                await message.download_media(download_path_full)
                logger.info(f"已下载媒体文件: {formatted_name}")
            else:
                logger.warning(f"Could not determine file name for message {message.id}, skipping download.")
        else:
            logger.debug(f"No media found in message {message.id}.")
    except Exception as e:
        logger.error(f"处理媒体文件时出错: {str(e)}", exc_info=True)

async def handle_watch_text_command(event, client, account_config, account_name, text_watch_rules, media_watch_rules):
    """命令格式: /watch_text 源chatid 目标chatid 关键词"""
    logger.info(f"Received /watch_text command from {event.sender_id}: {event.text}")
    if not event.is_private or not await check_admin(event, account_config):
        return
    try:
        args = event.text.strip().split()
        if len(args) != 4:
            await event.respond("用法: /watch_text <源chatid> <目标chatid> <关键词>")
            return
        source_id = str(args[1].strip().strip('_'))
        target_id = str(args[2].strip().strip('_'))
        keyword = args[3]
        text_watch_rules[(source_id, keyword)] = target_id
        persist_rules(account_name, text_watch_rules, media_watch_rules)
        await event.respond(f"已添加文字监控: 源: `{source_id}` -> 目标: `{target_id}`，关键词: `{keyword}`", parse_mode='markdown')
    except Exception as e:
        logger.error(f"Error handling /watch_text command: {e}", exc_info=True)
        await event.respond(f"添加失败: {e}")

async def handle_watch_media_command(event, client, account_config, account_name, text_watch_rules, media_watch_rules):
    """命令格式: /watch_media 源chatid 目标chatid [type]"""
    logger.info(f"Received /watch_media command from {event.sender_id}: {event.text}")
    if not event.is_private or not await check_admin(event, account_config):
        return
    try:
        args = event.text.strip().split()
        if len(args) < 3:
            await event.respond("用法: /watch_media <源chatid> <目标chatid> [type] (type 可选: all, photo, video, image, document, audio, text)")
            return
        source_id = str(args[1].strip().strip('_'))
        target_id = str(args[2].strip().strip('_'))
        media_type = args[3].lower() if len(args) > 3 else None
        # 存储为 dict，支持类型
        media_watch_rules[source_id] = {'target_id': target_id, 'type': media_type}
        persist_rules(account_name, text_watch_rules, media_watch_rules)
        await event.respond(f"已添加媒体监控: 源: `{source_id}` -> 目标: `{target_id}` 类型: `{media_type or 'media'}`", parse_mode='markdown')
    except Exception as e:
        logger.error(f"Error handling /watch_media command: {e}", exc_info=True)
        await event.respond(f"添加失败: {e}")

async def handle_batch_forward_command(event, client, account_config, account_name, db_account, text_watch_rules, media_watch_rules):
    """命令格式: /batch_forward 源chatid 目标chatid 数量 [跳过数量] [type]"""
    logger.info(f"Received /batch_forward command from {event.sender_id}: {event.text}")
    if not event.is_private or not await check_admin(event, account_config):
        return
    try:
        args = event.text.strip().split()
        if len(args) < 4:
            await event.respond("用法: /batch_forward <源chatid> <目标chatid> <数量> [跳过数量] [type] (type 可选: all, photo, video, image, document, audio, text)")
            return
        source_chat_id = int(args[1])
        target_chat_id = int(args[2])
        limit = int(args[3])
        offset = int(args[4]) if len(args) > 4 and args[4].isdigit() else 0
        media_type = args[5].lower() if len(args) > 5 else None

        await event.respond(f"开始批量转发...\n源: `{source_chat_id}`\n目标: `{target_chat_id}`\n数量: `{limit}`\n跳过: `{offset}`\n类型: `{media_type or 'photo+video'}`", parse_mode='markdown')
        await batch_forward_media(source_chat_id, target_chat_id, limit, offset, media_type, client)
        await event.respond("批量转发完成！")
    except ValueError:
        await event.respond("参数错误：chatid、数量和跳过数量必须是数字。")
    except Exception as e:
        logger.error(f"Error handling /batch_forward command: {e}", exc_info=True)
        await event.respond(f"批量转发出错: {e}")

async def batch_forward_media(source_chat_id, target_chat_id, limit=50, offset=0, media_type=None, client=None):
    """
    批量转发历史消息，支持 type 参数
    :param source_chat_id: 源群组/频道ID
    :param target_chat_id: 目标群组/频道ID
    :param limit: 获取的历史消息数量
    :param offset: 跳过前 offset 条
    :param media_type: 支持 all, all-txt, photo, video, image, document, audio, text
    """
    logger.info(f"Starting batch media forward from {source_chat_id} to {target_chat_id}, limit={limit}, offset={offset}, type={media_type}")
    count = 0
    try:
        async for message in client.iter_messages(source_chat_id, offset_id=0, reverse=True):
            if offset > 0:
                logger.debug(f"Skipping message {message.id} (offset remaining: {offset})")
                offset -= 1
                continue
            doc = getattr(message.media, 'document', None)
            mime = doc.mime_type if doc and hasattr(doc, 'mime_type') else None
            is_photo = message.photo is not None
            is_video = mime and mime.startswith('video/')
            is_image = is_photo or (mime and mime.startswith('image/'))
            is_audio = mime and mime.startswith('audio/')
            is_document = doc and not (is_image or is_video or is_audio)
            is_text = doc and (mime == 'text/plain' or (doc and doc.attributes and any(getattr(attr, 'file_name', '').endswith('.txt') for attr in doc.attributes)))
            # 新增网页预览类型判断
            is_webpage = message.media is not None and isinstance(message.media, MessageMediaWebPage)
            should_forward = False
            if media_type == 'all-txt':
                # 所有消息都转发（包括纯文字、所有媒体、网页预览）
                should_forward = True
            elif media_type == 'all':
                # 只转发有媒体的消息，且排除网页预览
                should_forward = message.media is not None and not is_webpage
            elif media_type in (None, '', 'media'):
                should_forward = is_image or is_video
            elif media_type in ('photo', 'image'):
                should_forward = is_image
            elif media_type == 'video':
                should_forward = is_video
            elif media_type == 'audio':
                should_forward = is_audio
            elif media_type == 'document':
                should_forward = is_document
            elif media_type == 'text':
                should_forward = is_text
            if should_forward:
                try:
                    logger.info(f"Forwarding message {message.id} (type: {media_type or 'photo+video'}) from {source_chat_id} to {target_chat_id}")
                    await message.forward_to(target_chat_id)
                    count += 1
                    logger.info(f"Successfully forwarded message {message.id}. Total forwarded: {count}/{limit}")
                    await asyncio.sleep(2)
                except Exception as e:
                    preview = (message.text or message.caption or '').replace('\n', ' ')[:60]
                    media_info = f"photo={is_photo}, video={is_video}, image={is_image}, audio={is_audio}, document={is_document}, text={is_text}, mime={mime}, webpage={is_webpage}"
                    logger.error(f"转发消息失败 | id={message.id} | 预览='{preview}' | 媒体: {media_info} | 错误类型: {type(e).__name__} | 详情: {e}", exc_info=True)
            else:
                logger.debug(f"Message {message.id} from {source_chat_id} is not type {media_type or 'photo+video'}, skipping.")
            if count >= limit:
                logger.info(f"Reached forwarding limit ({limit}). Stopping batch forward.")
                break
    except Exception as e:
        logger.error(f"Error during batch media forwarding: {e}", exc_info=True)
        raise # 重新抛出异常，让调用者处理

async def handle_help_command(event, client, account_config, account_name):
    """显示所有命令及用途"""
    logger.info(f"Received /help command from {event.sender_id}")
    if not event.is_private or not await check_admin(event, account_config):
        return
    help_text = (
        "可用命令列表：\n"
        "/help - 显示本帮助信息\n"
        "/watch_text <源chatid> <目标chatid> <关键词> - 文字监控转发（*为全部）\n"
        "/watch_media <源chatid> <目标chatid> [type] - 媒体监控转发，type 可选：all, photo, video, image, document, audio, text，all 表示所有文件，默认仅常见媒体\n"
        "/batch_forward <源chatid> <目标chatid> <数量> [跳过数量] - 批量转发历史图片和视频\n"
        "/status - 查看当前账号状态和监控规则\n"
        "/config - 查看和设置配置项（例如：/config show, /config set auto_download true）\n"
    )
    await event.respond(help_text, parse_mode='markdown')

async def handle_account_command(event, client, account_config, account_name, db_account, text_watch_rules, media_watch_rules):
    """Handle account status command"""
    logger.info(f"Received /status command from {event.sender_id}")
    if not event.is_private or not await check_admin(event, account_config):
        return
    
    try:
        response = f"*Account Status for {account_name}:*\n\n"
        response += f"Name: `{account_name}`\n"
        response += f"Session: `{account_config['session_name']}`\n"
        response += f"Status: `{'Active' if db_account.is_active else 'Inactive'}`\n"
        response += f"Created: `{db_account.created_at.strftime('%Y-%m-%d %H:%M:%S')}`\n"
        response += f"\n*当前监控规则:*\n"
        if not text_watch_rules and not media_watch_rules:
            response += "暂无监控规则。\n"
        else:
            for (sid, keyword), tid in text_watch_rules.items():
                response += f"文字: 源:`{sid}` -> 目标:`{tid}` | 关键词: `{keyword}`\n"
            for sid, tid in media_watch_rules.items():
                response += f"媒体: 源:`{sid}` -> 目标:`{tid}`\n"
        await event.respond(response, parse_mode='markdown')
            
    except Exception as e:
        logger.error(f"Error handling account command: {e}", exc_info=True)
        await event.respond(f"处理状态命令时出错: {e}")

async def handle_config_command(event, client, account_config, account_name, text_watch_rules, media_watch_rules):
    """处理配置命令"""
    logger.info(f"Received /config command from {event.sender_id}: {event.text}")
    if not event.is_private or not await check_admin(event, account_config):
        return

    try:
        args = event.text.split()[1:] # 去掉命令本身
        if not args:
            await event.respond(
                "用法:\n"
                "`/config show` - 显示当前配置\n"
                "`/config set <选项> <值>` - 设置配置选项\n"
                "可用选项:\n"
                "- `auto_forward_media`: 是否自动转发媒体文件 (true/false)\n"
                "- `monitor_private_bots`: 是否监控机器人私聊 (true/false)\n"
                "- `auto_download`: 是否自动下载媒体文件 (true/false)\n"
                "- `enabled_chats`: 设置监控的群组/频道ID (例如: `/config set enabled_chats -100123456789 -100987654321`)"
                "- `bot_usernames`: 设置监控的机器人用户名 (例如: `/config set bot_usernames MyBotUsername AnotherBot`)"
                , parse_mode='markdown'
            )
            return

        action = args[0].lower()
        if action == "show":
            response = "*当前配置:*\n"
            response += f"自动转发媒体文件 (auto_forward_media): `{account_config['monitoring'].get('auto_forward_media', False)}`\n"
            response += f"监控机器人私聊 (monitor_private_bots): `{account_config['monitoring'].get('monitor_private_bots', False)}`\n"
            response += f"自动下载媒体文件 (auto_download): `{account_config['storage'].get('auto_download', False)}`\n"
            response += f"监控的群组/频道 (enabled_chats): `{', '.join(map(str, account_config['monitoring'].get('enabled_chats', []))) or '所有'}`\n"
            response += f"监控的机器人用户名 (bot_usernames): `{', '.join(account_config['monitoring'].get('bot_usernames', [])) or '所有机器人'}`"
            await event.respond(response, parse_mode='markdown')

        elif action == "set":
            if len(args) < 3: # 至少需要 set, option, value
                await event.respond("用法: `/config set <选项> <值>`", parse_mode='markdown')
                return

            option = args[1].lower()
            value_args = args[2:]

            if option in ['auto_forward_media', 'monitor_private_bots', 'auto_download']:
                if len(value_args) != 1 or value_args[0].lower() not in ['true', 'false']:
                    await event.respond(f"值必须是 `true` 或 `false`。", parse_mode='markdown')
                    return
                value = value_args[0].lower() == 'true'
                if option == 'auto_forward_media':
                    account_config['monitoring']['auto_forward_media'] = value
                    await event.respond(f"已{'启用' if value else '禁用'}自动转发媒体文件。")
                elif option == 'monitor_private_bots':
                    account_config['monitoring']['monitor_private_bots'] = value
                    await event.respond(f"已{'启用' if value else '禁用'}监控机器人私聊。")
                elif option == 'auto_download':
                    account_config['storage']['auto_download'] = value
                    await event.respond(f"已{'启用' if value else '禁用'}自动下载媒体文件。")
                persist_config_changes_to_file(account_name, account_config, text_watch_rules, media_watch_rules) # 保存到文件
                
            elif option == 'enabled_chats':
                # 允许设置多个chatid，将它们转换为整数列表
                try:
                    chat_ids = [int(cid) for cid in value_args]
                    account_config['monitoring']['enabled_chats'] = chat_ids
                    persist_config_changes_to_file(account_name, account_config, text_watch_rules, media_watch_rules)
                    await event.respond(f"已设置监控的群组/频道ID: `{', '.join(map(str, chat_ids))}`", parse_mode='markdown')
                except ValueError:
                    await event.respond("`enabled_chats` 的值必须是有效的数字ID列表。", parse_mode='markdown')
                    
            elif option == 'bot_usernames':
                # 允许设置多个机器人用户名
                account_config['monitoring']['bot_usernames'] = value_args # 直接使用列表
                persist_config_changes_to_file(account_name, account_config, text_watch_rules, media_watch_rules)
                await event.respond(f"已设置监控的机器人用户名: `{', '.join(value_args) or '无'}`", parse_mode='markdown')

            else:
                await event.respond("未知选项。", parse_mode='markdown')

        else:
            await event.respond("未知命令动作。请使用 `show` 或 `set`。", parse_mode='markdown')

    except Exception as e:
        logger.error(f"处理配置命令时出错: {str(e)}", exc_info=True)
        await event.respond(f"处理命令时出错: {str(e)}")

async def handle_msginfo_command(event, client, account_config, account_name):
    """处理 /msginfo 命令，显示被回复消息的详细信息"""
    logger.info(f"Received /msginfo command from {event.sender_id}")
    if not event.is_private or not await check_admin(event, account_config):
        return
    try:
        # 必须是回复消息
        if not event.is_reply:
            await event.respond("请在回复一条消息的情况下使用 /msginfo。")
            return
        reply_msg = await event.get_reply_message()
        if not reply_msg:
            await event.respond("未能获取被回复的消息。")
            return
        info = (
            f"**消息详细信息：**\n"
            f"chat_id: `{reply_msg.chat_id}`\n"
            f"message_id: `{reply_msg.id}`\n"
            f"from_id: `{getattr(reply_msg, 'from_id', None)}`\n"
            f"sender_username: `{getattr(reply_msg.sender, 'username', None)}`\n"
            f"chat_title: `{getattr(reply_msg.chat, 'title', None)}`\n"
            f"内容: `{(reply_msg.text or reply_msg.message or reply_msg.raw_text or '')[:100]}`"
        )
        await event.respond(info, parse_mode='markdown')
    except Exception as e:
        logger.error(f"Error in handle_msginfo_command: {e}", exc_info=True)
        await event.respond(f"获取消息信息失败: {e}")

async def check_admin(event, account_config):
    """Checks if the sender of the event is an admin (只检查当前账号的 admin_ids，类型统一为 int)"""
    admin_ids = account_config.get('admin_ids', [])
    # 统一 admin_ids 为 int 列表
    admin_ids_int = [int(i) for i in admin_ids]
    try:
        sender_id = int(event.sender_id)
    except Exception:
        sender_id = event.sender_id
    if sender_id in admin_ids_int:
        return True
    else:
        await event.respond("您不是管理员，无法使用此命令。")
        return False

async def safe_send_message(target_id, text, client):
    """安全发送消息，自动兼容 int/用户名两种写法，并捕获实体找不到等异常"""
    try:
        # 尝试将 target_id 转为 int，如果是纯数字
        if isinstance(target_id, str) and target_id.lstrip('-').isdigit():
            target_id = int(target_id)
        await client.send_message(target_id, text)
    except ValueError as e:
        logger.error(f"无法找到目标实体 {target_id}，请确保机器人已与目标建立对话或在群组/频道内。错误: {e}")
    except Exception as e:
        logger.error(f"发送消息到 {target_id} 时出错: {e}")

async def safe_forward_message(message, target_id, client):
    """安全转发消息，自动兼容 int/用户名两种写法，并捕获实体找不到等异常"""
    try:
        if isinstance(target_id, str) and target_id.lstrip('-').isdigit():
            target_id = int(target_id)
        await message.forward_to(target_id)
    except ValueError as e:
        logger.error(f"无法找到目标实体 {target_id}，请确保机器人已与目标建立对话或在群组/频道内。错误: {e}")
    except Exception as e:
        logger.error(f"转发消息到 {target_id} 时出错: {e}")

async def main():
    logger.info("Starting main bot loop...")
    clients = []
    for account_config in config['accounts']:
        if account_config.get('enabled', False):
            account_name = account_config['name']
            logger.info(f"Initializing account: {account_name}")
            text_watch_rules, media_watch_rules = load_persisted_rules(account_config)
            custom_api = account_config.get('custom_api')
            proxy = None
            if custom_api and custom_api.get('enable', False):
                proxy_type = custom_api.get('proxy_type', 'socks5')
                host = custom_api.get('host')
                port = int(custom_api.get('port'))
                username = custom_api.get('username')
                password = custom_api.get('password')
                if proxy_type == 'mtproxy':
                    secret = custom_api.get('secret')
                    proxy = (proxy_type, host, port, secret)
                elif username and password:
                    proxy = (proxy_type, host, port, username, password)
                else:
                    proxy = (proxy_type, host, port)
                logger.info(f"Using proxy: {proxy_type}://{host}:{port}")
            client_kwargs = {
                "session": account_config['session_name'],
                "api_id": config['api_id'],
                "api_hash": config['api_hash'],
                "connection_retries": 10,
                "retry_delay": 2,
                "timeout": 60,
                "auto_reconnect": True
            }
            if proxy:
                client_kwargs["proxy"] = proxy
            client = TelegramClient(**client_kwargs)
            await client.connect()
            if not await client.is_user_authorized():
                phone = input(f"Enter phone number for account {account_name}: ")
                await client.send_code_request(phone)
                code = input(f"Enter the code you received for account {account_name}: ")
                try:
                    await client.sign_in(phone, code)
                except SessionPasswordNeededError:
                    password = input(f"Enter 2FA password for account {account_name}: ")
                    await client.sign_in(password=password)
                logger.info(f"Account {account_name} logged in successfully")
            else:
                logger.info(f"Account {account_name} is already authorized.")
            db_account = get_db_account(account_name, account_config['session_name'])
            setup_handlers(client, account_config, account_name, db_account, text_watch_rules, media_watch_rules)
            clients.append(client)
        else:
            logger.info(f"Account {account_config.get('name', 'Unnamed')} is disabled and will not be initialized.")
    if not clients:
        logger.critical("No accounts were successfully initialized. Exiting.")
        return
    logger.info(f"Successfully initialized {len(clients)} active accounts. Starting clients...")
    try:
        await asyncio.gather(*[client.run_until_disconnected() for client in clients])
    except KeyboardInterrupt:
        logger.info("Bot stopped by user (KeyboardInterrupt).")
    except Exception as e:
        logger.critical(f"An unexpected error occurred in main loop: {e}", exc_info=True)
    finally:
        logger.info("Disconnecting all clients...")
        for client in clients:
            if client.is_connected():
                await client.disconnect()
        logger.info("All clients disconnected. Exiting.")

if __name__ == '__main__':
    asyncio.run(main())

