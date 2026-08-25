import os
import logging
import sys
import asyncio
import base64
import secrets

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
import mtf_data
import strategy_engine
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

app = FastAPI(title="BIST Scalp Bot v2 | Multi-Timeframe (15m, 1h, 4h, 1d) + Kar Alma Stratejileri")

# ---------------------------------------------------------------------------
# Dashboard/API kimlik dogrulama (Basic Auth)
# - Sadece DASHBOARD_AUTH_TOKEN acikca set edildiyse aktif olur.
# - Bos ise tarayici kullanici adi / sifre sormaz.
# ---------------------------------------------------------------------------
DASHBOARD_AUTH_TOKEN = os.getenv("DASHBOARD_AUTH_TOKEN", "").strip()

PROTECTED_PATHS = (
    "/dashboard", "/portfolio", "/trades", "/signals",
    "/scan", "/api/backtest", "/api/deep-analysis", "/config",
    "/api/mtf-analysis", "/api/strategies", "/api/positions"
)


@app.middleware("http")
async def dashboard_auth_middleware(request: Request, call_next):
    path = request.url.path
    if path in PROTECTED_PATHS and DASHBOARD_AUTH_TOKEN:
        auth = request.headers.get("Authorization", "")
        expected_basic = "Basic " + base64.b64encode(
            f"borsa:{DASHBOARD_AUTH_TOKEN}".encode("utf-8")
        ).decode("ascii")
        expected_bearer = "Bearer " + DASHBOARD_AUTH_TOKEN
        valid = (
            secrets.compare_digest(auth, expected_basic)
            or secrets.compare_digest(auth, expected_bearer)
        )
        if not valid:
            return JSONResponse(
                status_code=401,
                content={"detail": "Yetkisiz erisim. Gecersiz kimlik bilgisi."},
                headers={"WWW-Authenticate": 'Basic realm="BIST Bot"'},
            )
    return await call_next(request)


async def periodic_position_evaluator():
    """Acik pozisyonlarin TP/SL/Trailing durumunu her 60 saniyede bir kontrol eder."""
    await asyncio.sleep(5)
    while True:
        try:
            await trade_manager.evaluate_open_positions()
        except Exception as e:
            logger.error(f"Pozisyon denetleyicisinde hata: {str(e)}")
        await asyncio.sleep(60)


async def periodic_scan_loop():
    """Periyodik BIST50 Multi-Timeframe tarama dongusu (Her 15 dakikada bir)."""
    await asyncio.sleep(10)
    while True:
        try:
            import datetime
            import pytz
            tz = pytz.timezone("Europe/Istanbul")
            now = datetime.datetime.now(tz)
            # Hafta ici mi ve borsa acik mi kontrol et (Pazartesi=0, Cuma=4)
            # BIST seans saatleri 10:00 - 18:10
            if now.weekday() < 5 and (10 <= now.hour < 18):
                logger.info("Periyodik BIST Multi-Timeframe taramasi baslatiliyor...")
                await auto_analyst.scan_all_and_report()
            else:
                logger.debug("BIST kapali oldugu icin periyodik tarama atlandi.")
        except Exception as e:
            logger.error(f"Periyodik tarama dongusunde hata: {str(e)}")
        
        await asyncio.sleep(900)  # 15 dakika bekle


# Sunucu baslarken veritabani kontrolu
@app.on_event("startup")
async def startup_event():
    logger.info("Uygulama baslatiliyor. Veritabani kontrol ediliyor...")
    database.init_db()
    asyncio.create_task(periodic_position_evaluator())
    asyncio.create_task(periodic_scan_loop())
    logger.info("Periyodik MTF tarama motoru ve pozisyon takipcisi arka planda baslatildi.")


# TradingView'dan gelecek JSON verisi icin Pydantic modeli
class WebhookAlert(BaseModel):
    ticker: str = Field(..., pattern=r"^[A-Za-z0-9.]{1,10}$", description="Hisse adi (Orn: KRONT, ARFYE)")
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


class StrategySelectRequest(BaseModel):
    strategy_mode: Literal["auto", "scaling", "swing", "momentum"]


