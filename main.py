import os
import logging
import sys
import asyncio

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from typing import Literal
from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
from fastapi.responses import JSONResponse, HTMLResponse
from pydantic import BaseModel, Field
import database
import telegram_utils
import order_executor
import market_data
import auto_analyst
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
            now = datetime.datetime.now()
            # Hafta ici mi ve borsa acik mi kontrol et (Pazartesi=0, Cuma=4, 10:00 - 18:00)
            if now.weekday() < 5 and (10 <= now.hour < 18):
                logger.info("Periyodik BIST taramasi baslatiliyor...")
                await asyncio.to_thread(auto_analyst.scan_all_and_report)
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
def get_portfolio():
    try:
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT ticker, quantity, average_cost FROM portfolio")
        rows = cursor.fetchall()
        conn.close()
        
        portfolio = []
        for row in rows:
            item = dict(row)
            ticker = item["ticker"]
            quantity = item["quantity"]
            avg_cost = item["average_cost"]
            
            # Canli piyasa fiyatini cek
            current_price = market_data.get_stock_price(ticker)
            
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
def get_trades(limit: int = 50):
    try:
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, timestamp, ticker, action, price, quantity, total_value, reasoning FROM trades ORDER BY id DESC LIMIT ?", (limit,))
        rows = cursor.fetchall()
        conn.close()
        
        trades = [dict(row) for row in rows]
        return {"status": "success", "trades": trades}
    except Exception as e:
        logger.error(f"Islem gecmisi okunurken hata: {str(e)}")
        raise HTTPException(status_code=500, detail="Islem gecmisi alinamadi.")

@app.get("/signals")
def get_signals(limit: int = 50):
    try:
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, timestamp, ticker, action, price, quantity, reasoning FROM signals ORDER BY id DESC LIMIT ?", (limit,))
        rows = cursor.fetchall()
        conn.close()
        
        signals = [dict(row) for row in rows]
        return {"status": "success", "signals": signals}
    except Exception as e:
        logger.error(f"Sinyal gecmisi okunurken hata: {str(e)}")
        raise HTTPException(status_code=500, detail="Sinyal gecmisi alinamadi.")

