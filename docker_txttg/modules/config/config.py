import os
from dotenv import load_dotenv

# 加载.env文件
load_dotenv()

# 从环境变量读取配置
TOKEN = os.getenv('BOT_TOKEN')
# 管理员用户ID列表
ADMIN_USER_ID = [int(id) for id in os.getenv('ADMIN_USER_ID', '').split(',') if id]
TXT_ROOT = os.getenv('TXT_ROOT', '/app/share_folder')
# 上传目录
UPLOAD_DIR = os.getenv('UPLOAD_DIR', './uploads')
TELEGRAM_API_URL = os.getenv('TELEGRAM_API_URL')
TXT_EXTS = [x.strip() for x in os.getenv('TXT_EXTS', '.txt,.pdf').split(',') if x.strip()]
ALLOWED_EXTENSIONS = {'.txt', '.epub', '.pdf', '.mobi'}
# 下载目录
DOWNLOAD_DIR = os.path.join(os.getenv('TXT_ROOT', '/app/share_folder'), 'downloaded_docs').replace('\\', '/')

API_BASE_URL = os.getenv('IDATARIVER_API_URL', 'https://open.idatariver.com/mapi')
API_KEY = os.getenv('IDATARIVER_API_KEY')
PAGE_SIZE = int(os.getenv('PAGE_SIZE', 10))  # 每页显示的结果数量

# 数据库配置
DB_TYPE = os.getenv('DB_TYPE', 'sqlite')
DB_USER = os.getenv('DB_USER', 'root')
DB_PASS = os.getenv('DB_PASS', '')
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_NAME = os.getenv('DB_NAME', 'test')
DB_PATH = os.getenv('DB_PATH', './data/sent_files.db')

# 根据数据库类型构建数据库URL
if DB_TYPE == 'sqlite':
    DATABASE_URL = f'sqlite:///{DB_PATH}'
else:
    DATABASE_URL = f'mysql+pymysql://{DB_USER}:{DB_PASS}@{DB_HOST}/{DB_NAME}'

# 超时配置（这些是固定值，不需要从环境变量读取）
CONNECT_TIMEOUT = 60
READ_TIMEOUT = 1810
WRITE_TIMEOUT = 1810
POOL_TIMEOUT = 60
MEDIA_WRITE_TIMEOUT = 1810

# VIP套餐配置
VIP_DAYS = [3, 7, 30, 90, 180, 365]  # 所有有效的VIP套餐天数

# VIP套餐配置
VIP_PACKAGES = [
    # 格式: (等级, 天数, 积分, 描述)
    # 短期套餐
    (1, 3, 15, "3天VIP1"),
    (1, 7, 35, "7天VIP1"),
    
    # 月度套餐
    (1, 30, 120, "30天VIP1"),
    (2, 30, 240, "30天VIP2"),
    (3, 30, 400, "30天VIP3"),
    
    # 季度套餐
    (1, 90, 300, "90天VIP1"),
    (2, 90, 600, "90天VIP2"),
    (3, 90, 1000, "90天VIP3"),
    
    # 半年套餐
    (1, 180, 500, "180天VIP1"),
    (2, 180, 1000, "180天VIP2"),
    (3, 180, 1800, "180天VIP3"),
    
    # 年度套餐
    (1, 365, 1000, "365天VIP1"),
    (2, 365, 2000, "365天VIP2"),
    (3, 365, 3500, "365天VIP3"),
] 

