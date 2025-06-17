import os
import yaml
import logging
from telethon import TelegramClient, events
from telethon.tl.types import MessageMediaDocument, MessageMediaPhoto, MessageMediaWebPage
from db.base import init_db
from db.models import Message, Keyword, ForwardRule
from sqlalchemy.orm import Session
from db.base import SessionLocal
import re
import asyncio
from telethon.errors import SessionPasswordNeededError
from datetime import datetime, timedelta
import time
from sqlalchemy.exc import IntegrityError

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
    
    def setup_handlers(self):
        """Set up event handlers for this account"""
        @self.client.on(events.NewMessage)
        async def handle_new_message(event):
            await self.handle_message(event)
        
        @self.client.on(events.NewMessage(pattern='/watch'))
        async def handle_watch_command(event):
            await self.handle_watch_command(event)
        
        # Add other command handlers...
    
    async def handle_message(self, event):
        """Handle new messages for this account"""
        db = SessionLocal()
        try:
            # Check if chat is monitored
            if event.chat_id not in self.config['monitoring']['enabled_chats']:
                return

            # Check for media
            has_media = bool(event.message.media and not isinstance(event.message.media, MessageMediaWebPage))
            
            if has_media:
                try:
                    # Download media if enabled
                    file_path = await self.download_media(event.message, db)
                    
                    # Create message record
                    message = Message(
                        message_id=event.message.id,
                        chat_id=event.chat_id,
                        chat_title=getattr(event.chat, 'title', None),
                        sender_id=event.sender_id,
                        content=event.message.text,
                        media_type=type(event.message.media).__name__,
                        file_name=getattr(event.message.media, 'file_name', None),
                        file_path=file_path,
                        tg_file_id=getattr(event.message.media, 'id', None),
                        access_hash=getattr(event.message.media, 'access_hash', None)
                    )
                    
                    # Check keywords
                    matched_keywords = await self.check_keywords(event.message, db)
                    if matched_keywords:
                        message.detected_keywords = ','.join(matched_keywords)
                        
                        # Forward if rules exist
                        forward_rules = db.query(ForwardRule).filter(
                            ForwardRule.source_chat_id == event.chat_id,
                            ForwardRule.is_active == True
                        ).all()
                        
                        for rule in forward_rules:
                            if await self.forward_message(event.message, rule.target_user_id):
                                message.is_forwarded = True
                    
                    db.add(message)
                    db.commit()
                except IntegrityError:
                    db.rollback()
                    self.logger.info(f"Message {event.message.id} from chat {event.chat_id} already exists")
                except Exception as e:
                    self.logger.error(f"Error handling message: {e}")
                    db.rollback()
                
        except Exception as e:
            self.logger.error(f"Error in message handler: {e}")
        finally:
            db.close()
    
    async def download_media(self, message, db: Session):
        """Download media for this account"""
        if not self.config['storage']['auto_download']:
            return None
        
        try:
            # Generate unique filename
            timestamp = int(time.time())
            original_filename = getattr(message.media, 'file_name', f'file_{timestamp}')
            filename = self.config['storage']['file_naming'].format(
                chat_id=message.chat_id,
                message_id=message.id,
                timestamp=timestamp,
                filename=original_filename
            )
            
            # Ensure download directory exists
            os.makedirs(self.config['storage']['download_path'], exist_ok=True)
            
            path = await message.download_media(
                self.config['storage']['download_path'],
                file=filename
            )
            return path
        except Exception as e:
            self.logger.error(f"Error downloading media: {e}")
            return None
    
    async def forward_message(self, message, target_user_id):
        """Forward message for this account"""
        try:
            # Try direct forward first
            await self.client.forward_messages(target_user_id, message)
            return True
        except Exception as e:
            self.logger.error(f"Direct forward failed: {e}")
            
            if not self.config['forwarding']['fallback_to_upload']:
                return False
                
            try:
                # Download and re-upload
                if message.media:
                    path = await self.download_media(message, None)
                    if path:
                        await self.client.send_file(
                            target_user_id,
                            path,
                            caption=message.text
                        )
                        return True
            except Exception as e:
                self.logger.error(f"Fallback forward failed: {e}")
            
            return False
    
    async def check_keywords(self, message, db: Session):
        """Check keywords for this account"""
        matched_keywords = []
        keywords = db.query(Keyword).filter(Keyword.is_active == True).all()
        
        for keyword in keywords:
            if keyword.is_regex:
                try:
                    if re.search(keyword.pattern, message.text or ''):
                        matched_keywords.append(keyword.pattern)
                except re.error:
                    self.logger.error(f"Invalid regex pattern: {keyword.pattern}")
            else:
                if keyword.pattern in (message.text or ''):
                    matched_keywords.append(keyword.pattern)
        
        return matched_keywords

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