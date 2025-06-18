from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from utils.db import SessionLocal, UploadedDocument
from config import ADMIN_IDS
import os
from datetime import datetime

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理文档上传"""
    user_id = update.effective_user.id
    
    # 获取文件信息
    document = update.message.document
    file_name = document.file_name
    file_id = document.file_id
    
    # 下载文件
    file = await context.bot.get_file(file_id)
    download_path = f"uploads/{file_name}"
    os.makedirs("uploads", exist_ok=True)
    await file.download_to_drive(download_path)
    
    # 保存到数据库
    session = SessionLocal()
    doc = UploadedDocument(
        user_id=user_id,
        file_name=file_name,
        file_size=document.file_size,
        download_path=download_path,
        tg_file_id=file_id,
        status='pending',
        uploaded_at=datetime.now()
    )
    session.add(doc)
    session.commit()
    
    # 通知管理员
    keyboard = [
        [
            InlineKeyboardButton("✅ 批准", callback_data=f"doc_approve_{doc.id}"),
            InlineKeyboardButton("❌ 拒绝", callback_data=f"doc_reject_{doc.id}")
        ]
    ]
    
    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(
                chat_id=admin_id,
                text=f"新文件上传：\n用户：{user_id}\n文件名：{file_name}\n大小：{document.file_size} 字节",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except Exception as e:
            print(f"通知管理员 {admin_id} 失败：{str(e)}")
    
    await update.message.reply_text("文件已上传，等待管理员审核。")

async def handle_document_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理文档审核回调"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await query.message.reply_text("此操作仅限管理员使用！")
        return
    
    # 解析回调数据
    action, doc_id = query.data.split('_')[1:]
    doc_id = int(doc_id)
    
    # 更新文档状态
    session = SessionLocal()
    doc = session.query(UploadedDocument).filter_by(id=doc_id).first()
    if not doc:
        await query.message.reply_text("文档不存在！")
        return
    
    if action == 'approve':
        doc.status = 'approved'
        await query.message.reply_text(f"已批准文件：{doc.file_name}")
        # 通知用户
        try:
            await context.bot.send_message(
                chat_id=doc.user_id,
                text=f"您的文件 {doc.file_name} 已通过审核！"
            )
        except Exception as e:
            print(f"通知用户 {doc.user_id} 失败：{str(e)}")
    else:
        doc.status = 'rejected'
        await query.message.reply_text(f"已拒绝文件：{doc.file_name}")
        # 通知用户
        try:
            await context.bot.send_message(
                chat_id=doc.user_id,
                text=f"您的文件 {doc.file_name} 未通过审核。"
            )
        except Exception as e:
            print(f"通知用户 {doc.user_id} 失败：{str(e)}")
    
    session.commit()

async def batch_approve_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理批量批准命令"""
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("此命令仅限管理员使用！")
        return
    
    # 获取所有待审核文件
    session = SessionLocal()
    pending_docs = session.query(UploadedDocument).filter_by(status='pending').all()
    
    if not pending_docs:
        await update.message.reply_text("没有待审核的文件！")
        return
    
    # 批量批准
    for doc in pending_docs:
        doc.status = 'approved'
        try:
            await context.bot.send_message(
                chat_id=doc.user_id,
                text=f"您的文件 {doc.file_name} 已通过审核！"
            )
        except Exception as e:
            print(f"通知用户 {doc.user_id} 失败：{str(e)}")
    
    session.commit()
    await update.message.reply_text(f"已批量批准 {len(pending_docs)} 个文件！") 