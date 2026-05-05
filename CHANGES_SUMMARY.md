# Gold Trading Platform - 更新摘要 (Changes Summary)

## 📋 Project Update: gold-trading-platform Integration with Analytics & AI Decision Window

**Date:** May 4, 2026  
**Status:** ✅ Completed  
**Version:** 2.0

---

## 🎯 หลักการปรับปรุง (Key Improvements)

แปลงโปรเจกต์ `gold-trading-platform` ให้มีความสามารถเหมือน `gold-trade-discord-notification` โดยรักษา LSTM Model ของ gold-trading-platform และเพิ่มเติม:
1. ✅ Analytics Dashboard พร้อมตัวชี้วัดผลการทำงาน (Performance Metrics)
2. ✅ Logging System สำหรับบันทึกการทำรายการ (Transaction History)
3. ✅ Manual Trade Buttons ที่ผู้ใช้สามารถกดได้ตลอดเวลา
4. ✅ 15-วินาที Decision Window สำหรับการตัดสินใจ AI Signal โดย Timeout จะ HOLD อัตโนมัติ
5. ✅ Pending Signal Polling System (Auto AI Analysis ทุก 15 นาที)

---

## ✅ ตอนนี้โค้ดทำอะไรได้บ้าง (Updated May 5, 2026)

### Core Trading Features
- ประมวลผลสัญญาณ AI อัตโนมัติทุก 15 นาที โดยใช้ LSTM model + prompt AI
- เก็บสัญญาณไว้ใน `pending_signal` แล้วให้ frontend poll ได้
- มี Countdown 15 วินาทีให้ผู้ใช้ตัดสินใจ BUY / SELL / HOLD
- หากหมดเวลาแล้วจะทำ "HOLD" อัตโนมัติและไม่ execute ตาม AI โดยตรง
- ผู้ใช้กด Manual Trade BUY / SELL ได้ตลอดเวลาระหว่างตลาดเปิด

### Logging & Persistence
- บันทึก Trade ทั้งหมดลง `live_gold_log.json` และ SQLite database
- **[NEW]** ส่ง log ไปยังระบบมหาวิทยาลัย เมื่อ `ENABLE_UNIVERSITY_API` เปิด
  - ส่ง log จาก `/execute` endpoint (AI decision trades)
  - ส่ง log จาก `/manual-trade` endpoint (ผู้ใช้กดเอง)
- มีระบบนับ BUY/SELL ในแต่ละช่วงเวลาเพื่อบังคับให้ครบ quota

### Analytics & Dashboard
- แสดง dashboard performance metrics ผ่าน API `/status`
- คำนวณและแสดง 15 Performance Metrics ทั้งหมด
- ติดตามผลประกอบการเรียลไทม์

### University Log Submission (NEW - May 5, 2026)
- เมื่อตั้ง `ENABLE_UNIVERSITY_API=true` และให้ `TEAM_API_KEY`
- ระบบจะส่ง HTTP POST ไปยัง `https://goldtrade-logs-api.poonnatuch.workers.dev/logs`
- ส่งข้อมูลทั้ง 3 ประเภท:
  1. **AI Signal Trades** - จาก `run_ai_analysis_logic()` (จำนวน: 1 ครั้งต่อ 15 นาที)
  2. **Executed AI Trades** - จาก `/execute` endpoint (ผู้ใช้ตัดสินใจเลือก AI signal)
  3. **Manual Trades** - จาก `/manual-trade` endpoint (ผู้ใช้กดเองตามอิสระ)
- Payload ตรงตามมาตรฐาน API ของมหาวิทยาลัย:
  - `action`: BUY / SELL / HOLD
  - `price`: ราคาปัจจุบัน หรือ "MARKET"
  - `reason`: เหตุผลการตัดสินใจ
  - `executed_amount`: จำนวนที่ซื้อ/ขายไป
  - `net_asset_value`: มูลค่าสินทรัพย์ทั้งหมด
  - Extra fields: `ai_intended_action`, `user_override_action`

---

## 📁 ไฟล์ที่ถูกแก้ไข/เพิ่มเติม

### Backend Changes

#### 1. **analytics_engine.py** (NEW)
   - **Location:** `backend/analytics_engine.py`
   - **Purpose:** คำนวณ Performance Metrics ทั้งหมด
   - **Key Features:**
     - `AdvancedTradingAnalytics.generate_full_report()` - คำนวณ metrics
     - `parse_logs_to_metrics()` - แปลง Log เป็น Metrics
     - **Metrics Calculated:**
       - Total Closed Trade / Win Rate / Total Profit
       - Unrealized P/L / Average Win / Average Loss
       - Best/Worst/Median Annualized Returns
       - Top 10% / Bottom 10% Annualized Returns
       - XIRR / Avg Capital/Year / Sharpe Ratio
       - Expectancy per Trade

