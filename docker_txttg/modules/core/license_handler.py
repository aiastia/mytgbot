import os
import requests
from datetime import datetime
from modules.db.orm_utils import SessionLocal
from modules.db.orm_models import User, LicenseCode
from dotenv import load_dotenv
from modules.config.config import API_BASE_URL, API_KEY, REDEM_URL
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
# 加载环境变量
# load_dotenv()

# # API Configuration from environment variables
# API_BASE_URL = os.getenv('IDATARIVER_API_URL', 'https://open.idatariver.com/mapi')
# API_KEY = os.getenv('IDATARIVER_API_KEY')

if not API_KEY:
    raise ValueError("IDATARIVER_API_KEY environment variable is not set")

def query_license(code):
    """Query license code status"""
    headers = {
        "Authorization": f"Bearer {API_KEY}"
    }
    url = f"{API_BASE_URL}/license/query"
    params = {"code": code}
    
    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        return {"error": str(e)}

def activate_license(code):
    """Activate license code"""
    headers = {
        "Authorization": f"Bearer {API_KEY}"
    }
    url = f"{API_BASE_URL}/license/activate"
    data = {"code": code}
    
    try:
        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        return {"error": str(e)}

def redeem_license_code(user_id, code):
    """Redeem a license code and add points to user"""
    # First check if code was already used
    with SessionLocal() as session:
        existing_code = session.query(LicenseCode).filter_by(code=code).first()
        if existing_code:
            return False, "此兑换码已被使用"
        
        # Query license status
        license_info = query_license(code)
        if "error" in license_info:
            return False, f"查询兑换码失败: {license_info['error']}"
        
        if not license_info.get("result", {}).get("items"):
            return False, "无效的兑换码"
        
        license_item = license_info["result"]["items"][0]
        status = license_item["status"]
        
        # 检查兑换码状态
        if status == "USED":
            return False, "此兑换码已被使用"
        elif status != "VALID":
            return False, f"此兑换码状态无效: {status}"
        
        # Get points value from states
        try:
            points = int(license_item.get("states", "0"))
            if points <= 0:
                return False, "无效的积分值"
        except (ValueError, TypeError):
            return False, "无法获取积分值"
        
        # Activate the license
        activation_result = activate_license(code)
        if "error" in activation_result:
            return False, f"激活兑换码失败: {activation_result['error']}"
        
        # Add points to user
        user = session.query(User).filter_by(user_id=user_id).first()
        if not user:
            user = User(user_id=user_id, points=0)
            session.add(user)
        
        user.points += points
        
        # Record the used code
        used_code = LicenseCode(
            code=code,
            user_id=user_id,
            points=points,
            redeemed_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            license_info=str(license_item)
        )
        session.add(used_code)
        
        try:
            session.commit()
            return True, f"成功兑换 {points} 积分"
        except Exception as e:
            session.rollback()
            return False, f"兑换失败: {str(e)}"

async def redeem_command(update, context):
    """Handle /redeem command"""
    if not context.args:
        help_text = (
            "📝 用法: /redeem <code>兑换码</code>\n"
            "例如: /redeem ABC123\n\n"
            "🔑 没有兑换码？点击下方按钮购买"
        )
        keyboard = [
            [InlineKeyboardButton("💎 购买兑换码", url=REDEM_URL)]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(help_text, parse_mode='HTML', reply_markup=reply_markup)
        return
    
    code = context.args[0].strip()
    user_id = update.effective_user.id
    
    success, message = redeem_license_code(user_id, code)
    await update.message.reply_text(message) 

    