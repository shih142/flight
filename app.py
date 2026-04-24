from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import asyncio
import os

# 注意：部署到雲端時，SQLite 寫入會失效 (因為檔案系統是唯讀的)
# 這裡我們暫時移除資料庫寫入，或改用模擬回傳，確保不會噴 500 錯誤
from .scraper import get_flight_prices 

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class SearchRequest(BaseModel):
    origin: str 
    destination: str
    depart_date: str
    return_date: Optional[str] = None
    threshold: int

@app.post("/api/search")
async def search_flights(req: SearchRequest):
    try:
        # 雲端環境 Playwright 執行較慢，建議超時設長一點
        result = await asyncio.wait_for(
            get_flight_prices(req.origin, req.destination, req.depart_date, req.return_date),
            timeout=50.0 
        )
        
        # 雲端版暫時回傳模擬歷史紀錄，避免 SQLite 報錯
        history_data = [
            {"time": "04-20 12:00", "price": result['best_price'] + 500},
            {"time": "04-21 12:00", "price": result['best_price'] - 300},
            {"time": "今日 查詢", "price": result['best_price']}
        ]
        
        return {
            "success": True,
            "is_alert": result['best_price'] < req.threshold,
            "saving": max(0, req.threshold - result['best_price']),
            "data": result,
            "history": history_data
        }
    except Exception as e:
        return {"success": False, "detail": str(e)}

# Vercel 需要這個
# @app.get("/") 不需要，因為我們有 rewrite 到 index.html