#### 2. **main.py** (UPDATED - MAJOR CHANGES)
   - **Location:** `backend/main.py`
   - **Key Additions:**

   **a) Imports:**
   ```python
   import lstm_model
   from analytics_engine import AdvancedTradingAnalytics, parse_logs_to_metrics
   ```

   **b) Global Variable:**
   ```python
   pending_signal = None  # เก็บสัญญาณที่ AI วิเคราะห์ได้รอ Frontend
   ```

   **c) New Function: `run_ai_analysis_logic()`**
   - ทำการวิเคราะห์ตลาด โดยใช้ LSTM Model ของ gold-trading-platform
   - Return: AI Signal พร้อม Action, Amount, Reasoning
   - Runs every 15 minutes (via background task)

   **d) New Async Task: `auto_analysis_loop()`**
   - Background task ที่รันทุก 15 นาที
   - เรียก `run_ai_analysis_logic()` และเก็บผลใน `pending_signal`
   - ทำให้ Frontend สามารถ Poll หา Signal ได้

   **e) New Endpoints:**

   | Endpoint | Method | Purpose |
   |----------|--------|---------|
   | `/pending-signal` | GET | ตรวจสอบสัญญาณที่ AI วิเคราะห์ได้ |
   | `/manual-trade` | POST | ให้ผู้ใช้กดซื้อ/ขายด้วยตนเอง |

   **f) Updated Endpoints:**

   | Endpoint | Changes |
   |----------|---------|
   | `/status` | เพิ่ม Performance metrics ใน response |
   | `/execute` | เพิ่มการเคลียร์ `pending_signal` หลังตัดสินใจแล้ว + ส่ง log ไประบบมหาลัย |
   | `/manual-trade` | **[NEW]** เพิ่ม push_log_to_server() เพื่อส่งไปยังระบบมหาลัย |

   **g) Enhanced Logging:**
   - บันทึก action, price, reason, timestamp เข้า SQLite
   - บันทึก JSON log ของ Live Gold Log
   - **[NEW May 5]** เรียก `push_log_to_server()` จาก `/execute` และ `/manual-trade`
   - ส่ง log ไประบบมหาวิทยาลัยเมื่อเปิดใช้ `ENABLE_UNIVERSITY_API`

   **h) Period Trade Requirements:**
   - เพิ่ม helper สำหรับนับจำนวน BUY/SELL ในแต่ละช่วงเวลา
   - AI prompt จะได้รับคำสั่งให้พยายามทำทั้ง BUY และ SELL อย่างน้อย 1 รอบในช่วงนั้น
   - ถ้ายังขาด BUY หรือ SELL ระบบจะแจ้งเตือนผ่าน dynamic quota

---

### Frontend Changes

#### **App.jsx** (COMPLETE REWRITE)
   - **Location:** `frontend/src/App.jsx`
   - **Major Changes:**

   **a) AI Signal Polling System:**
   ```javascript
   // Polls /pending-signal every 5 seconds
   useEffect(() => {
     const checkPendingSignal = async () => {
       if (aiData || (dashboard && !dashboard.period.is_active)) return;
       const res = await fetch("/api/pending-signal");
       const data = await res.json();
       if (data.signal) {
         setAiData(data.signal);
         setTimeLeft(15); // Start 15-second countdown
       }
     };
     const pollInterval = setInterval(checkPendingSignal, 5000);
     return () => clearInterval(pollInterval);
   }, [aiData, dashboard]);
   ```

   **b) 15-Second Manual Decision Window:**
   - ทำให้ผู้ใช้สามารถตัดสินใจได้ในเวลา 15 วินาทีเท่านั้น
   - Timeout: หากผู้ใช้ไม่ตอบภายใน 15 วินาที ระบบจะ HOLD อัตโนมัติ
   - ไม่มีการ execute ตาม AI โดยอัตโนมัติเมื่อ timeout
   - BUY / SELL / HOLD buttons ให้ผู้ใช้เลือก

   **c) Manual Trade Buttons (เพิ่มใหม่):**
   ```javascript
   // Available anytime during trading hours
   <button onClick={() => manualTrade("BUY")}>🛒 BUY ทอง</button>
   <button onClick={() => manualTrade("SELL")}>💰 SELL ทอง</button>
   ```
   - ผู้ใช้สามารถกดซื้อ/ขายด้วยตนเองได้ตลอดเวลาระหว่างเปิดตลาด
   - ใช้จำนวนเงินทั้งหมด (ALL)

   **d) Performance Dashboard (เพิ่มใหม่):**
   - แสดง 15 Performance Metrics:
     - Total Closed Trade, Win Rate, Total Profit
     - Unrealized P/L, Average Win/Loss, Expectancy
     - Best/Worst/Median Annualized Returns
     - Top 10% / Bottom 10% Returns
     - XIRR, Avg Capital/Year, Sharpe Ratio
   - ใช้สี: ❌ Red (Loss), ✅ Green (Profit/Win), 🟡 Yellow (อื่นๆ)

   **e) History Management:**
   - "ดูทั้งหมด" button สำหรับแสดงประวัติทั้งหมด
   - เก็บ Signal History ใน localStorage
   - แสดง Signal Icon (▲ BUY / ▼ SELL / ● HOLD)

   **f) Timer Updates:**
   - เปลี่ยนจาก 5 นาที เป็น **15 นาที** (getSecondsToNextInterval)
   - แสดง "ระบบกำลังรอสัญญาณจาก AI..." เมื่อไม่มี AI Signal

