import logging 
import asyncio
from telethon.tl.types import  MessageMediaWebPage
from modules.check_admin_utils import check_admin
from modules.offset_utils import is_media_type

logging.basicConfig(
    level=logging.INFO, # 可以暂时设置为 DEBUG 级别以获取更多信息
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
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
        #await batch_forward_media(source_chat_id, target_chat_id, limit, offset, media_type, client)
        #await event.respond("批量转发完成！")
        sent_count, last_id = await batch_forward_media(source_chat_id, target_chat_id, limit, offset, media_type, client)
        await event.respond(f"批量转发完成！共发送 {sent_count} 条，最后一条源消息ID是 {last_id}。\n下次可用 offset={offset+sent_count} 跳过。")
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
    last_message_id = None  # 新增
    try:
        async for message in client.iter_messages(source_chat_id, offset_id=0, reverse=True):
            if not is_media_type(message, media_type):
                continue
            if offset > 0:
                logger.debug(f"Skipping message {message.id} (offset remaining: {offset})")
                offset -= 1
                continue
            try:
                logger.info(f"Forwarding message {message.id} (type: {media_type or 'photo+video'}) from {source_chat_id} to {target_chat_id}")
                await message.forward_to(target_chat_id)
                count += 1
                last_message_id = message.id  # 记录最后一条成功转发的消息ID
                logger.info(f"Successfully forwarded message {message.id}. Total forwarded: {count}/{limit}")
                await asyncio.sleep(2)
            except Exception as e:
                preview = (message.text or '').replace('\n', ' ')[:60]
                logger.error(f"转发消息失败 | id={message.id} | 预览='{preview}' | 错误类型: {type(e).__name__} | 详情: {e}", exc_info=True)
            if count >= limit:
                logger.info(f"Reached forwarding limit ({limit}). Stopping batch forward.")
                break
    except Exception as e:
        logger.error(f"Error during batch media forwarding: {e}", exc_info=True)
        raise # 重新抛出异常，让调用者处理
    return count, last_message_id  # 返回最后一条成功转发的消息ID
