from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from modules.config.config import REDEM_URL

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = get_help_text()
    keyboard = [
        [InlineKeyboardButton("💎 购买积分", url=REDEM_URL)]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(help_text, parse_mode='HTML', reply_markup=reply_markup)


def get_help_text():
    sections = {
        "header": (
            "🤖 <b>机器人使用指南</b>\n"
        ),
        
        "basic_commands": (
            "\n<b>基础命令：</b>\n"
            "    /start - 开始使用机器人\n"
            "    /help - 显示此帮助信息\n"
            "    /user - 查看个人统计信息\n"
            "    /stats - 查看已接收文件数量\n"
        ),
        
        "file_commands": (
            "\n<b>文件相关：</b>\n"
            "    /random - 随机获取一个文件\n"
            "    /search - 搜索文件\n"
            "    /getfile - 通过文件ID获取文件\n"
            "    /hot - 查看热门文件排行榜\n"
        ),
        
        "vip_commands": (
            "\n<b>VIP系统：</b>\n"
            "    /checkin - 每日签到获取积分\n"
            "    /points - 查看积分和兑换VIP\n"
            "    /s - 搜索文件（仅VIP2可用）\n"
            "    /ss - 高级搜索（仅VIP3可用）\n"
            "    /redeem - 兑换积分码\n"
        ),
        
        "vip_levels": (
            "\n<b>VIP等级说明：</b>\n"
            "    VIP0 - 每日限制10个文件\n"
            "    VIP1 - 每日限制30个文件\n"
            "    VIP2 - 每日限制50个文件\n"
            "    VIP3 - 每日限制100个文件\n"
        ),
        
        "admin_commands": (
            "\n<b>管理员命令：</b>\n"
            "    /reload - 重新加载文件列表\n"
            "    /setvip - 设置用户VIP状态\n"
            "    /setviplevel - 设置用户VIP等级\n"
            "    /batchapprove - 批量批准上传的文件\n"
            "    /download_pending - 批量下载的文件\n"
            "    /list_pending - 显示文件清单\n"
        ),
        
        "tips": (
            "\n<b>使用提示：</b>\n"
            "    • 每日签到可获得1-5积分\n"
            "    • 文件评分可帮助其他用户找到优质内容\n"
            "    • VIP等级越高，每日可获取的文件数量越多\n"
            "\n如有问题，请联系管理员。"
        )
    }
    
    return "".join(sections.values())