---

## 🔄 ระบบการทำงาน (Workflow)

### Backend Flow:
```
Every 15 minutes:
┌─────────────────────────────────┐
│  auto_analysis_loop() triggers  │
├─────────────────────────────────┤
│ run_ai_analysis_logic() executes │
├─────────────────────────────────┤
│  get_live_hsh_data()            │
│  get_global_markets()           │
│  get_news()                     │
│  ask_groq(prompt)               │  <- Uses LSTM predictions
├─────────────────────────────────┤
│  Result saved to pending_signal │
├─────────────────────────────────┤
│  Frontend polls /pending-signal  │
└─────────────────────────────────┘
```

### Frontend Flow (User Decision):
```
AI Signal Received
        ↓
Display AI Decision Box
        ↓
15-Second Countdown
        ↓
    User Action?
    ├── BUY → Submit Decision
    ├── SELL → Submit Decision
    ├── HOLD → Submit Decision
    └── TIMEOUT → HOLD automatically
        ↓
Execute Trade (or Hold)
        ↓
Update Portfolio & History
```

### Manual Trade Flow:
```
Any Time (During Market Hours)
        ↓
User clicks BUY/SELL Button
        ↓
POST /api/manual-trade
        ↓
Execute Trade (ALL amount)
        ↓
Log to JSON & SQLite
        ↓
Update Dashboard
```

---

## 📊 API Endpoints Summary

### New/Updated Endpoints:

| Endpoint | Method | Purpose | Request | Response |
|----------|--------|---------|---------|----------|
| `/api/pending-signal` | GET | Get pending AI signal | - | `{signal: AIData \| null}` |
| `/api/manual-trade` | POST | Execute manual trade | `{action, amount_thb}` | `{status, executed_action, net_asset_value}` |
| `/api/status` | GET | Get dashboard + analytics | - | `{portfolio, performance, ...}` |
| `/api/execute` | POST | Execute AI decision | `{ai_action, user_action, ...}` | `{status, executed_action, nav}` |

---

## 🔐 ระบบ 15-วินาที (Security: No Autotrade)

**Key Feature:** ❌ NO AUTOTRADE - User Must Click Within 15 Seconds

```javascript
// If user doesn't click within 15 seconds:
if (timeLeft === 0 && aiData) {
  submitDecision("HOLD"); // AUTO-HOLD, no AI execution
}
```

**Action on TIMEOUT:**
- System executes HOLD automatically
- ไม่มีการ execute ตาม AI recommendation
- Logged as `user_action: "HOLD"` when timeout occurs

---

## 📈 Performance Metrics Displayed

```
Dashboard Grid (15 Metrics):
┌─────────────────────────────────────────┐
│ 1. Total Closed Trade    │ 2. Win Rate   │
├─────────────────────────────────────────┤
│ 3. Total Profit          │ 4. Unrealized P/L │
├─────────────────────────────────────────┤
│ 5. Average Win           │ 6. Average Loss   │
├─────────────────────────────────────────┤
│ 7. Expectancy            │ 8. Best Ann.      │
├─────────────────────────────────────────┤
│ 9. Worst Ann.            │ 10. Median Ann.   │
├─────────────────────────────────────────┤
│ 11. Top 10%              │ 12. Bottom 10%    │
├─────────────────────────────────────────┤
│ 13. XIRR                 │ 14. Avg Cap/Year  │
├─────────────────────────────────────────┤
│ 15. Sharpe Ratio         │                   │
└─────────────────────────────────────────┘
```

---

## 💾 Data Storage

### JSON Files:
- `portfolio.json` - Current portfolio state
- `live_gold_log.json` - All transaction history
- `chart_history.json` - Price history (last 60 minutes)
- `last_signal.json` - Last AI signal (for reference)

### SQLite Database:
- `logs.db` - Persistent transaction logs
  - Columns: id, action, price, reason, timestamp

---

## 🔧 Technical Notes

### LSTM Model Integration:
- Continues to use gold-trading-platform's LSTM model
- Predictions passed to AI analysis as `lstm_pred` parameter
- No changes to LSTM model itself

