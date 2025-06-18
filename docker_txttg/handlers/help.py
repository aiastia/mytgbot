from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """🤖 <b>机器人使用指南</b>

<b>基础命令：</b>
/start - 开始使用机器人
/help - 显示此帮助信息
/user - 查看个人统计信息
/stats - 查看已接收文件数量

<b>文件相关：</b>
/random - 随机获取一个文件
/search - 搜索文件
/s - 搜索文件（快捷命令）
/getfile - 通过文件ID获取文件
/hot - 查看热门文件排行榜

<b>VIP系统：</b>
/checkin - 每日签到获取积分
/points - 查看积分和兑换VIP
/ss - 高级搜索（仅VIP可用）
/redeem - 兑换积分码

<b>VIP等级说明：</b>
VIP0 - 每日限制10个文件
VIP1 - 每日限制30个文件
VIP2 - 每日限制50个文件
VIP3 - 每日限制100个文件

<b>管理员命令：</b>
/reload - 重新加载文件列表
/setvip - 设置用户VIP状态
/setviplevel - 设置用户VIP等级
/batchapprove - 批量批准上传的文件
<b>使用提示：</b>
• 每日签到可获得1-5积分
• 文件评分可帮助其他用户找到优质内容
• VIP等级越高，每日可获取的文件数量越多

如有问题，请联系管理员。"""

    # 创建购买积分的按钮
    keyboard = [
        [InlineKeyboardButton("💎 购买积分", url="https://t.me/iDataRiver_Bot?start=M_685017ebfaa790cf11d677bd")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(help_text, parse_mode='HTML', reply_markup=reply_markup)