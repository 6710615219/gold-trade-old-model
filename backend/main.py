import os
import json
import sqlite3
import requests
import feedparser
import asyncio
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, time as dt_time, timedelta
from fastapi import FastAPI, APIRouter, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from groq import Groq

import lstm_model
from analytics_engine import AdvancedTradingAnalytics, parse_logs_to_metrics

# =====================================================================
# 1. MASTER CONFIGURATION
# =====================================================================
app = FastAPI(title="Advanced AI Trading API")
api_router = APIRouter(prefix="/api")

# ดึงคีย์จาก Environment Variables (ปลอดภัย ไม่โดน GitHub บล็อก)
GROQ_API_KEYS = [
    os.getenv("GROQ_API_KEY_1", ""),
    os.getenv("GROQ_API_KEY_2", "")
]
# กรองเอาเฉพาะคีย์ที่ใส่ค่ามาจริงๆ
GROQ_API_KEYS = [k for k in GROQ_API_KEYS if k.strip() != ""]

ENABLE_UNIVERSITY_API = False
TEAM_API_KEY = "6e2755d365cb0e408024ddaca46aadf28756bd9c2a7481de70c82adeff2b436c"
LOG_BASE_URL = "https://goldtrade-logs-api.poonnatuch.workers.dev"

STARTING_THB = 1500.00
TRADE_MIN_THB = 1000.00
PORTFOLIO_FILE = "portfolio.json"
LOG_FILE_NAME = "live_gold_log.json"
CHART_FILE = "chart_history.json"
LANGUAGE = "EN"
BAHT_TO_GRAM = 15.244

GOLD_HISTORY_PERIOD = "3mo"
FOREX_HISTORY_PERIOD = "14d"
EMA_FAST = 14
EMA_SLOW = 50
RSI_PERIOD = 14
URGENCY_MINUTES_THRESHOLD = 60

TRADE_QUOTAS = {
    "WD_Morning": 4, "WD_Afternoon": 4, "WD_Evening": 4, "WD_Late_Night": 0, "WE_Active": 4
}