@app.get("/scan")
async def trigger_scan():
    try:
        logger.info("Manuel BIST taramasi tetiklendi...")
        report = await asyncio.to_thread(auto_analyst.scan_all_and_report)
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
async def receive_webhook(alert: WebhookAlert, request: Request, background_tasks: BackgroundTasks):
    client_host = request.client.host if request.client else "unknown"
    logger.info(f"Webhook istegi alindi. Kaynak IP: {client_host}")
    
    conn = database.get_db_connection()
    cursor = conn.cursor()
    
    demo_mode = os.getenv("DEMO_MODE", "True").strip().lower() == "true"
    mode_text = " (Simule)" if demo_mode else " (GERCEK)"
    
    try:
        # 1. Sinyali signals tablosuna kaydet
        cursor.execute(
            "INSERT INTO signals (ticker, action, price, quantity) VALUES (?, ?, ?, ?)",
            (alert.ticker, alert.action, alert.price, alert.quantity)
        )
        conn.commit()
        
        # 2. Islem Simulasyonu
        total_cost = alert.price * alert.quantity
        
        # TRY Bakiyesini al
        cursor.execute("SELECT quantity FROM portfolio WHERE ticker = 'TRY'")
        try_row = cursor.fetchone()
        cash = try_row["quantity"] if try_row else 0.0
        
        if alert.action == "AL":
            if cash < total_cost:
                logger.warning(f"Bakiye yetersiz! Gerekli: {total_cost} TL, Mevcut: {cash} TL. Islem iptal edildi.")
                # Telegram Bildirimi (Arka Planda)
                err_msg = (
                    f"⚠️ <b>ISLEM IPTAL [Yetersiz Bakiye]{mode_text}</b>\n\n"
                    f"📌 <b>Hisse:</b> #{alert.ticker}\n"
                    f"👉 <b>Yon:</b> AL\n"
                    f"💵 <b>Fiyat:</b> {alert.price:.2f} TL\n"
                    f"📦 <b>Miktar:</b> {alert.quantity} Lot\n"
                    f"💰 <b>Gerekli:</b> {total_cost:.2f} TL\n"
                    f"❌ <b>Mevcut Bakiye:</b> {cash:.2f} TL"
                )
                background_tasks.add_task(telegram_utils.send_telegram_message, err_msg)
                
                return JSONResponse(
                    status_code=400,
                    content={"status": "rejected", "reason": "Bakiye yetersiz", "required": total_cost, "available": cash}
                )
            
            # Nakit bakiyesini dusur
            new_cash = cash - total_cost
            cursor.execute("UPDATE portfolio SET quantity = ? WHERE ticker = 'TRY'", (new_cash,))
            
            # Portfoyde hisseyi guncelle veya ekle
            cursor.execute("SELECT quantity, average_cost FROM portfolio WHERE ticker = ?", (alert.ticker,))
            stock_row = cursor.fetchone()
            
            if stock_row:
                old_qty = stock_row["quantity"]
                old_cost = stock_row["average_cost"]
                new_qty = old_qty + alert.quantity
                new_avg_cost = ((old_qty * old_cost) + total_cost) / new_qty
                cursor.execute(
                    "UPDATE portfolio SET quantity = ?, average_cost = ? WHERE ticker = ?",
                    (new_qty, new_avg_cost, alert.ticker)
                )
            else:
                cursor.execute(
                    "INSERT INTO portfolio (ticker, quantity, average_cost) VALUES (?, ?, ?)",
                    (alert.ticker, alert.quantity, alert.price)
                )
                
        elif alert.action == "SAT":
            # Portfoyde hisse kontrolu
            cursor.execute("SELECT quantity, average_cost FROM portfolio WHERE ticker = ?", (alert.ticker,))
            stock_row = cursor.fetchone()
            stock_qty = stock_row["quantity"] if stock_row else 0.0
            
            if stock_qty < alert.quantity:
                logger.warning(f"Hisse miktari yetersiz! Satilmak istenen: {alert.quantity}, Mevcut: {stock_qty}. Islem iptal edildi.")
                # Telegram Bildirimi (Arka Planda)
                err_msg = (
                    f"⚠️ <b>ISLEM IPTAL [Yetersiz Hisse]{mode_text}</b>\n\n"
                    f"📌 <b>Hisse:</b> #{alert.ticker}\n"
                    f"👉 <b>Yon:</b> SAT\n"
                    f"💵 <b>Fiyat:</b> {alert.price:.2f} TL\n"
                    f"📦 <b>Satilmak Istenen:</b> {alert.quantity} Lot\n"
                    f"❌ <b>Mevcut Hisse:</b> {stock_qty} Lot"
                )
                background_tasks.add_task(telegram_utils.send_telegram_message, err_msg)
                
                return JSONResponse(
                    status_code=400,
                    content={"status": "rejected", "reason": "Yetersiz hisse miktari", "requested": alert.quantity, "available": stock_qty}
                )
                
            # Hisse miktarini dusur veya portfoyden kaldir
            new_qty = stock_qty - alert.quantity
            if new_qty == 0:
                cursor.execute("DELETE FROM portfolio WHERE ticker = ?", (alert.ticker,))
            else:
                cursor.execute("UPDATE portfolio SET quantity = ? WHERE ticker = ?", (new_qty, alert.ticker))
                
            # Nakit bakiyesini artir
            new_cash = cash + total_cost
            cursor.execute("UPDATE portfolio SET quantity = ? WHERE ticker = 'TRY'", (new_cash,))
            
        # 3. Gerceklesen islemi trades tablosuna yaz
        cursor.execute(
            "INSERT INTO trades (ticker, action, price, quantity, total_value) VALUES (?, ?, ?, ?, ?)",
            (alert.ticker, alert.action, alert.price, alert.quantity, total_cost)
        )
        conn.commit()
        
        logger.info(
            f"Islem Basarili{mode_text} -> Hisse: {alert.ticker} | "
            f"Yon: {alert.action} | Fiyat: {alert.price} | Miktar: {alert.quantity} | Toplam: {total_cost} TL"
        )
        
        # Basarili Islem Bildirimi (Arka Planda)
        emoji = "🟢" if alert.action == "AL" else "🔴"
        success_msg = (
            f"{emoji} <b>ISLEM BASARILI{mode_text}</b>\n\n"
            f"📌 <b>Hisse:</b> #{alert.ticker}\n"
            f"👉 <b>Yon:</b> {alert.action}\n"
            f"💵 <b>Fiyat:</b> {alert.price:.2f} TL\n"
            f"📦 <b>Miktar:</b> {alert.quantity} Lot\n"
            f"💰 <b>Toplam:</b> {total_cost:.2f} TL"
        )
        background_tasks.add_task(telegram_utils.send_telegram_message, success_msg)
        
        # 4. Gercek BIST Emir Otomasyonunu Arka Planda Tetikle (Sadece DEMO_MODE = False ise)
        if not demo_mode:
            background_tasks.add_task(order_executor.execute_order, alert.ticker, alert.action, alert.price, alert.quantity)
            logger.info("Gercek emir otomasyonu arka planda tetiklendi.")
        else:
            logger.info("Sanal Mod (Demo) aktif. Gercek emir gonderilmedi.")
        
        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "message": f"Islem simule edildi. Mod: {'Sanal (Demo)' if demo_mode else 'Gercek'}",
                "data": alert.model_dump()
            }
        )
        
    except Exception as e:
        conn.rollback()
        logger.error(f"Webhook islenirken hata olustu: {str(e)}")
        raise HTTPException(status_code=500, detail="Sinyal islenirken sunucu hatasi olustu.")
    finally:
        conn.close()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000)

