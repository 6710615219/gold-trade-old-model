import os
from dotenv import load_dotenv

# โหลดค่าจากไฟล์ .env
load_dotenv()

# 🎯 สร้างตัวแปรบังคับตำแหน่งไฟล์ ให้อยู่ในโฟลเดอร์เดียวกับ config.py (คือโฟลเดอร์ backend เสมอ)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# API Keys (ดึงจากตัวแปร Environment)
GROQ_API_KEYS = [
    os.getenv("GROQ_API_KEY_1", "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"),
    os.getenv("GROQ_API_KEY_2", "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"),
    os.getenv("GROQ_API_KEY_3", "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"),
    os.getenv("GROQ_API_KEY_4", "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"),
]
GROQ_API_KEYS = [k for k in GROQ_API_KEYS if k.strip() != ""]

ENABLE_UNIVERSITY_API = False
TEAM_API_KEY = os.getenv("TEAM_API_KEY", "")
LOG_BASE_URL = "https://goldtrade-logs-api.poonnatuch.workers.dev"

# 🎯 Portfolio & File Settings (แก้ให้ใช้ BASE_DIR ล็อกเป้าหมาย)
STARTING_THB = 1500.00
TRADE_MIN_THB = 1000.00
PORTFOLIO_FILE = os.path.join(BASE_DIR, "portfolio.json")
LOG_FILE_NAME = os.path.join(BASE_DIR, "live_gold_log.json")
HISTORICAL_CSV = os.path.join(BASE_DIR, "gold_historical_2568_2569_combined.csv")
DEALS_CSV_FILE = os.path.join(BASE_DIR, "CN240_Deals_Record.csv")
BAHT_TO_GRAM = 15.244

# Market Settings
GOLD_HISTORY_PERIOD = "3mo"
FOREX_HISTORY_PERIOD = "14d"
EMA_FAST = 14
EMA_SLOW = 50
RSI_PERIOD = 14
RSI_BUY_THRESHOLD = 40
RSI_SELL_THRESHOLD = 60

# System Timers
RUN_EVERY_MINUTES = 2
DECISION_TIMEOUT_SECONDS = 15

# Trading Quotas
TRADE_QUOTAS = {
    "WD_Morning": 2,
    "WD_Afternoon": 2,
    "WD_Evening": 2,
    "WD_Late_Night": 0,
    "WE_Active": 2,
}