@app.get("/")
def read_root():
    return {"status": "running", "message": "BIST Scalp Bot v2 Multi-Timeframe Webhook Receiver is active."}


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
            
            current_price = await market_data.get_stock_price(ticker)
            if current_price is None:
                current_price = avg_cost
                
            current_value = quantity * current_price
            
            if ticker == 'TRY':
                pnl_value = 0.0
                pnl_percent = 0.0
            else:
                total_cost = quantity * avg_cost
                pnl_value = current_value - total_cost
                pnl_percent = ((current_price - avg_cost) / avg_cost * 100) if avg_cost > 0 else 0.0
                
            item.update({
                "current_price": round(current_price, 2),
                "current_value": round(current_value, 2),
                "pnl_value": round(pnl_value, 2),
                "pnl_percent": round(pnl_percent, 2)
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


@app.get("/api/positions")
async def get_positions():
    """Tum aktif acik pozisyonlari (TP/SL/Trailing Stop ve PnL verileriyle) dondurur."""
    try:
        positions = await trade_manager.get_all_open_positions()
        return {"status": "success", "open_positions": positions}
    except Exception as e:
        logger.error(f"Pozisyonlar alinamadi: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Pozisyonlar alinamadi: {str(e)}")


@app.post("/api/positions/close/{ticker}")
async def close_position_api(ticker: str):
    """Belirtilen hissenin acik pozisyonunu manuel olarak piyasa fiyatindan kapatir."""
    try:
        clean_ticker = ticker.upper().replace(".IS", "")
        conn = await database.get_async_db_connection()
        try:
            async with conn.execute("SELECT id, current_quantity FROM open_positions WHERE ticker = ? AND status = 'OPEN'", (clean_ticker,)) as cursor:
                pos = await cursor.fetchone()
                if not pos:
                    raise HTTPException(status_code=404, detail=f"{clean_ticker} icin acik pozisyon bulunamadi.")
                
                curr_price = await market_data.get_stock_price(clean_ticker) or 0.0
                await trade_manager.close_position_partial_or_full(pos["id"], clean_ticker, pos["current_quantity"], curr_price, "MANUAL")
                return {"status": "success", "message": f"{clean_ticker} pozisyonu kapatildi."}
        finally:
            await conn.close()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Pozisyon kapatilirken hata [{ticker}]: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/mtf-analysis")
async def get_mtf_analysis_api(ticker: str = "THYAO"):
    """Belirtilen hisse icin 4 zaman dilimi detayli analiz sonucunu dondurur."""
    try:
        clean_ticker = ticker.upper().replace(".IS", "")
        analysis = await auto_analyst.analyze_single_ticker(clean_ticker)
        return {"status": "success", "data": analysis}
    except Exception as e:
        logger.error(f"MTF Analiz API hatasi [{ticker}]: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Analiz hatasi: {str(e)}")


@app.get("/api/strategies")
async def get_strategies_api():
    """Strateji aciklamalarini ve mevcut aktif modu dondurur."""
    try:
        current_mode = await database.get_setting("strategy_mode", "auto")
        return {
            "status": "success",
            "active_strategy_mode": current_mode,
            "strategies": strategy_engine.STRATEGY_DESCRIPTIONS,
            "max_positions": strategy_engine.MAX_CONCURRENT_POSITIONS,
            "max_portfolio_ratio_pct": strategy_engine.MAX_POSITION_PORTFOLIO_RATIO * 100
        }
    except Exception as e:
        logger.error(f"Strateji bilgisi alinamadi: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/strategy/select")
async def select_strategy_mode_api(req: StrategySelectRequest):
    """Aktif strateji modunu degistirir (auto, scaling, swing, momentum)."""
    try:
        await database.set_setting("strategy_mode", req.strategy_mode)
        logger.info(f"Strateji modu guncellendi -> {req.strategy_mode}")
        return {
            "status": "success",
            "strategy_mode": req.strategy_mode,
            "description": strategy_engine.STRATEGY_DESCRIPTIONS.get(req.strategy_mode)
        }
    except Exception as e:
        logger.error(f"Strateji secilemedi: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/deep-analysis")
async def get_deep_analysis(ticker: str = "THYAO"):
    try:
        from bist_analysis import build_markdown
        ticker = ticker.upper().replace(".IS", "")
        md = await build_markdown(ticker)
        return {"ticker": ticker, "markdown": md}
    except Exception as e:
        logger.error(f"Derin analiz hatasi [{ticker}]: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Derin analiz sirasinda hata: {str(e)}")


@app.get("/scan")
async def trigger_scan(report_only: bool = True):
    """Manuel BIST Multi-Timeframe taramasi."""
    try:
        logger.info(f"Manuel BIST MTF taramasi tetiklendi (report_only={report_only})...")
        report = await auto_analyst.scan_all_and_report(report_only=report_only)
        return report
    except Exception as e:
        logger.error(f"Manuel tarama sirasinda hata: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Tarama hatasi: {str(e)}")


@app.get("/config")
def get_config():
    demo_mode = os.getenv("DEMO_MODE", "True").strip().lower() == "true"
    return {"demo_mode": demo_mode}


@app.post("/webhook")
async def receive_webhook(
    alert: WebhookAlert, 
    request: Request, 
    background_tasks: BackgroundTasks,
    x_webhook_token: str = Header(None, alias="X-Webhook-Token"),
    token: str = None
):
    client_host = request.client.host if request.client else "unknown"
    logger.info(f"Webhook istegi alindi. Kaynak IP: {client_host}")
    
    webhook_secret = os.getenv("WEBHOOK_SECRET_TOKEN", "").strip()
    provided_token = x_webhook_token or token
    
    if not webhook_secret:
        logger.error("WEBHOOK_SECRET_TOKEN tanimlanmamis! Guvenlik icin tum webhook istekleri reddedildi.")
        raise HTTPException(status_code=503, detail="Webhook servisi aktif degil. WEBHOOK_SECRET_TOKEN gerekli.")
    
    if not provided_token or not secrets.compare_digest(provided_token, webhook_secret):
        logger.warning(f"Yetkisiz webhook istegi engellendi. Kaynak IP: {client_host}")
        raise HTTPException(status_code=401, detail="Yetkisiz erisim. Gecersiz token.")

    try:
        result = await trade_manager.process_trade_signal(
            ticker=alert.ticker,
            action=alert.action,
            price=alert.price,
            quantity=alert.quantity
        )
        
        if result.get("trigger_real_order"):
            background_tasks.add_task(
                order_executor.execute_order, 
                alert.ticker, 
                alert.action, 
                alert.price, 
                alert.quantity
            )
            logger.info("Gercek emir otomasyonu arka planda tetiklendi.")
            
        return JSONResponse(status_code=200, content=result)
        
    except trade_manager.TradeExecutionError as e:
        return JSONResponse(status_code=400, content={"status": "rejected", "reason": str(e), **e.details})
    except Exception as e:
        logger.error(f"Webhook islenirken beklenmedik hata: {str(e)}")
        raise HTTPException(status_code=500, detail="Sinyal islenirken sunucu hatasi olustu.")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000)