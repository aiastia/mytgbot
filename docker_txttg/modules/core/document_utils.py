from telegram import InlineKeyboardButton, InlineKeyboardMarkup

def format_document_list_message(docs, page, total_pages, total_count):
    msg = f"📥 <b>待下载文件列表</b> (第{page}/{total_pages}页)\n"
    msg += f"共{total_count}个文件待下载\n\n"
    for doc in docs:
        size_mb = doc.file_size / (1024 * 1024)
        status = "✅ 可下载" if size_mb < 20 else "❌ 过大"
        msg += (
            f"ID: <code>{doc.id}</code>\n"
            f"📁 {doc.file_name}\n"
            f"📊 {size_mb:.1f}MB {status}\n"
            f"👤 上传者ID: {doc.user_id}\n"
            f"⏰ 上传时间: {doc.upload_time}\n"
            "------------------------\n"
        )
    return msg

def build_pagination_keyboard(page, total_pages):
    keyboard = []
    nav_buttons = []
    if page > 1:
        nav_buttons.append(InlineKeyboardButton("⬅️ 上一页", callback_data=f"pendinglist_{page-1}"))
    if page < total_pages:
        nav_buttons.append(InlineKeyboardButton("➡️ 下一页", callback_data=f"pendinglist_{page+1}"))
    if nav_buttons:
        keyboard.append(nav_buttons)
    keyboard.append([
        InlineKeyboardButton("🔄 刷新", callback_data=f"pendinglist_{page}"),
        InlineKeyboardButton("📥 下载当前页", callback_data=f"dlpending_{page}")
    ])
    return InlineKeyboardMarkup(keyboard)
