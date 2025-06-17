import os
import yaml
import logging
from telethon import TelegramClient, events
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
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load configuration
with open('config.yaml', 'r', encoding='utf-8') as f:
    config = yaml.safe_load(f)

# Initialize database
init_db()

class BotAccount:
    def __init__(self, account_config):
        self.config = account_config
        self.name = account_config['name']
        self.client = None
        self.logger = logging.getLogger(f"BotAccount_{self.name}")
        self.db_account = None  # 数据库中的账户记录
        
    async def initialize(self):
        """Initialize the bot account"""
        try:
            # Create client
            self.client = TelegramClient(
                self.config['session_name'],
                config['api_id'],
                config['api_hash'],
                connection_retries=10,
                retry_delay=2,
                timeout=60,
                auto_reconnect=True
            )
            
            # Connect and login
            await self.client.connect()
            if not await self.client.is_user_authorized():
                await self.login()
            
            # Initialize database account
            self.init_db_account()
            
            # Set up event handlers
            self.setup_handlers()
            
            self.logger.info(f"Account {self.name} initialized successfully")
            return True
        except Exception as e:
            self.logger.error(f"Error initializing account {self.name}: {e}")
            return False
    
    async def login(self):
        """Handle login process"""
        try:
            phone = input(f"Enter phone number for account {self.name}: ")
            await self.client.send_code_request(phone)
            code = input(f"Enter the code you received for account {self.name}: ")
            try:
                await self.client.sign_in(phone, code)
            except SessionPasswordNeededError:
                password = input(f"Enter 2FA password for account {self.name}: ")
                await self.client.sign_in(password=password)
            self.logger.info(f"Account {self.name} logged in successfully")
        except Exception as e:
            self.logger.error(f"Error logging in account {self.name}: {e}")
            raise
    
    def init_db_account(self):
        """Initialize or get database account record"""
        db = SessionLocal()
        try:
            # 查找或创建账户记录
            self.db_account = db.query(Account).filter(
                Account.name == self.name,
                Account.session_name == self.config['session_name']
            ).first()
            
            if not self.db_account:
                self.db_account = Account(
                    name=self.name,
                    session_name=self.config['session_name'],
                    is_active=True
                )
                db.add(self.db_account)
                db.commit()
                db.refresh(self.db_account)
                
            self.logger.info(f"Database account initialized: {self.db_account.id}")
        except Exception as e:
            self.logger.error(f"Error initializing database account: {e}")
            db.rollback()
            raise
        finally:
            db.close()
    
    def setup_handlers(self):
        """Set up event handlers for this account"""
        @self.client.on(events.NewMessage)
        async def handle_new_message(event):
            await self.handle_message(event)
        
        @self.client.on(events.NewMessage(pattern='/watch'))
        async def handle_watch_command(event):
            await self.handle_watch_command(event)
        
        @self.client.on(events.NewMessage(pattern='/keywords'))
        async def handle_keywords_command(event):
            await self.handle_keywords_command(event)
        
        @self.client.on(events.NewMessage(pattern='/forwardrule'))
        async def handle_forwardrule_command(event):
            await self.handle_forwardrule_command(event)
        
        @self.client.on(events.NewMessage(pattern='/status'))  # 简化命令名
        async def handle_account_command(event):
            await self.handle_account_command(event)
    
    async def handle_message(self, event):
        """处理新消息"""
        try:
            # 检查是否是私聊
            if not event.is_private:
                return

            # 检查是否是机器人消息
            if not event.message.sender.bot:
                return

            # 获取机器人用户名
            bot_username = event.message.sender.username
            if not bot_username:
                return

            # 检查是否在监控列表中
            if (self.config['monitoring']['bot_usernames'] and 
                bot_username not in self.config['monitoring']['bot_usernames']):
                return

            # 记录消息
            message = Message(
                account_id=self.db_account.id,
                message_id=event.message.id,
                chat_id=event.chat_id,
                chat_title=event.chat.title if event.chat.title else "Private Chat",
                sender_id=event.message.sender_id,
                sender_username=bot_username,
                message_text=event.message.text or event.message.caption or "",
                timestamp=datetime.now(),
                is_bot=True,
                is_forwarded=event.message.forward is not None
            )

            # 检查关键词
            detected_keywords = []
            if message.message_text:  # 只在有文本内容时检查关键词
                for keyword in self.keywords:
                    if keyword.is_regex:
                        if re.search(keyword.pattern, message.message_text, re.IGNORECASE):
                            detected_keywords.append(keyword.pattern)
                    else:
                        if keyword.pattern.lower() in message.message_text.lower():
                            detected_keywords.append(keyword.pattern)

            # 保存消息
            async with self.db_session() as session:
                session.add(message)
                await session.commit()

            # 处理媒体文件
            if event.message.media:
                await self.handle_media(event.message)
                # 如果启用了自动转发媒体文件，直接触发转发
                if self.config['monitoring']['auto_forward_media']:
                    await self.handle_forwarding(event.message, detected_keywords, force_forward=True)
                elif detected_keywords:
                    # 否则只在有关键词时转发
                    await self.handle_forwarding(event.message, detected_keywords)
            elif detected_keywords:
                # 如果是文本消息且有关键词，才触发转发
                await self.handle_forwarding(event.message, detected_keywords)

        except Exception as e:
            logger.error(f"处理消息时出错: {str(e)}")

    async def handle_media(self, message):
        """处理媒体文件"""
        try:
            if not self.config['storage']['auto_download']:
                return

            # 获取文件名
            if message.media:
                if hasattr(message.media, 'document'):
                    file_name = message.media.document.attributes[0].file_name
                elif hasattr(message.media, 'photo'):
                    file_name = f"photo_{message.id}.jpg"
                else:
                    file_name = f"media_{message.id}"

                # 使用配置的命名格式
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                formatted_name = self.config['storage']['file_naming'].format(
                    chat_id=message.chat_id,
                    message_id=message.id,
                    timestamp=timestamp,
                    filename=file_name
                )

                # 下载文件
                download_path = os.path.join(self.config['storage']['download_path'], formatted_name)
                await message.download_media(download_path)
                logger.info(f"已下载媒体文件: {formatted_name}")

        except Exception as e:
            logger.error(f"处理媒体文件时出错: {str(e)}")

    async def handle_forwarding(self, message, detected_keywords, force_forward=False):
        """处理消息转发"""
        try:
            async with self.db_session() as session:
                # 获取所有启用的转发规则
                rules = await session.execute(
                    select(ForwardRule).where(
                        ForwardRule.account_id == self.db_account.id,
                        ForwardRule.is_active == True
                    )
                )
                rules = rules.scalars().all()

                if not rules:
                    return

                # 如果不是强制转发，只使用匹配关键词的规则
                if not force_forward:
                    rules = [rule for rule in rules if rule.keyword in detected_keywords]

                if not rules:
                    return

                logger.info(f"找到 {len(rules)} 个转发规则")
                for rule in rules:
                    logger.info(f"规则: 目标='{rule.target_chat_id}'")

                # 处理每个匹配的规则
                for rule in rules:
                    try:
                        # 检查消息类型
                        if message.media:
                            # 获取媒体类型
                            media_type = type(message.media).__name__
                            logger.info(f"转发媒体文件: 类型={media_type}")

                            # 根据媒体类型处理
                            if hasattr(message.media, 'document'):
                                # 文档类型
                                file_name = message.media.document.attributes[0].file_name
                                mime_type = message.media.document.mime_type
                                logger.info(f"文档: {file_name} ({mime_type})")
                                
                                # 下载并重新上传
                                file_path = await message.download_media(
                                    self.config['storage']['download_path']
                                )
                                if file_path:
                                    await self.client.send_file(
                                        rule.target_chat_id,
                                        file_path,
                                        caption=message.caption or f"文档: {file_name}",
                                        force_document=True
                                    )
                                    # 删除临时文件
                                    os.remove(file_path)
                                    logger.info(f"文档已转发到 {rule.target_chat_id}")

                            elif hasattr(message.media, 'photo'):
                                # 图片类型
                                logger.info("转发图片")
                                await message.forward_to(rule.target_chat_id)

                            elif hasattr(message.media, 'video'):
                                # 视频类型
                                logger.info("转发视频")
                                await message.forward_to(rule.target_chat_id)

                            elif hasattr(message.media, 'voice'):
                                # 语音消息
                                logger.info("转发语音消息")
                                await message.forward_to(rule.target_chat_id)

                            elif hasattr(message.media, 'audio'):
                                # 音频文件
                                logger.info("转发音频文件")
                                await message.forward_to(rule.target_chat_id)

                            else:
                                # 其他类型媒体
                                logger.info(f"转发其他类型媒体: {media_type}")
                                await message.forward_to(rule.target_chat_id)

                        else:
                            # 纯文本消息
                            await message.forward_to(rule.target_chat_id)
                            logger.info(f"文本消息已转发到 {rule.target_chat_id}")

                    except Exception as e:
                        logger.error(f"转发失败: {str(e)} (规则ID: {rule.id})")
                        if self.config['forwarding']['fallback_to_upload']:
                            try:
                                if message.media:
                                    # 下载并重新上传
                                    file_path = await message.download_media(
                                        self.config['storage']['download_path']
                                    )
                                    if file_path:
                                        await self.client.send_file(
                                            rule.target_chat_id,
                                            file_path,
                                            caption=message.caption or ""
                                        )
                                        # 删除临时文件
                                        os.remove(file_path)
                                        logger.info(f"媒体文件已重新上传到 {rule.target_chat_id}")
                                else:
                                    await self.client.send_message(
                                        rule.target_chat_id,
                                        message.text or message.caption or ""
                                    )
                                    logger.info(f"消息已重新上传到 {rule.target_chat_id}")
                            except Exception as upload_error:
                                logger.error(f"重新上传失败: {str(upload_error)}")
                        else:
                            raise e

        except Exception as e:
            logger.error(f"处理转发时出错: {str(e)}")

    async def handle_keywords_command(self, event):
        """Handle keywords command"""
        if not event.is_private or not await self.check_admin(event):
            return
        
        try:
            args = event.text.split(maxsplit=2)
            if len(args) < 2:
                await event.respond("Usage: /keywords add|remove <pattern>")
                return
            
            action = args[1]
            db = SessionLocal()
            
            if action == 'add' and len(args) == 3:
                pattern = args[2]
                keyword = Keyword(
                    account_id=self.db_account.id,  # 关联到当前账户
                    pattern=pattern
                )
                db.add(keyword)
                db.commit()
                await event.respond(f"Added keyword: {pattern}")
                
            elif action == 'remove' and len(args) == 3:
                try:
                    keyword_id = int(args[2])
                    # 只删除当前账户的关键词
                    keyword = db.query(Keyword).filter(
                        Keyword.id == keyword_id,
                        Keyword.account_id == self.db_account.id
                    ).first()
                    if keyword:
                        db.delete(keyword)
                        db.commit()
                        await event.respond(f"Removed keyword ID: {keyword_id}")
                    else:
                        await event.respond("Keyword not found")
                except ValueError:
                    await event.respond("Invalid keyword ID")
            
            db.close()
                
        except Exception as e:
            self.logger.error(f"Error handling keywords command: {e}")
            await event.respond("Error processing command")
    
    async def handle_forwardrule_command(self, event):
        """处理转发规则命令"""
        if not event.is_private:
            return

        try:
            # 检查是否是管理员
            if event.sender_id not in self.config['admin_ids']:
                await event.respond("只有管理员可以使用此命令")
                return

            # 解析命令参数
            args = event.text.split()[1:]  # 去掉命令本身
            if not args:
                await event.respond(
                    "用法:\n"
                    "/forwardrule add <关键词> <目标聊天ID> - 添加转发规则\n"
                    "/forwardrule remove <规则ID> - 删除转发规则\n"
                    "/forwardrule list - 列出所有转发规则"
                )
                return

            action = args[0].lower()
            async with self.db_session() as session:
                if action == "add":
                    if len(args) != 3:
                        await event.respond("用法: /forwardrule add <关键词> <目标聊天ID>")
                        return

                    keyword = args[1]
                    target_chat_id = int(args[2])

                    # 检查关键词是否存在
                    keyword_exists = await session.execute(
                        select(Keyword).where(
                            Keyword.account_id == self.db_account.id,
                            Keyword.keyword == keyword
                        )
                    )
                    if not keyword_exists.scalar_one_or_none():
                        await event.respond(f"错误: 关键词 '{keyword}' 不存在，请先添加关键词")
                        return

                    # 创建转发规则
                    rule = ForwardRule(
                        account_id=self.db_account.id,
                        keyword=keyword,
                        target_chat_id=target_chat_id,
                        is_active=True
                    )
                    session.add(rule)
                    await session.commit()
                    await event.respond(f"已添加转发规则: {keyword} -> {target_chat_id}")

                elif action == "remove":
                    if len(args) != 2:
                        await event.respond("用法: /forwardrule remove <规则ID>")
                        return

                    rule_id = int(args[1])
                    result = await session.execute(
                        select(ForwardRule).where(
                            ForwardRule.account_id == self.db_account.id,
                            ForwardRule.id == rule_id
                        )
                    )
                    rule = result.scalar_one_or_none()
                    if not rule:
                        await event.respond(f"错误: 规则ID {rule_id} 不存在")
                        return

                    await session.delete(rule)
                    await session.commit()
                    await event.respond(f"已删除转发规则: {rule.keyword} -> {rule.target_chat_id}")

                elif action == "list":
                    result = await session.execute(
                        select(ForwardRule).where(
                            ForwardRule.account_id == self.db_account.id
                        ).order_by(ForwardRule.id)
                    )
                    rules = result.scalars().all()

                    if not rules:
                        await event.respond("当前没有转发规则")
                        return

                    response = "当前转发规则:\n"
                    for rule in rules:
                        status = "启用" if rule.is_active else "禁用"
                        response += f"ID: {rule.id} | 关键词: {rule.keyword} | 目标: {rule.target_chat_id} | 状态: {status}\n"
                    await event.respond(response)

                else:
                    await event.respond("未知操作，可用操作: add, remove, list")

        except Exception as e:
            logger.error(f"处理转发规则命令时出错: {str(e)}")
            await event.respond(f"处理命令时出错: {str(e)}")
    
    async def handle_account_command(self, event):
        """Handle account status command"""
        if not event.is_private or not await self.check_admin(event):
            return
        
        try:
            db = SessionLocal()
            
            # 显示当前账户状态
            response = f"*Account Status:*\n\n"
            response += f"Name: {self.name}\n"
            response += f"Session: {self.config['session_name']}\n"
            response += f"Status: {'Active' if self.db_account.is_active else 'Inactive'}\n"
            response += f"Created: {self.db_account.created_at.strftime('%Y-%m-%d %H:%M:%S')}\n"
            
            # 统计信息
            message_count = db.query(Message).filter(
                Message.account_id == self.db_account.id
            ).count()
            keyword_count = db.query(Keyword).filter(
                Keyword.account_id == self.db_account.id
            ).count()
            rule_count = db.query(ForwardRule).filter(
                ForwardRule.account_id == self.db_account.id
            ).count()
            
            response += f"\n*Statistics:*\n"
            response += f"Messages: {message_count}\n"
            response += f"Keywords: {keyword_count}\n"
            response += f"Forward Rules: {rule_count}\n"
            
            # 监控的聊天列表
            monitored_chats = self.config['monitoring']['enabled_chats']
            response += f"\n*Monitored Chats:* {len(monitored_chats)}\n"
            for chat_id in monitored_chats:
                response += f"- {chat_id}\n"
            
            await event.respond(response, parse_mode='markdown')
            db.close()
                
        except Exception as e:
            self.logger.error(f"Error handling account command: {e}")
            await event.respond("Error processing command")

    async def handle_config_command(self, event):
        """处理配置命令"""
        if not event.is_private:
            return

        try:
            # 检查是否是管理员
            if event.sender_id not in self.config['admin_ids']:
                await event.respond("只有管理员可以使用此命令")
                return

            # 解析命令参数
            args = event.text.split()[1:]  # 去掉命令本身
            if not args:
                await event.respond(
                    "用法:\n"
                    "/config show - 显示当前配置\n"
                    "/config set <选项> <值> - 设置配置选项\n"
                    "可用选项:\n"
                    "- auto_forward_media: 是否自动转发媒体文件 (true/false)\n"
                    "- monitor_private_bots: 是否监控机器人私聊 (true/false)\n"
                    "- auto_download: 是否自动下载媒体文件 (true/false)"
                )
                return

            action = args[0].lower()
            if action == "show":
                # 显示当前配置
                response = "当前配置:\n"
                response += f"自动转发媒体文件: {self.config['monitoring']['auto_forward_media']}\n"
                response += f"监控机器人私聊: {self.config['monitoring']['monitor_private_bots']}\n"
                response += f"自动下载媒体文件: {self.config['storage']['auto_download']}\n"
                response += f"监控的机器人: {', '.join(self.config['monitoring']['bot_usernames']) or '所有机器人'}"
                await event.respond(response)

            elif action == "set":
                if len(args) != 3:
                    await event.respond("用法: /config set <选项> <值>")
                    return

                option = args[1].lower()
                value = args[2].lower()

                if value not in ['true', 'false']:
                    await event.respond("值必须是 true 或 false")
                    return

                value = value == 'true'

                if option == 'auto_forward_media':
                    self.config['monitoring']['auto_forward_media'] = value
                    await event.respond(f"已{'启用' if value else '禁用'}自动转发媒体文件")
                elif option == 'monitor_private_bots':
                    self.config['monitoring']['monitor_private_bots'] = value
                    await event.respond(f"已{'启用' if value else '禁用'}监控机器人私聊")
                elif option == 'auto_download':
                    self.config['storage']['auto_download'] = value
                    await event.respond(f"已{'启用' if value else '禁用'}自动下载媒体文件")
                else:
                    await event.respond("未知选项")

        except Exception as e:
            logger.error(f"处理配置命令时出错: {str(e)}")
            await event.respond(f"处理命令时出错: {str(e)}")

async def main():
    """Main function"""
    # Initialize all enabled accounts
    accounts = []
    for account_config in config['accounts']:
        if account_config['enabled']:
            account = BotAccount(account_config)
            if await account.initialize():
                accounts.append(account)
    
    if not accounts:
        logger.error("No accounts were successfully initialized")
        return
    
    logger.info(f"Successfully initialized {len(accounts)} accounts")
    
    # Keep the script running
    try:
        await asyncio.gather(*[account.client.run_until_disconnected() for account in accounts])
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    finally:
        # Disconnect all clients
        for account in accounts:
            await account.client.disconnect()

if __name__ == '__main__':
    asyncio.run(main()) 