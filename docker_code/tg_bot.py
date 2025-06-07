import re
import sqlite3
import os
from datetime import datetime
import tempfile
from pathlib import Path
from functools import wraps
from telegram import Update
from telegram.ext import Application, ApplicationBuilder, CommandHandler, MessageHandler, filters, CallbackContext

# 加载.env文件（如果存在）
env_path = Path('.env')
if env_path.exists():
    print("从.env文件加载配置...")
    with env_path.open() as f:
        for line in f:
            if line.strip() and not line.startswith('#'):
                key, value = line.strip().split('=', 1)
                os.environ[key] = value

# 管理员ID列表
ADMIN_IDS = [int(x) for x in os.environ.get('ADMIN_IDS', '12345678').split(',') if x.strip().isdigit()]
print(f"管理员ID列表: {ADMIN_IDS}")
# 管理员权限检查装饰器
def admin_only(func):
    @wraps(func)
    async def wrapped(update: Update, context: CallbackContext, *args, **kwargs):
        user_id = update.effective_user.id
        if user_id not in ADMIN_IDS:
            await update.message.reply_text("此命令仅限管理员使用。")
            return
        return await func(update, context, *args, **kwargs)
    return wrapped

# 初始化 SQLite 数据库
conn = sqlite3.connect('./data/messages.db', check_same_thread=False)
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                content TEXT,
                type TEXT,
                created_at TEXT,
                UNIQUE(user_id, content)
            )''')
c.execute('''CREATE TABLE IF NOT EXISTS user_status (
                user_id INTEGER PRIMARY KEY,
                last_send_time TEXT
            )''')
conn.commit()

# 提取消息的正则表达式
PATTERN = re.compile(r'(?:'
    r'@(?:FilesPan1Bot|MediaBK5Bot|FilesDrive_BLGA_bot)\s+[^\s]+.*'
    r'|showfilesbot_\d+[PpvVdD]_[A-Za-z0-9_\-\+]+'
    r'|(?:vi|pk|[dvp])_(?:FilesPan1Bot_)?[A-Za-z0-9_\-\+]+'
    r'|[A-Za-z0-9_\-\+]+=[^=\s]*?(?:_grp|_mda)(?=[\s\u4e00-\u9fa5]|$)'
    r'|@filepan_bot:([A-Za-z0-9_\-\+]+)'
    r')', re.IGNORECASE)

# 提取消息内容
def extract_messages(text):
    matches = []
    for m in PATTERN.finditer(text):
        match = m.group(0)
        if match.endswith('_grp') or match.endswith('_mda'):
            # 对于 grp/mda 结尾的，只保留到 _grp/_mda
            end_pos = match.find('_grp')
            if end_pos == -1:
                end_pos = match.find('_mda')
            if end_pos != -1:
                match = match[:end_pos + 4]  # +4 包含 _grp 或 _mda
        matches.append(match)
    return matches

# 处理普通消息
async def handle_message(update: Update, context: CallbackContext):
    text = update.message.text
    message_id = update.message.message_id
    extracted = extract_messages(text)
    if extracted:
        user_id = update.effective_user.id
        from datetime import datetime
        now = datetime.now().isoformat(sep=' ', timespec='seconds')
        saved_count = 0
        for message in set(extracted):            # 检查bot出现次数
            bot_count = 0
            if '@FilesDrive_BLGA_bot' in message:
                bot_count += 1
            if '@FilesPan1Bot' in message:
                bot_count += 1
            if '@MediaBK5Bot' in message:
                bot_count += 1
            if '@filepan_bot:' in message:
                bot_count += 1
            # 如果发现多个bot，跳过此消息
            if bot_count > 1:
                continue
                
            # 单个bot的情况
            if '@FilesDrive_BLGA_bot' in message:
                message_type = 'filesdrive'
            elif '@FilesPan1Bot' in message:
                message_type = 'filespan1'
            elif '@MediaBK5Bot' in message:
                message_type = 'mediabk5'
            elif '@filepan_bot:' in message:
                message_type = 'filepan_bot'
            # 匹配 showfilesbot
            elif message.startswith('showfilesbot_'):
                message_type = 'showfilesbot-code'
            # 匹配老版本格式
            elif message.startswith(('vi_', 'pk_')):
                message_type = message[:2] + '_old'
            # 匹配新版本格式
            elif message.startswith(('d_', 'v_', 'p_')):
                if 'FilesPan1Bot_' in message:
                    message_type = 'filespan1bot_' + message[0]
                else:
                    message_type = message[0] + '_new'
            # 匹配 mediabk5bot
            elif message.endswith(('_grp', '_mda')):
                message_type = 'mediabk5bot'
            else:
                continue  # 对于无法识别的类型，跳过不保存
                
            try:
                c.execute('INSERT INTO messages (user_id, content, type, created_at) VALUES (?, ?, ?, ?)', 
                         (user_id, message, message_type, now))
                conn.commit()
                saved_count += 1
            except sqlite3.IntegrityError:
                pass  # 忽略重复内容
        context.user_data['save_count'] = context.user_data.get('save_count', 0) + saved_count
        await update.message.reply_text(f"提取到以下内容：\n{chr(10).join(extracted)}", reply_to_message_id=message_id)
    else:
        await update.message.reply_text("未找到可提取的内容。", reply_to_message_id=message_id)

# 保存消息到数据库
async def save_messages(update: Update, context: CallbackContext):
    save_count = context.user_data.get('save_count', 0)
    await update.message.reply_text(f"成功保存 {save_count} 条消息。")
    context.user_data['save_count'] = 0

# 发送消息
async def send_messages(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    from datetime import datetime
    now = datetime.now().isoformat(sep=' ', timespec='seconds')
    # 获取上次发送时间
    c.execute('SELECT last_send_time FROM user_status WHERE user_id = ?', (user_id,))
    row = c.fetchone()
    last_send_time = row[0] if row and row[0] else None
    if last_send_time:
        c.execute('SELECT content, type, created_at FROM messages WHERE user_id = ? AND created_at > ? ORDER BY created_at', (user_id, last_send_time))
    else:
        c.execute('SELECT content, type, created_at FROM messages WHERE user_id = ? ORDER BY created_at', (user_id,))
    rows = c.fetchall()

    if not rows:
        await update.message.reply_text("没有可发送的内容。")
        # 也要更新 last_send_time，避免重复发送
        c.execute('INSERT OR REPLACE INTO user_status (user_id, last_send_time) VALUES (?, ?)', (user_id, now))
        conn.commit()
        return

    # 按类型分组
    grouped_messages = {}
    total_length = 0
    for content, msg_type, created_at in rows:
        if msg_type not in grouped_messages:
            grouped_messages[msg_type] = []
        grouped_messages[msg_type].append((content, created_at))
        total_length += len(content) + 1  # +1 for newline

    # 如果内容总长度超过4000字符，使用文件发送
    if total_length > 4000:
        # 创建临时文件
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt', encoding='utf-8') as tmp:
            tmp.write(f"导出时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            tmp.write(f"总消息数：{len(rows)}\n\n")
            
            # 写入分组消息
            for msg_type, messages in grouped_messages.items():
                tmp.write(f"\n=== {msg_type} (共 {len(messages)} 条) ===\n")
                for content, created_at in messages:
                    tmp.write(f"{created_at}: {content}\n")
                tmp.write("\n")

        # 发送文件
        with open(tmp.name, 'rb') as file:
            await update.message.reply_document(
                document=file,
                filename=f"new_messages_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                caption="这是您的新消息"
            )
        
        # 删除临时文件
        os.unlink(tmp.name)
    else:
        # 内容不多时，直接发送消息
        for msg_type, messages in grouped_messages.items():
            contents = [f"{created_at}: {content}" for content, created_at in messages]
            await update.message.reply_text(f"类型：{msg_type}\n{chr(10).join(contents)}")

    # 更新 last_send_time
    c.execute('INSERT OR REPLACE INTO user_status (user_id, last_send_time) VALUES (?, ?)', (user_id, now))
    conn.commit()

# 发送所有消息为文件
async def send_all_messages(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    
    # 获取该用户的所有消息
    c.execute('SELECT content, type, created_at FROM messages WHERE user_id = ? ORDER BY created_at', (user_id,))
    rows = c.fetchall()

    if not rows:
        await update.message.reply_text("没有保存的消息。")
        return

    # 创建临时文件
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt', encoding='utf-8') as tmp:
        tmp.write(f"导出时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        tmp.write(f"总消息数：{len(rows)}\n\n")
        
        # 按类型分组
        grouped_messages = {}
        for content, msg_type, created_at in rows:
            if msg_type not in grouped_messages:
                grouped_messages[msg_type] = []
            grouped_messages[msg_type].append((content, created_at))

        # 写入分组消息
        for msg_type, messages in grouped_messages.items():
            tmp.write(f"\n=== {msg_type} (共 {len(messages)} 条) ===\n")
            for content, created_at in messages:
                tmp.write(f"{created_at}: {content}\n")
            tmp.write("\n")

    # 发送文件
    with open(tmp.name, 'rb') as file:
        await update.message.reply_document(
            document=file,
            filename=f"messages_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
            caption="这是您保存的所有消息"
        )
    
    # 删除临时文件
    os.unlink(tmp.name)

@admin_only
async def get_user_stats(update: Update, context: CallbackContext) -> None:
    """获取所有用户的统计信息"""
    conn = sqlite3.connect('data/messages.db')
    cursor = conn.cursor()
    
    try:
        # 获取用户统计数据
        cursor.execute("""
            SELECT user_id, COUNT(*) as message_count 
            FROM messages 
            GROUP BY user_id
        """)
        stats = cursor.fetchall()
        
        if not stats:
            await update.message.reply_text("目前还没有任何用户数据。")
            return
            
        response = "用户统计信息：\n\n"
        for user_id, count in stats:
            response += f"用户 ID: {user_id}\n消息数量: {count}\n\n"
            
        await update.message.reply_text(response)
    
    finally:
        conn.close()

@admin_only
async def get_user_messages(update: Update, context: CallbackContext) -> None:
    """获取指定用户的消息历史"""
    args = context.args
    if not args:
        await update.message.reply_text("请提供用户ID。\n用法: /user_messages <用户ID> [YYYY-MM-DD]")
        return
        
    try:
        user_id = int(args[0])
        date_filter = None
        if len(args) > 1:
            try:
                date_filter = datetime.strptime(args[1], "%Y-%m-%d")
            except ValueError:
                await update.message.reply_text("日期格式无效。请使用 YYYY-MM-DD 格式。")
                return
    except ValueError:
        await update.message.reply_text("无效的用户ID。请提供一个数字ID。")
        return
        
    conn = sqlite3.connect('data/messages.db')
    cursor = conn.cursor()
    
    try:
        if date_filter:
            cursor.execute("""
                SELECT content, created_at
                FROM messages
                WHERE user_id = ? AND date(created_at) = date(?)
                ORDER BY created_at DESC
            """, (user_id, date_filter.strftime("%Y-%m-%d")))
        else:
            cursor.execute("""
                SELECT content, created_at
                FROM messages
                WHERE user_id = ?
                ORDER BY created_at DESC LIMIT 10
            """, (user_id,))
            
        messages = cursor.fetchall()
        
        if not messages:
            await update.message.reply_text(f"未找到用户 {user_id} 的消息记录。")
            return
        response = f"用户 {user_id} 的消息历史：\n\n"
        for msg_text, created_at in messages:
            dt = datetime.fromisoformat(created_at)
            response += f"{dt.strftime('%Y-%m-%d %H:%M:%S')}: {msg_text}\n\n"
            
        await update.message.reply_text(response)
    
    finally:
        conn.close()

# 启动 Bot
def main():
    # 从环境变量获取 Bot Token
    bot_token = os.environ.get('BOT_TOKEN')
    print(f"使用的 BOT_TOKEN: {bot_token}")
    if not bot_token:
        print("错误：未设置 BOT_TOKEN 环境变量")
        return

    application = ApplicationBuilder().token(bot_token).build()

    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(CommandHandler("save", save_messages))
    application.add_handler(CommandHandler("send", send_messages))
    application.add_handler(CommandHandler("all", send_all_messages))
    application.add_handler(CommandHandler("send_all", send_all_messages))
    application.add_handler(CommandHandler("users", get_user_stats))
    application.add_handler(CommandHandler("user_messages", get_user_messages))
    application.add_handler(CommandHandler("user_message", get_user_messages))  # 添加不带s的别名命令

    application.run_polling()

if __name__ == '__main__':
    main()
