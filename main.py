import os
import logging
import sys
import asyncio

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from typing import Literal
from fastapi import FastAPI, HTTPException, Request, BackgroundTasks, Header
from fastapi.responses import JSONResponse, HTMLResponse
from pydantic import BaseModel, Field
import database
import telegram_utils
import order_executor
import market_data
import auto_analyst
import trade_manager
from dotenv import load_dotenv

# .env yukle
load_dotenv()

# Loglama yapilandirmasi
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("bot.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("BistScalpBot")

app = FastAPI(title="BIST Scalp Bot Webhook Receiver & Simulator")

async def periodic_scan_loop():
    # Bekle ve baslat (baslangicta uvicorn'un yuklenmesini bekle)
    await asyncio.sleep(10)
    while True:
        try:
            import datetime
            import pytz
            tz = pytz.timezone("Europe/Istanbul")
            now = datetime.datetime.now(tz)
            # Hafta ici mi ve borsa acik mi kontrol et (Pazartesi=0, Cuma=4)
            # BIST seans saatleri 10:00 - 18:00
            if now.weekday() < 5 and (10 <= now.hour < 18):
                logger.info("Periyodik BIST taramasi baslatiliyor...")
                await auto_analyst.scan_all_and_report()
            else:
                logger.debug("BIST kapali oldugu icin periyodik tarama atlandi.")
        except Exception as e:
            logger.error(f"Periyodik tarama dongusunde hata: {str(e)}")
        
        await asyncio.sleep(300) # 5 dakika bekle

# Sunucu baslarken veritabani kontrolu
@app.on_event("startup")
def startup_event():
    logger.info("Uygulama baslatiliyor. Veritabani kontrol ediliyor...")
    database.init_db()
    asyncio.create_task(periodic_scan_loop())
    logger.info("Periyodik BIST tarama motoru arka planda baslatildi.")

# TradingView'dan gelecek JSON verisi icin Pydantic modeli
class WebhookAlert(BaseModel):
    ticker: str = Field(..., description="Hisse adi (Orn: KRONT, ARFYE)")
    action: Literal["AL", "SAT"] = Field(..., description="Islem yonu (AL veya SAT)")
    price: float = Field(..., gt=0, description="Hisse fiyati")
    quantity: float = Field(..., gt=0, description="Islem miktari (lot)")

    class Config:
        json_schema_extra = {
            "example": {
                "ticker": "KRONT",
                "action": "AL",
                "price": 75.50,
                "quantity": 100.0
            }
        }

@app.get("/")
def read_root():
    return {"status": "running", "message": "BIST Scalp Bot Webhook Receiver is active."}

# Dashboard Arayuzu
@app.get("/dashboard", response_class=HTMLResponse)
def get_dashboard():
    try:
        template_path = os.path.join("templates", "dashboard.html")
        if not os.path.exists(template_path):
            raise HTTPException(status_code=404, detail="Dashboard template not found")
        
        with open(template_path, "r", encoding="utf-8") as f:
            html_content = f.read()
        return HTMLResponse(content=html_content, status_code=200)
    except Exception as e:
        logger.error(f"Dashboard yuklenirken hata: {str(e)}")
        raise HTTPException(status_code=500, detail="Dashboard yuklenemedi.")

@app.get("/portfolio")
async def get_portfolio():
    try:
        conn = await database.get_async_db_connection()
        try:
            cursor = await conn.execute("SELECT ticker, quantity, average_cost FROM portfolio")
            rows = await cursor.fetchall()
        finally:
            await conn.close()
        
        portfolio = []
        for row in rows:
            item = dict(row)
            ticker = item["ticker"]
            quantity = item["quantity"]
            avg_cost = item["average_cost"]
            
            # Canli piyasa fiyatini cek
            current_price = await market_data.get_stock_price(ticker)
            
            # Fallback (Hata durumunda maliyeti guncel fiyat olarak kullan)
            if current_price is None:
                current_price = avg_cost
                
            current_value = quantity * current_price
            
            # PnL (Kar/Zarar) Hesapla
            if ticker == 'TRY':
                pnl_value = 0.0
                pnl_percent = 0.0
            else:
                total_cost = quantity * avg_cost
                pnl_value = current_value - total_cost
                pnl_percent = ((current_price - avg_cost) / avg_cost * 100) if avg_cost > 0 else 0.0
                
            item.update({
                "current_price": current_price,
                "current_value": current_value,
                "pnl_value": pnl_value,
                "pnl_percent": pnl_percent
            })
            portfolio.append(item)
            
        return {"status": "success", "portfolio": portfolio}
    except Exception as e:
        logger.error(f"Portfoy okunurken ve degerlenirken hata: {str(e)}")
        raise HTTPException(status_code=500, detail="Portfoy bilgisi alinamadi.")

@app.get("/trades")
async def get_trades(limit: int = 50):
    try:
        conn = await database.get_async_db_connection()
        try:
            cursor = await conn.execute("SELECT id, timestamp, ticker, action, price, quantity, total_value, reasoning FROM trades ORDER BY id DESC LIMIT ?", (limit,))
            rows = await cursor.fetchall()
        finally:
            await conn.close()
        
        trades = [dict(row) for row in rows]
        return {"status": "success", "trades": trades}
    except Exception as e:
        logger.error(f"Islem gecmisi okunurken hata: {str(e)}")
        raise HTTPException(status_code=500, detail="Islem gecmisi alinamadi.")

@app.get("/signals")
async def get_signals(limit: int = 50):
    try:
        conn = await database.get_async_db_connection()
        try:
            cursor = await conn.execute("SELECT id, timestamp, ticker, action, price, quantity, reasoning FROM signals ORDER BY id DESC LIMIT ?", (limit,))
            rows = await cursor.fetchall()
        finally:
            await conn.close()
        
        signals = [dict(row) for row in rows]
        return {"status": "success", "signals": signals}
    except Exception as e:
        logger.error(f"Sinyal gecmisi okunurken hata: {str(e)}")
        raise HTTPException(status_code=500, detail="Sinyal gecmisi alinamadi.")

@app.get("/scan")
async def trigger_scan():
    try:
        logger.info("Manuel BIST taramasi tetiklendi...")
        report = await auto_analyst.scan_all_and_report()
        return report
    except Exception as e:
        logger.error(f"Manuel tarama sirasinda hata: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Tarama hatasi: {str(e)}")

# Demo/Gercek mod bilgisini donen endpoint
@app.get("/config")
def get_config():
    demo_mode = os.getenv("DEMO_MODE", "True").strip().lower() == "true"
    return {"demo_mode": demo_mode}

@app.post("/webhook")
async def receive_webhook(
    alert: WebhookAlert, 
    request: Request, 
    background_tasks: BackgroundTasks,
    x_webhook_token: str = Header(None, alias="X-Webhook-Token")
):
    client_host = request.client.host if request.client else "unknown"
    logger.info(f"Webhook istegi alindi. Kaynak IP: {client_host}")
    
    # Token dogrulamasi
    webhook_secret = os.getenv("WEBHOOK_SECRET_TOKEN", "").strip()
    if webhook_secret and x_webhook_token != webhook_secret:
        logger.warning(f"Yetkisiz webhook istegi engellendi. Kaynak IP: {client_host}")
        raise HTTPException(status_code=401, detail="Yetkisiz erisim. Gecersiz token.")

    
    try:
        # trade_manager ile sinyali islet
        result = await trade_manager.process_trade_signal(
            ticker=alert.ticker,
            action=alert.action,
            price=alert.price,
            quantity=alert.quantity
        )
        
        # Gercek emir otomasyonu tetikleme kontrolu
        if result.get("trigger_real_order"):
            background_tasks.add_task(
                order_executor.execute_order, 
                alert.ticker, 
                alert.action, 
                alert.price, 
                alert.quantity
            )
            logger.info("Gercek emir otomasyonu arka planda tetiklendi.")
            
        return JSONResponse(
            status_code=200,
            content=result
        )
        
    except trade_manager.TradeExecutionError as e:
        return JSONResponse(
            status_code=400,
            content={"status": "rejected", "reason": str(e), **e.details}
        )
    except Exception as e:
        logger.error(f"Webhook islenirken beklenmedik hata: {str(e)}")
        raise HTTPException(status_code=500, detail="Sinyal islenirken sunucu hatasi olustu.")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000)

