from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """🤖 <b>机器人使用指南</b>\n\n<b>基础命令：</b>\n/start - 开始使用机器人\n/help - 显示此帮助信息\n/user - 查看个人统计信息\n/stats - 查看已接收文件数量\n\n<b>文件相关：</b>\n/random - 随机获取一个文件\n/search - 搜索文件\n/s - 搜索文件（快捷命令）\n/getfile - 通过文件ID获取文件\n/hot - 查看热门文件排行榜\n\n<b>VIP系统：</b>\n/checkin - 每日签到获取积分\n/points - 查看积分和兑换VIP\n/ss - 高级搜索（仅VIP可用）\n/redeem - 兑换积分码\n\n<b>VIP等级说明：</b>\nVIP0 - 每日限制10个文件\nVIP1 - 每日限制30个文件\nVIP2 - 每日限制50个文件\nVIP3 - 每日限制100个文件\n\n<b>管理员命令：</b>\n/reload - 重新加载文件列表\n/setvip - 设置用户VIP状态\n/setviplevel - 设置用户VIP等级\n/batchapprove - 批量批准上传的文件\n<b>使用提示：</b>\n• 每日签到可获得1-5积分\n• 文件评分可帮助其他用户找到优质内容\n• VIP等级越高，每日可获取的文件数量越多\n\n如有问题，请联系管理员。"""
    keyboard = [
        [InlineKeyboardButton("💎 购买积分", url="https://t.me/iDataRiver_Bot?start=M_685017ebfaa790cf11d677bd")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(help_text, parse_mode='HTML', reply_markup=reply_markup)
