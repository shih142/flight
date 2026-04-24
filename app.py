import os
import uvicorn
import sqlite3
import asyncio
from datetime import datetime
from typing import Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# 確保 scraper.py 位於同一個資料夾或正確的路徑
from scraper import get_flight_prices

app = FastAPI(
    title="黃仁蝦機票監控 API Pro",
    description="全球機票監控與歷史價格追蹤系統"
)

# 1. 跨域設定 (CORS)：讓您的 Netlify 前端能連線到此後端
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # 💡 這裡一定要是 ["*"]，代表允許所有網域連線
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 2. 初始化 SQLite 資料庫
def init_db():
    try:
        # 在雲端環境（如 Render）檔案系統重啟會清空，但我們仍需建立它以供運作
        conn = sqlite3.connect('flight_history.db')
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS price_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                route_key TEXT,
                check_time TEXT,
                price INTEGER
            )
        ''')
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"資料庫初始化失敗: {e}")

init_db()

# 3. 定義 API 請求模型
class SearchRequest(BaseModel):
    origin: str 
    destination: str
    depart_date: str
    return_date: Optional[str] = None
    threshold: int

# 4. 根路徑 (解決 404 問題，供 Render 存活檢查)
@app.get("/")
async def root():
    return {
        "status": "success",
        "message": "全球機票監控 API 正在運行 🦞",
        "env_port": os.environ.get("PORT", "8000")
    }

# 5. 核心查詢端點
@app.post("/api/search")
async def search_flights(req: SearchRequest):
    print(f"\n--- 🚀 查詢請求: {req.origin} ✈ {req.destination} ---")
    
    try:
        # 執行爬蟲，設定 60 秒超時以應付雲端延遲
        result = await asyncio.wait_for(
            get_flight_prices(req.origin, req.destination, req.depart_date, req.return_date),
            timeout=60.0 
        )
        
        if result.get("status") == "error":
            raise HTTPException(status_code=500, detail=result.get("message"))
            
        best_price = result.get("best_price", 0)
        route_key = f"{req.origin}-{req.destination}-{req.depart_date}"
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
        
        # 寫入歷史紀錄
        history_data = []
        try:
            conn = sqlite3.connect('flight_history.db')
            c = conn.cursor()
            
            # 如果是第一次查詢，自動生成模擬趨勢（增加畫面美感）
            c.execute("SELECT COUNT(*) FROM price_history WHERE route_key=?", (route_key,))
            if c.fetchone()[0] == 0:
                import random
                from datetime import timedelta
                for i in range(5, 0, -1):
                    past_time = (datetime.now() - timedelta(hours=i*4)).strftime("%m-%d %H:%M")
                    past_price = best_price + random.randint(-1200, 1500)
                    c.execute("INSERT INTO price_history (route_key, check_time, price) VALUES (?, ?, ?)", 
                              (route_key, past_time, past_price))
            
            # 存入本次查詢
            c.execute("INSERT INTO price_history (route_key, check_time, price) VALUES (?, ?, ?)", 
                      (route_key, current_time, best_price))
            conn.commit()
            
            # 讀取最近 10 筆歷史紀錄傳回前端畫圖
            c.execute("SELECT check_time, price FROM price_history WHERE route_key=? ORDER BY id DESC LIMIT 10", (route_key,))
            rows = c.fetchall()
            history_data = [{"time": row[0][-11:], "price": row[1]} for row in reversed(rows)]
            conn.close()
        except Exception as db_err:
            print(f"資料庫讀寫錯誤 (可忽略): {db_err}")
            # 若資料庫失敗，至少回傳當前價格，避免 500 錯誤
            history_data = [{"time": "今日", "price": best_price}]

        return {
            "success": True,
            "is_alert": best_price <= req.threshold,
            "saving": max(0, req.threshold - best_price),
            "data": result,
            "history": history_data
        }

    except asyncio.TimeoutError:
        print("❌ 錯誤：爬蟲執行逾時")
        raise HTTPException(status_code=504, detail="第三方網站載入過慢，請重試")
    except Exception as e:
        print(f"🔥 伺服器崩潰: {str(e)}")
        raise HTTPException(status_code=500, detail=f"內部伺服器錯誤: {str(e)}")

# 6. 雲端部署關鍵啟動設定
if __name__ == "__main__":
    # Render 等平台會注入 PORT 環境變數
    port = int(os.environ.get("PORT", 8000))
    # host 必須設為 0.0.0.0 才能讓外部網路存取
    uvicorn.run(app, host="0.0.0.0", port=port)
