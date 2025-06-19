from docker_txttg.modules.db_utils import *
from orm_utils import SessionLocal
from orm_models import User
from telegram import Update
from telegram.ext import ContextTypes
from datetime import datetime, timedelta
from docker_txttg.modules.config import ADMIN_USER_ID
async def setvip_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN_USER_ID:
        await update.message.reply_text('无权限，仅管理员可用。')
        return
    if len(context.args) != 3:
        await update.message.reply_text('用法：/setvip <user_id> <0/1/2/3> <天数>')
        return
    try:
        target_id = int(context.args[0])
        vip_level = int(context.args[1])
        days = int(context.args[2])
        if vip_level not in (0, 1, 2, 3):
            raise ValueError
        if days <= 0:
            raise ValueError
    except Exception:
        await update.message.reply_text('参数错误。')
        return
    with SessionLocal() as session:
        user = session.query(User).filter_by(user_id=target_id).first()
        if not user:
            await update.message.reply_text('用户不存在。')
            return
        now = datetime.now()
        new_expiry_date = (now + timedelta(days=days)).strftime('%Y-%m-%d')
        if vip_level > 0:
            if not user.vip_date:
                user.vip_date = now.strftime('%Y-%m-%d')
            if user.vip_level > 0 and user.vip_expiry_date:
                current_expiry = datetime.strptime(user.vip_expiry_date, '%Y-%m-%d')
                new_expiry = datetime.strptime(new_expiry_date, '%Y-%m-%d')
                if current_expiry < new_expiry:
                    user.vip_expiry_date = new_expiry_date
                    await update.message.reply_text(f'用户 {target_id} VIP等级已设置为 {vip_level}，有效期更新为 {days} 天')
                else:
                    await update.message.reply_text(f'用户 {target_id} VIP等级已设置为 {vip_level}，保持原到期时间不变')
            else:
                user.vip_expiry_date = new_expiry_date
                await update.message.reply_text(f'用户 {target_id} VIP等级已设置为 {vip_level}，有效期 {days} 天')
            user.vip_level = vip_level
        else:
            user.vip_level = 0
            user.vip_expiry_date = None
            await update.message.reply_text(f'用户 {target_id} VIP状态已取消')
        session.commit()

async def setviplevel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN_USER_ID:
        await update.message.reply_text('无权限，仅管理员可用。')
        return
    if len(context.args) != 2:
        await update.message.reply_text('用法：/setviplevel <user_id> <0/1/2/3>')
        return
    try:
        target_id = int(context.args[0])
        vip_level = int(context.args[1])
        if vip_level not in (0, 1, 2, 3):
            raise ValueError
    except Exception:
        await update.message.reply_text('参数错误。')
        return
    with SessionLocal() as session:
        user = session.query(User).filter_by(user_id=target_id).first()
        if not user:
            await update.message.reply_text('用户不存在。')
            return
        if user.vip_level > 0 and user.vip_expiry_date:
            expiry_date = datetime.strptime(user.vip_expiry_date, '%Y-%m-%d')
            remaining_days = (expiry_date - datetime.now()).days
            if remaining_days >= 30:
                user.vip_level = vip_level
                session.commit()
                await update.message.reply_text(f'用户 {target_id} VIP等级已更新为 {vip_level}，过期时间保持不变')
                return
    set_user_vip_level(target_id, vip_level)
    await update.message.reply_text(f'用户 {target_id} VIP等级已设置为 {vip_level}')
