# Telegram Media Monitoring Bot

A Telegram bot built with Telethon that monitors messages, downloads media, and forwards content based on keywords.

## Features

- Monitor messages in groups, channels, and private chats
- Download media files (images, videos, documents)
- Keyword-based monitoring with regex support
- Message forwarding system
- SQLite database for message storage
- Command-based control system
- Proxy support (SOCKS5/HTTP)

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Configure the bot:
   - Edit `config.yaml` and add your Telegram API credentials:
     ```yaml
     api_id: "your_api_id"
     api_hash: "your_api_hash"
     ```
   - Configure proxy settings (if needed):
     ```yaml
     proxy:
       enabled: true
       type: "socks5"  # or "http"
       host: "127.0.0.1"
       port: 7890
       username: ""  # Optional
       password: ""  # Optional
     ```

3. Create required directories:
```bash
mkdir -p storage/downloads
```

4. Run the bot:
```bash
python main.py
```

## Commands

The bot supports the following commands (admin only):

- `/watch enable <chat_id>` - Start monitoring a chat
- `/watch disable <chat_id>` - Stop monitoring a chat
- `/keywords add <pattern>` - Add a keyword to monitor
- `/keywords remove <id>` - Remove a keyword by ID

## Database

The bot uses SQLite with SQLAlchemy ORM. The database file will be created automatically as `bot.db`.

## Configuration

Edit `config.yaml` to customize:
- API credentials
- Proxy settings
- Database settings
- Storage options
- Monitoring settings
- Forwarding rules

## Security

- Keep your API credentials secure
- Only share the bot with trusted users
- Monitor the bot's activity regularly
- Use secure proxy settings if needed 