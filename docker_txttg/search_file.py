import os
import math
import sqlite3
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

DB_PATH = './data/sent_files.db'
PAGE_SIZE = 10
BOT_USERNAME = None  # 由主程序注入

def set_bot_username(username):
    global BOT_USERNAME
    BOT_USERNAME = username

def search_files_by_name(keyword):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT file_id, file_path, tg_file_id FROM files WHERE file_path LIKE ? ORDER BY file_id DESC", (f"%{keyword}%",))
    results = c.fetchall()
    conn.close()
    return results

def build_search_keyboard(results, page, keyword):
    start = page * PAGE_SIZE
    end = start + PAGE_SIZE
    page_results = results[start:end]
    keyboard = []
    for file_id, file_path, tg_file_id in page_results:
        filename = os.path.basename(file_path)
        # 按钮 callback_data: sget|file_id
        keyboard.append([InlineKeyboardButton(filename, callback_data=f"sget|{file_id}")])
    # 分页按钮
    total_pages = math.ceil(len(results) / PAGE_SIZE)
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton('上一页', callback_data=f'spage|{keyword}|{page-1}'))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton('下一页', callback_data=f'spage|{keyword}|{page+1}'))
    if nav:
        keyboard.append(nav)
    return InlineKeyboardMarkup(keyboard)

async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT vip_level FROM users WHERE user_id=?', (user_id,))
    row = c.fetchone()
    conn.close()
    vip_level = row[0] if row else 0
    if vip_level < 3:
        await update.message.reply_text('只有VIP3及以上用户才能使用此命令。')
        return
    if not context.args:
        await update.message.reply_text('用法：/s <关键词>')
        return
    keyword = ' '.join(context.args)
    results = search_files_by_name(keyword)
    if not results:
        await update.message.reply_text('未找到相关文件。')
        return
    reply_markup = build_search_keyboard(results, 0, keyword)
    await update.message.reply_text(f'搜索结果，共{len(results)}个文件：', reply_markup=reply_markup)

async def search_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data.split('|')
    if data[0] == 'spage':
        keyword = data[1]
        page = int(data[2])
        results = search_files_by_name(keyword)
        reply_markup = build_search_keyboard(results, page, keyword)
        await query.edit_message_reply_markup(reply_markup=reply_markup)
    elif data[0] == 'sget':
        file_id = int(data[1])
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('SELECT tg_file_id, file_path FROM files WHERE file_id=?', (file_id,))
        row = c.fetchone()
        conn.close()
        if not row:
            await query.answer('文件不存在', show_alert=True)
            return
        tg_file_id, file_path = row
        try:
            # 判断 file_id 前缀类型
            if tg_file_id and (tg_file_id.startswith('BQAC') or tg_file_id.startswith('CAAC') or tg_file_id.startswith('HDAA')):
                await query.message.reply_document(tg_file_id, caption=f'文件tg_file_id: {tg_file_id}')
            elif tg_file_id and tg_file_id.startswith('BAAC'):
                await query.message.reply_video(tg_file_id, caption=f'文件tg_file_id: {tg_file_id}')
            elif tg_file_id and tg_file_id.startswith('AgAC'):
                await query.message.reply_photo(tg_file_id, caption=f'文件tg_file_id: {tg_file_id}')
            elif tg_file_id is None or tg_file_id == '':
                # 没有 file_id，直接发本地文件，需判断文件类型
                ext = os.path.splitext(file_path)[1].lower()
                if ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']:
                    with open(file_path, 'rb') as f:
                        msg = await query.message.reply_photo(f, caption='本地图片直传')
                        # 写入tg_file_id
                        new_file_id = msg.photo[-1].file_id if msg.photo else None
                elif ext in ['.mp4', '.mov', '.avi', '.mkv', '.webm']:
                    with open(file_path, 'rb') as f:
                        msg = await query.message.reply_video(f, caption='本地视频直传')
                        new_file_id = msg.video.file_id
                elif os.path.exists(file_path):
                    with open(file_path, 'rb') as f:
                        msg = await query.message.reply_document(f, caption='本地文件直传')
                        new_file_id = msg.document.file_id
                else:
                    await query.answer('文件丢失', show_alert=True)
                    return
                # 更新数据库
                if new_file_id:
                    conn = sqlite3.connect(DB_PATH)
                    c = conn.cursor()
                    c.execute('UPDATE files SET tg_file_id=? WHERE file_id=?', (new_file_id, file_id))
                    conn.commit()
                    conn.close()
            elif os.path.exists(file_path):
                ext = os.path.splitext(file_path)[1].lower()
                if ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']:
                    with open(file_path, 'rb') as f:
                        msg = await query.message.reply_photo(f, caption=f'文件tg_file_id: {tg_file_id}')
                        # 写入tg_file_id（如有变化）
                        new_file_id = msg.photo[-1].file_id if msg.photo else None
                elif ext in ['.mp4', '.mov', '.avi', '.mkv', '.webm']:
                    with open(file_path, 'rb') as f:
                        msg = await query.message.reply_video(f, caption=f'文件tg_file_id: {tg_file_id}')
                        new_file_id = msg.video.file_id
                else:
                    with open(file_path, 'rb') as f:
                        msg = await query.message.reply_document(f, caption=f'文件tg_file_id: {tg_file_id}')
                        new_file_id = msg.document.file_id
                # 更新数据库
                if new_file_id and new_file_id != tg_file_id:
                    conn = sqlite3.connect(DB_PATH)
                    c = conn.cursor()
                    c.execute('UPDATE files SET tg_file_id=? WHERE file_id=?', (new_file_id, file_id))
                    conn.commit()
                    conn.close()
            else:
                await query.answer('文件丢失', show_alert=True)
                return
        except Exception as e:
            await query.answer(f'发送失败: {e}', show_alert=True)
        await query.answer()

async def ss_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT vip_level FROM users WHERE user_id=?', (user_id,))
    row = c.fetchone()
    conn.close()
    vip_level = row[0] if row else 0
    if vip_level < 2:
        await update.message.reply_text('只有VIP2及以上用户才能使用此命令。')
        return
    if not context.args:
        await update.message.reply_text('用法：/ss <关键词>')
        return
    keyword = ' '.join(context.args)
    results = search_files_by_name(keyword)
    if not results:
        await update.message.reply_text('未找到相关文件。')
        return
    links = []
    for idx, (file_id, file_path, tg_file_id) in enumerate(results, 1):
        filename = os.path.basename(file_path)
        link = f'https://t.me/{BOT_USERNAME}?start=book_{file_id}'
        links.append(f'{idx}. <a href="{link}">{filename}</a>')
    msg = f'搜索结果，共{len(results)}个文件：\n' + '\n'.join(links)
    await update.message.reply_text(msg, parse_mode='HTML', disable_web_page_preview=True)
