from telegram import Update
from telegram.ext import ContextTypes

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理帮助命令"""
    help_text = """
🤖 机器人使用指南：

📚 基本命令：
/start - 开始使用机器人
/help - 显示此帮助信息
/search <关键词> - 搜索文件
/ss <关键词> - 快速搜索文件
/random - 获取随机文件

📊 用户系统：
/checkin - 每日签到
/points - 查看积分
/redeem <兑换码> - 兑换积分

🔥 热门功能：
/hot - 查看热门文件

👑 VIP功能：
需要VIP1及以上等级才能使用搜索功能

❓ 其他说明：
- 每个用户每天最多发送5个文件
- 文件发送后会生成file_id，可以直接使用
- 上传的文件需要管理员审核
"""
    await update.message.reply_text(help_text) 