### University API Integration (NEW - May 5, 2026):
- `push_log_to_server()` function ใน main.py จัดการการส่ง log ไปมหาลัย
- Config ใน `backend/config.py`:
  - `ENABLE_UNIVERSITY_API`: ควบคุมว่าจะส่ง log หรือไม่ (default: False)
  - `TEAM_API_KEY`: API key ของทีม (ดึงจาก environment variable)
  - `LOG_BASE_URL`: `https://goldtrade-logs-api.poonnatuch.workers.dev`
- Call sites:
  1. `run_ai_analysis_logic()`: ส่ง log เมื่อ AI สร้างสัญญาณใหม่
  2. `execute_trade()`: ส่ง log เมื่อผู้ใช้ตัดสินใจจากสัญญาณ AI
  3. `manual_trade()`: ส่ง log เมื่อผู้ใช้กดซื้อ/ขายด้วยตนเอง
- Safety: ถ้า API ไม่ตอบสนอง หรือ network error จะไม่ทำให้การเทรดหยุด (silent fail)

### Threading:
- `auto_analysis_loop()` runs as background task via asyncio
- Doesn't block frontend polling
- New analysis every 15 minutes

### Frontend Update Cycle:
- Polls `/pending-signal` every 5 seconds
- Dashboard refreshes on `/status` call
- History updates on each trade execution

---

## ✅ Verification Checklist

- [x] Analytics engine calculates all 15 metrics correctly
- [x] Pending signal system works (stores and retrieves signals)
- [x] Manual trade buttons functional
- [x] 15-second countdown timer working
- [x] Timeout auto-hold implemented (no AI execute on timeout)
- [x] Logging to JSON and SQLite functioning
- [x] Performance dashboard displays correctly
- [x] Frontend polling updates smoothly
- [x] No autotrade - user must click
- [x] History management working (show all / hide)
- [x] **[NEW]** push_log_to_server() integrated in /execute endpoint
- [x] **[NEW]** push_log_to_server() integrated in /manual-trade endpoint
- [x] **[NEW]** University API submission working when ENABLE_UNIVERSITY_API=true
- [x] **[NEW]** Payload format matches university API requirements
- [x] **[NEW]** Silent failure handling (API errors don't break trading)

---

## 🚀 How to Test

### Test 1: Manual Trade
```
1. Navigate to Trading Platform
2. Click 🛒 BUY ทอง or 💰 SELL ทอง
3. Check that portfolio updates immediately
4. Verify trade appears in history
```

### Test 2: AI Signal Polling
```
1. Wait for 15-minute interval
2. Check that AI Signal box appears
3. Verify countdown starts from 15
4. Try clicking BUY/SELL/HOLD before timeout
```

### Test 3: Timeout Auto-Hold
```
1. Wait for AI Signal
2. Don't click anything
3. Wait 15 seconds
4. Verify system switches to HOLD automatically
```

### Test 4: Performance Metrics
```
1. Execute a few trades
2. Check Dashboard
3. Verify all 15 metrics display correctly
4. Check that Win Rate and Profit update
```

---

## 📝 Files Changed

| File | Type | Status |
|------|------|--------|
| `backend/analytics_engine.py` | NEW | ✅ Created |
| `backend/main.py` | MODIFIED | ✅ Updated |
| `frontend/src/App.jsx` | MODIFIED | ✅ Rewritten |

**Total Lines Changed:** ~1500+ lines
**Breaking Changes:** None (fully backward compatible)

---

## 🎉 Summary

**gold-trading-platform** ได้รับการปรับปรุงให้มีความสามารถครบถ้วนดังนี้:

1. ✅ **Analytics Dashboard** - 15 Performance Metrics
2. ✅ **Logging System** - JSON + SQLite Storage
3. ✅ **Manual Trading** - BUY/SELL buttons anytime
4. ✅ **15-Second Decision Window** - No autotrade enforcement
5. ✅ **AI Signal Polling** - Every 15 minutes auto-analysis
6. ✅ **Pending Signal System** - Frontend polling mechanism
7. ✅ **Performance Tracking** - All key metrics calculated
8. ✅ **[NEW May 5]** **University Log Submission** - Real-time trade logging to university API

### What Changed on May 5, 2026:
- Added `push_log_to_server()` call in `execute_trade()` endpoint
- Added `push_log_to_server()` call in `manual_trade()` endpoint
- Updated `backend/config.py` to support environment-based `ENABLE_UNIVERSITY_API` toggle
- Now sends all AI signals, AI-based trades, and manual trades to university system
- Maintains backward compatibility - all existing features work without interruption

**All systems are fully operational and maintain the use of gold-trading-platform's original LSTM model.**

---

**Status:** ✅ COMPLETE  
**Last Updated:** May 5, 2026  
**Version:** 2.1

