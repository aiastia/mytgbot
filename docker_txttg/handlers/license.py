from telegram import Update
from telegram.ext import ContextTypes
from utils.db import SessionLocal, User
from config import ADMIN_IDS

async def redeem_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理兑换码命令"""
    user_id = update.effective_user.id
    
    # 获取兑换码
    if not context.args:
        await update.message.reply_text("请提供兑换码！")
        return
    
    code = context.args[0]
    
    # 验证兑换码
    if code == "VIP1":  # 示例兑换码
        # 获取用户信息
        session = SessionLocal()
        user = session.query(User).filter_by(user_id=user_id).first()
        if not user:
            user = User(user_id=user_id)
            session.add(user)
        
        # 设置VIP等级
        user.vip_level = 1
        session.commit()
        
        await update.message.reply_text("兑换成功！您已获得VIP1权限。")
    else:
        await update.message.reply_text("无效的兑换码！") 