# Setup SQLite Database
conn = sqlite3.connect("logs.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute("""
CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT, action TEXT, price REAL,
    reason TEXT, timestamp TEXT
)
""")
conn.commit()

# 🎯 ตัวแปรเก็บสัญญาณที่ AI วิเคราะห์ได้ (รอหน้าเว็บมารับ)
pending_signal = None

# =====================================================================
# 2. MODELS & PROMPTS
# =====================================================================
class ExecuteRequest(BaseModel):
    ai_action: str
    ai_reason: str
    ai_amount_thb: str
    user_action: str

class PortfolioUpdate(BaseModel):
    THB_Balance: float
    Gold_Gram: float

PROMPTS = {
    "EN": {
        "system": "You are a senior quantitative commodities strategist. Respond strictly in English.",
        "eco": "Chief Economist. Analyze headlines:\n{news}\nWrite 2-sentence sentiment report. End with SENTIMENT SCORE: (1-10).",
        "quant": "Quant Analyst. Analyze Global Gold (XAUUSD):\nGlobal Price: ${xau_price:,.2f}\nRSI ({rsi_period}): {rsi:.4f}\nEMA ({ema_fast}/{ema_slow}): {ema_signal}\nLive HSH Arbitrage Spread: {hsh_spread:.2f} THB (Premium: {premium:.2f} THB)\nWrite 2-sentence technical summary. End with MOMENTUM SCORE: (1-10).",
        "currency": "Currency Analyst (Forex). Analyze USD/THB:\nCurrent Rate: {current_thb:.3f} THB per USD\n{forex_period} Trend: {thb_trend} (Slope: {thb_slope:.4f})\nWrite 2-sentence analysis on how this affects THB Gold prices. End with CURRENCY RISK SCORE: (1-10).",
        "manager": "Portfolio Manager. Cash: {balance:,.2f} THB. Gold Held: {gold_gram:.4f} Grams.\nBuy Price: {price_per_gram_buy:,.2f} THB | Sell Price: {price_per_gram_sell:,.2f} THB.\n\n--- SESSION INFO ---\nPeriod: {period_name}\nTime Remaining: {minutes_remaining} Minutes\nTrades done: {trades_count} / {target_trades}\n\n--- REPORTS ---\n{eco}\n{quant}\n{currency}\n\nRules:\n1. Constraint: You CANNOT BUY if Cash < {trade_min:,.2f} THB. You CANNOT SELL if Gold Held is 0.\n{quota_instruction}\nFORMAT STRICTLY:\nACTION: [BUY / SELL / HOLD]\nAMOUNT_THB: [Enter number e.g., 1000, 1500, or ALL]\nREASONING: [1 sentence logic.]",
        "error_groq": "ACTION: HOLD\nAMOUNT_THB: 0\nREASONING: Emergency fallback. Groq API limits reached, offline, or keys not configured properly."
    }
}

# =====================================================================
# 3. HELPER FUNCTIONS & MATH ENGINE
# =====================================================================
def get_thai_time():
    return datetime.utcnow() + timedelta(hours=7)

def get_trading_period(now):
    weekday = now.weekday()
    current_time = now.time()
    current_date = now.date()

    if dt_time(0, 0) <= current_time <= dt_time(1, 59, 59):
        logical_date = current_date - timedelta(days=1)
        if logical_date.weekday() < 5:
            return "WD_Late_Night", "Weekday Late Night", True, datetime.combine(current_date, dt_time(1, 59, 59))

    if weekday < 5:
        if dt_time(6, 0) <= current_time <= dt_time(11, 59, 59):
            return "WD_Morning", "Weekday Morning", True, datetime.combine(current_date, dt_time(11, 59, 59))
        elif dt_time(12, 0) <= current_time <= dt_time(17, 59, 59):
            return "WD_Afternoon", "Weekday Afternoon", True, datetime.combine(current_date, dt_time(17, 59, 59))
        elif dt_time(18, 0) <= current_time <= dt_time(23, 59, 59):
            return "WD_Evening", "Weekday Evening", True, datetime.combine(current_date, dt_time(23, 59, 59))
    else:
        if dt_time(9, 30) <= current_time <= dt_time(17, 29, 59):
            return "WE_Active", "Weekend Active", True, datetime.combine(current_date, dt_time(17, 29, 59))
    return "CLOSED", "Out of Trading Hours", False, None

def load_portfolio():
    default_state = {"THB_Balance": STARTING_THB, "Gold_Gram": 0.0, "Current_Date": str(get_thai_time().date()), "Current_Period": "NONE", "Trades_Count": 0}
    if os.path.exists(PORTFOLIO_FILE):
        with open(PORTFOLIO_FILE, "r") as f:
            try:
                data = json.load(f)
                for k, v in default_state.items():
                    if k not in data: data[k] = v
                return data
            except: pass
    return default_state

def save_portfolio(portfolio):
    with open(PORTFOLIO_FILE, "w") as f: json.dump(portfolio, f, indent=4)

def load_chart_history():
    if os.path.exists(CHART_FILE):
        with open(CHART_FILE, "r") as f:
            try: return json.load(f)
            except: pass
    return []

def save_chart_history(history):
    with open(CHART_FILE, "w") as f: json.dump(history, f)

def get_live_hsh_data():
    try:
        url = "https://apicheckpricev3.huasengheng.com/api/Values/GetPriceSeacon"
        data = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5).json()
        hsh_buy, hsh_sell = float(data.get('Bid965', 0)), float(data.get('Ask965', 0))
        assoc_buy, assoc_sell = float(data.get('BidAssociation', 0)), float(data.get('AskAssociation', 0))
        if hsh_sell == 0 or assoc_sell == 0: return None
        return {'HSH_Buy': hsh_buy, 'HSH_Sell': hsh_sell, 'Assoc_Buy': assoc_buy, 'Assoc_Sell': assoc_sell, 'HSH_Spread': hsh_sell - hsh_buy, 'HSH_Premium': hsh_sell - assoc_sell}
    except: return None

def get_global_markets():
    try:
        gold_hist = None
        for ticker in ["GC=F", "MGC=F"]:
            try:
                temp_hist = yf.Ticker(ticker).history(period=GOLD_HISTORY_PERIOD)['Close']
                if len(temp_hist) >= EMA_SLOW: gold_hist = temp_hist; break
            except: continue
        if gold_hist is None: return None
        
        ema_fast_val = gold_hist.ewm(span=EMA_FAST, adjust=False).mean().iloc[-1]
        ema_slow_val = gold_hist.ewm(span=EMA_SLOW, adjust=False).mean().iloc[-1]
        ema_signal = "BULLISH (Uptrend)" if ema_fast_val > ema_slow_val else "BEARISH (Downtrend)"
        
        delta = gold_hist.diff()
        up = delta.clip(lower=0).ewm(alpha=1/RSI_PERIOD, adjust=False).mean()
        down = -1 * delta.clip(upper=0).ewm(alpha=1/RSI_PERIOD, adjust=False).mean()
        rsi = 100 - (100 / (1 + (up / down))).iloc[-1]
        
        thb_hist = yf.Ticker("THB=X").history(period=FOREX_HISTORY_PERIOD)['Close']
        current_thb = thb_hist.iloc[-1]
        x = np.arange(len(thb_hist))
        thb_slope, _ = np.polyfit(x, thb_hist.values, 1)
        thb_trend = "WEAKENING BAHT" if thb_slope > 0 else "STRONG BAHT"
        
        return {"xau_price": gold_hist.iloc[-1], "rsi": rsi, "ema_signal": ema_signal, "current_thb": current_thb, "thb_slope": thb_slope, "thb_trend": thb_trend}
    except: return None

def get_news():
    try:
        feed = feedparser.parse("https://www.bangkokpost.com/rss/data/business.xml")
        return "\n".join([f"- {e.get('title')}" for e in feed.entries[:3]])
    except: return "News feed offline."

def ask_groq(prompt):
    models = ["llama-3.1-8b-instant", "llama-3.3-70b-versatile"]
    
    if not GROQ_API_KEYS:
        return PROMPTS[LANGUAGE]["error_groq"]

    for api_key in GROQ_API_KEYS:
        try:
            client = Groq(api_key=api_key)
            res = client.chat.completions.create(
                messages=[{"role": "system", "content": PROMPTS[LANGUAGE]["system"]}, {"role": "user", "content": prompt}],
                model=models[0], temperature=0.1, max_tokens=600
            )
            return res.choices[0].message.content
        except: continue
    return PROMPTS[LANGUAGE]["error_groq"]

def log_to_json(log_entry):
    logs = []
    if os.path.isfile(LOG_FILE_NAME):
        with open(LOG_FILE_NAME, "r", encoding="utf-8") as f:
            try: logs = json.load(f)
            except: pass
    logs.append(log_entry)
    with open(LOG_FILE_NAME, "w", encoding="utf-8") as f: json.dump(logs[-50:], f, indent=4, ensure_ascii=False)


def get_period_trade_bounds(period_key, now):
    current_date = now.date()
    if period_key == "WD_Late_Night":
        return datetime.combine(current_date, dt_time(0, 0, 0)), datetime.combine(current_date, dt_time(1, 59, 59))
    if period_key == "WD_Morning":
        return datetime.combine(current_date, dt_time(6, 0, 0)), datetime.combine(current_date, dt_time(11, 59, 59))
    if period_key == "WD_Afternoon":
        return datetime.combine(current_date, dt_time(12, 0, 0)), datetime.combine(current_date, dt_time(17, 59, 59))
    if period_key == "WD_Evening":
        return datetime.combine(current_date, dt_time(18, 0, 0)), datetime.combine(current_date, dt_time(23, 59, 59))
    if period_key == "WE_Active":
        return datetime.combine(current_date, dt_time(9, 30, 0)), datetime.combine(current_date, dt_time(17, 29, 59))
    return None, None


def get_period_trade_counts(period_key, now):
    start, end = get_period_trade_bounds(period_key, now)
    if not start or not os.path.isfile(LOG_FILE_NAME):
        return 0, 0
    try:
        with open(LOG_FILE_NAME, "r", encoding="utf-8") as f:
            logs = json.load(f)
    except:
        return 0, 0

    buy_count = 0
    sell_count = 0
    for entry in logs:
        try:
            entry_dt = datetime.strptime(entry.get("date", ""), "%Y-%m-%d %H:%M:%S")
        except:
            continue
        if entry_dt < start or entry_dt > end:
            continue
        action = str(entry.get("action", "")).upper()
        if action == "BUY":
            buy_count += 1
        elif action == "SELL":
            sell_count += 1
    return buy_count, sell_count


def push_log_to_server(action, price, reason, amount, current_nav, ai_action, user_action):
    if not ENABLE_UNIVERSITY_API: return
    payload = {"action": action, "price": "MARKET" if price == "MARKET" else float(price), "reason": reason, "executed_amount": amount, "net_asset_value": current_nav, "signal_source": "AI_Agent_WebApp", "ai_intended_action": ai_action, "user_override_action": user_action}
    try: requests.post(f"{LOG_BASE_URL}/logs", headers={"Authorization": f"Bearer {TEAM_API_KEY}"}, json=payload, timeout=5)
    except: pass

# 🎯 ฟังก์ชันหลักสำหรับให้ AI วิเคราะห์ตลาด (ใช้ LSTM Model ของ gold-trading-platform)
def run_ai_analysis_logic():
    now = get_thai_time()
    portfolio = load_portfolio()
    market = get_live_hsh_data()
    global_math = get_global_markets()
    news = get_news()
    period_key, period_name, is_active, end_time = get_trading_period(now)

    if not is_active or not market or not global_math:
        return None

    target_trades = TRADE_QUOTAS.get(period_key, 0)
    current_trades = portfolio["Trades_Count"]
    minutes_remaining = int((end_time - now).total_seconds() / 60)
    weekend_rule = (
        f" WEEKEND MODE: Use minimum amount (AMOUNT_THB: {TRADE_MIN_THB:.2f})."
        if "WE_" in period_key
        else ""
    )

    buy_count, sell_count = get_period_trade_counts(period_key, now)
    missing_actions = []
    if buy_count == 0:
        missing_actions.append("BUY")
    if sell_count == 0:
        missing_actions.append("SELL")

    if target_trades == 0:
        dynamic_quota = "No strict quota. Trade on clear convergence." + weekend_rule
    elif current_trades < target_trades and minutes_remaining <= URGENCY_MINUTES_THRESHOLD:
        dynamic_quota = (
            f"URGENT: MUST trade NOW to pass limit ({minutes_remaining} mins left). Use AMOUNT_THB: {TRADE_MIN_THB:.2f}."
            + weekend_rule
        )
    else:
        dynamic_quota = (
            f"Quota Status: {current_trades}/{target_trades}. Trade normally."
            + weekend_rule
        )

    if missing_actions:
        missing_label = " and ".join(missing_actions)
        missing_hint = (
            f" IMPORTANT: This period currently has no {missing_label}. "
            "If you can, choose the missing action before period ends. "
        )
        if len(missing_actions) == 2:
            missing_hint += (
                "If both are missing, start with BUY when cash is available, "
                "or SELL if gold is already held, and then complete the opposite side later. "
            )
        dynamic_quota += missing_hint

    lstm_live_data = {
        "HSH_Buy": market["HSH_Buy"],
        "HSH_Sell": market["HSH_Sell"],
        "xau_price": global_math["xau_price"],
        "current_thb": global_math["current_thb"],
        "rsi": global_math["rsi"],
    }
    predicted_price = lstm_model.predict_next_price_with_lstm(lstm_live_data)
    if predicted_price is None:
        predicted_price = market["HSH_Buy"]

    p_buy_gram = market["HSH_Sell"] / BAHT_TO_GRAM
    p_sell_gram = market["HSH_Buy"] / BAHT_TO_GRAM

    prompt_content = PROMPTS[LANGUAGE]["manager"].format(
        balance=portfolio["THB_Balance"],
        gold_gram=portfolio["Gold_Gram"],
        price_per_gram_buy=p_buy_gram,
        price_per_gram_sell=p_sell_gram,
        trade_min=TRADE_MIN_THB,
        period_name=period_name,
        trades_count=current_trades,
        target_trades=target_trades,
        minutes_remaining=minutes_remaining,
        quota_instruction=dynamic_quota,
    )

    decision = ask_groq(prompt_content)
    ai_act, ai_reason, ai_amt = "HOLD", "Default Hold", "ALL"
    for line in decision.split("\n"):
        line_u = line.upper()
        if "ACTION:" in line_u:
            ai_act = line_u.split(":", 1)[1].strip()
        elif "AMOUNT_THB:" in line_u:
            ai_amt = line.split(":", 1)[1].strip().replace(",", "")
        elif "REASONING:" in line_u:
            ai_reason = line.split(":", 1)[1].strip()

    return {
        "ai_action": ai_act,
        "ai_amount_thb": ai_amt,
        "ai_reason": f"<strong>AI Reason:</strong> {ai_reason}",
        "current_market_price": market["HSH_Sell"]
        if ai_act == "BUY"
        else market["HSH_Buy"],
    }

# =====================================================================
# 3.5 BACKGROUND TASKS (ดึงกราฟกลาง + AI Analysis)
# =====================================================================
async def poll_chart_data():
    while True:
        try:
            url = "https://apicheckpricev3.huasengheng.com/api/Values/GetPriceSeacon"
            res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5).json()
            if res and 'Ask965' in res and 'Bid965' in res:
                sell_price = float(str(res['Ask965']).replace(',', ''))
                buy_price = float(str(res['Bid965']).replace(',', ''))
                
                history = load_chart_history()
                now_str = get_thai_time().isoformat()
                
                history.append({
                    "timestamp": now_str,
                    "price": sell_price,
                    "buy": buy_price
                })
                history = history[-60:] # เก็บย้อนหลัง 60 นาที
                save_chart_history(history)
        except Exception as e:
            print(f"Chart Poll Error: {e}")
        
        await asyncio.sleep(60) # ดึงทุก 60 วินาที

# 🎯 Background Task 2: ให้ AI วิเคราะห์อัตโนมัติทุก 15 นาที (Autonomous AI)
async def auto_analysis_loop():
    global pending_signal

    while True:
        try:
            now = get_thai_time()

            # ทำการ analyze ทุก 15 นาทีเพื่อให้ user สามารถตัดสินใจได้ในเวลา 15 วินาที
            if now.minute % 15 == 0 and now.second < 10:
                print(
                    f"[{now.strftime('%H:%M:%S')}] 🤖 Backend: Running Autonomous AI Analysis..."
                )

                result = run_ai_analysis_logic()

                if result:
                    ai_act = result.get("ai_action", "HOLD")

                    # แสดงสัญญาณเฉพาะตอนเปลี่ยนเป็น BUY/SELL
                    if ai_act in ["BUY", "SELL"]:
                        print(f"🔥 Signal Alert: {ai_act}")
                        # ตั้ง pending_signal เพื่อให้ frontend รับ
                        pending_signal = result

                await asyncio.sleep(60)

        except Exception as e:
            print(f"Auto Analysis Error: {e}")

        await asyncio.sleep(5)

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(poll_chart_data())
    asyncio.create_task(auto_analysis_loop())


# =====================================================================
# 4. API ENDPOINTS
# =====================================================================
@api_router.get("/chart")
def get_chart_data():
    return {"status": "success", "data": load_chart_history()}

@api_router.get("/news")
def get_latest_news_api():
    try:
        feed = feedparser.parse("https://www.bangkokpost.com/rss/data/business.xml")
        news_list = [{"title": e.get('title'), "link": e.get('link')} for e in feed.entries[:5]]
        return {"status": "success", "news": news_list}
    except Exception as e:
        return {"status": "error", "news": []}

@api_router.get("/status")
def get_status():
    now = get_thai_time()
    portfolio = load_portfolio()
    market = get_live_hsh_data()
    period_key, period_name, is_active, end_time = get_trading_period(now)

    if portfolio.get('Current_Date') != str(now.date()) or portfolio.get('Current_Period') != period_key:
        portfolio['Current_Date'] = str(now.date())
        portfolio['Current_Period'] = period_key
        portfolio['Trades_Count'] = 0
        save_portfolio(portfolio)

    if market is None:
        return {"error": "Market data unavailable"}

    price_g = (market["HSH_Buy"] / BAHT_TO_GRAM)
    nav = portfolio['THB_Balance'] + (portfolio['Gold_Gram'] * price_g)
    
    # 🎯 Calculate analytics
    closed, unrealized, first_date = parse_logs_to_metrics(LOG_FILE_NAME, price_g)
    report = AdvancedTradingAnalytics.generate_full_report(
        closed, unrealized, nav, first_date, STARTING_THB
    )

    return {
        "portfolio": portfolio,
        "market": market,
        "net_asset_value": nav,
        "period": {
            "name": period_name,
            "is_active": is_active,
            "trades_done": portfolio['Trades_Count']
        },
        "performance": {
            "total_closed_trade": report["Total Closed Trade"],
            "win_rate": report["Win Rate (%)"],
            "total_profit": report["Total Profit (THB)"],
            "unrealized_pl": report["Unrealized P/L (THB)"],
            "avg_win": report["Average Win (THB)"],
            "avg_loss": report["Average Loss (THB)"],
            "expectancy": report["Expectancy per Trade (THB)"],
            "best_trade": report["Best Annualized Trade (%)"],
            "worst_trade": report["Worst Annualized Trade (%)"],
            "median_trade": report["Median Annualized Trade (%)"],
            "top10_trade": report["Top 10% Annualized Trade (%)"],
            "bottom10_trade": report["Bottom 10% Annualized Trade (%)"],
            "xirr": report["XIRR (%)"],
            "avg_capital_year": report["Avg Capital/Year (THB)"],
            "sharpe_ratio": report["Sharpe Ratio"],
        },
    }

@api_router.post("/portfolio")
def update_portfolio(req: PortfolioUpdate):
    portfolio = load_portfolio()
    portfolio['THB_Balance'] = req.THB_Balance
    portfolio['Gold_Gram'] = req.Gold_Gram
    save_portfolio(portfolio)
    return {"status": "success"}

# 🎯 API ใหม่สำหรับหน้าเว็บมาเช็คสัญญาณที่ AI วิเคราะห์ทิ้งไว้
@api_router.get("/pending-signal")
def get_pending_signal():
    global pending_signal
    return {"signal": pending_signal}

# 🎯 API สำหรับ Manual Trade ที่ผู้ใช้กดได้ตลอดเวลา
class ManualTradeRequest(BaseModel):
    action: str  # "BUY" or "SELL"
    amount_thb: str  # amount in THB or "ALL"

@api_router.post("/manual-trade")
def manual_trade(req: ManualTradeRequest):
    now = get_thai_time()
    portfolio = load_portfolio()
    market = get_live_hsh_data()
    period_key, _, _, _ = get_trading_period(now)

    if not market:
        return {"error": "Market data unavailable"}

    p_buy_gram = market["HSH_Sell"] / BAHT_TO_GRAM
    p_sell_gram = market["HSH_Buy"] / BAHT_TO_GRAM
    act, exec_price, exec_amt_str = "HOLD", "MARKET", "0"

    if req.action == "BUY" and portfolio["THB_Balance"] >= TRADE_MIN_THB:
        target_thb = portfolio["THB_Balance"]
        if req.amount_thb != "ALL":
            try:
                target_thb = max(
                    TRADE_MIN_THB,
                    min(float(req.amount_thb), portfolio["THB_Balance"]),
                )
            except:
                pass
        gram_bought = round(target_thb / p_buy_gram, 4)
        portfolio["Gold_Gram"] += gram_bought
        portfolio["THB_Balance"] -= target_thb
        portfolio["Trades_Count"] += 1
        act, exec_price, exec_amt_str = (
            "BUY",
            market["HSH_Sell"],
            f"{gram_bought}g ({target_thb} THB)",
        )

    elif req.action == "SELL" and portfolio["Gold_Gram"] > 0:
        current_val = portfolio["Gold_Gram"] * p_sell_gram
        target_thb = current_val
        if req.amount_thb != "ALL":
            try:
                target_thb = min(float(req.amount_thb), current_val)
            except:
                pass
        gram_sold = min(round(target_thb / p_sell_gram, 4), portfolio["Gold_Gram"])
        cash_returned = round(gram_sold * p_sell_gram, 2)
        portfolio["THB_Balance"] += cash_returned
        portfolio["Gold_Gram"] -= gram_sold
        portfolio["Trades_Count"] += 1
        act, exec_price, exec_amt_str = (
            "SELL",
            market["HSH_Buy"],
            f"Sold {gram_sold}g ({cash_returned} THB)",
        )

    save_portfolio(portfolio)
    nav = portfolio["THB_Balance"] + (portfolio["Gold_Gram"] * p_sell_gram)
    
    # Logging
    log_entry = {
        "date": now.strftime("%Y-%m-%d %H:%M:%S"),
        "period": period_key,
        "action": req.action,
        "user_action": req.action,
        "executed_action": act,
        "price": exec_price,
        "reason": f"Manual {req.action} trade",
        "amount": exec_amt_str,
        "total_asset_value": nav,
    }
    log_to_json(log_entry)
    cursor.execute(
        "INSERT INTO logs (action, price, reason, timestamp) VALUES (?, ?, ?, ?)",
        (act, exec_price if act != "HOLD" else 0, f"Manual {req.action}", now.isoformat()),
    )
    conn.commit()

    if result := {"status": "success", "executed_action": act, "net_asset_value": nav}:
        return result

@api_router.post("/analyze")
def trigger_analysis():
    result = run_ai_analysis_logic()
    if not result:
        return {"error": "Market Offline"}
    return result

@api_router.post("/execute")
def execute_trade(req: ExecuteRequest):
    global pending_signal
    now = get_thai_time()
    portfolio = load_portfolio()
    market = get_live_hsh_data()
    period_key, _, _, _ = get_trading_period(now)
    p_buy_gram = market["HSH_Sell"] / BAHT_TO_GRAM
    p_sell_gram = market["HSH_Buy"] / BAHT_TO_GRAM
    final_act = "HOLD" if req.user_action == "TIMEOUT" else req.user_action
    act, exec_price, exec_amt_str = "HOLD", "MARKET", "0"

    if final_act == "BUY" and portfolio["THB_Balance"] >= TRADE_MIN_THB:
        target_thb = portfolio["THB_Balance"]
        if req.ai_amount_thb != "ALL":
            try:
                target_thb = max(
                    TRADE_MIN_THB,
                    min(float(req.ai_amount_thb), portfolio["THB_Balance"]),
                )
            except:
                pass
        gram_bought = round(target_thb / p_buy_gram, 4)
        portfolio["Gold_Gram"] += gram_bought
        portfolio["THB_Balance"] -= target_thb
        portfolio["Trades_Count"] += 1
        act, exec_price, exec_amt_str = (
            "BUY",
            market["HSH_Sell"],
            f"{gram_bought}g ({target_thb} THB)",
        )

    elif final_act == "SELL" and portfolio["Gold_Gram"] > 0:
        current_val = portfolio["Gold_Gram"] * p_sell_gram
        target_thb = current_val
        if req.ai_amount_thb != "ALL":
            try:
                target_thb = min(float(req.ai_amount_thb), current_val)
            except:
                pass
        gram_sold = min(round(target_thb / p_sell_gram, 4), portfolio["Gold_Gram"])
        cash_returned = round(gram_sold * p_sell_gram, 2)
        portfolio["THB_Balance"] += cash_returned
        portfolio["Gold_Gram"] -= gram_sold
        portfolio["Trades_Count"] += 1
        act, exec_price, exec_amt_str = (
            "SELL",
            market["HSH_Buy"],
            f"Sold {gram_sold}g ({cash_returned} THB)",
        )

    save_portfolio(portfolio)
    nav = portfolio["THB_Balance"] + (portfolio["Gold_Gram"] * p_sell_gram)
    log_to_json(
        {
            "date": now.strftime("%Y-%m-%d %H:%M:%S"),
            "period": period_key,
            "action": req.ai_action,
            "user_action": req.user_action,
            "executed_action": act,
            "price": exec_price,
            "reason": req.ai_reason,
            "amount": exec_amt_str,
            "total_asset_value": nav,
        }
    )
    parse_logs_to_metrics(LOG_FILE_NAME, p_sell_gram)
    cursor.execute(
        "INSERT INTO logs (action, price, reason, timestamp) VALUES (?, ?, ?, ?)",
        (act, exec_price if act != "HOLD" else 0, req.ai_reason, now.isoformat()),
    )
    conn.commit()

    # 🎯 เคลียร์สัญญาณหลังจากตัดสินใจเรียบร้อยแล้ว
    pending_signal = None
    return {"status": "success", "executed_action": act, "net_asset_value": nav}

app.include_router(api_router)

# =====================================================================
# 5. FRONTEND PROXY & SERVING (Deploy ready for Render)
# =====================================================================
@app.get("/hsh-api/{path:path}")
def proxy_hsh(path: str):
    url = f"https://apicheckpricev3.huasengheng.com/{path}"
    try: return requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5).json()
    except: return {}

FRONTEND_DIST = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend", "dist"))
if os.path.exists(FRONTEND_DIST):
    app.mount("/assets", StaticFiles(directory=os.path.join(FRONTEND_DIST, "assets")), name="assets")
    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        if full_path.startswith("api/") or full_path.startswith("hsh-api/"): raise HTTPException(status_code=404)
        return FileResponse(os.path.join(FRONTEND_DIST, "index.html"))
