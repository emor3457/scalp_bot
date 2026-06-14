import time
import logging
import asyncio
import yfinance as yf
import pandas as pd
import numpy as np
import database
import trade_manager

logger = logging.getLogger("BistScalpBot")

BIST30_TICKERS = [
    "THYAO", "EREGL", "ASELS", "YKBNK", "AKBNK", "TUPRS", "KCHOL", "SAHOL", "GARAN", "ISCTR",
    "BIMAS", "SISE", "PGSUS", "EKGYO", "TCELL", "FROTO", "TOASO", "PETKM", "KOZAA", "KOZAL",
    "TAVHL", "ENKAI", "SASA", "HEKTS", "GUBRF", "DOAS", "ODAS", "KRDMD", "VESTL", "ARCLK",
    "ALARK", "ASTOR", "SMRTG", "ALFAS", "GESAN", "KMPUR", "ENJSA", "TTRAK", "YYLGD", "GWIND",
    "TKFEN", "MGROS", "CCOLA", "AEFES", "SOKM", "OTKAR", "KORDS", "BRISA", "SELEC", "ALBRK"
]

def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Pandas kullanarak teknik analiz gostergelerini hesaplar.
    """
    df = df.copy()
    if len(df) < 50:
        return df

    # 1. EMA (Exponential Moving Average)
    df['EMA9'] = df['Close'].ewm(span=9, adjust=False).mean()
    df['EMA21'] = df['Close'].ewm(span=21, adjust=False).mean()
    df['EMA50'] = df['Close'].ewm(span=50, adjust=False).mean()

    # 2. RSI (Relative Strength Index)
    delta = df['Close'].diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    
    avg_gain = gain.ewm(alpha=1/14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/14, adjust=False).mean()
    
    rs = avg_gain / np.where(avg_loss == 0, 1e-10, avg_loss)
    df['RSI'] = 100 - (100 / (1 + rs))

    # 3. MACD
    ema12 = df['Close'].ewm(span=12, adjust=False).mean()
    ema26 = df['Close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = ema12 - ema26
    df['MACD_Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
    df['MACD_Hist'] = df['MACD'] - df['MACD_Signal']

    # 4. Bollinger Bands (20, 2)
    df['BB_Mid'] = df['Close'].rolling(window=20).mean()
    df['BB_Std'] = df['Close'].rolling(window=20).std()
    df['BB_Upper'] = df['BB_Mid'] + (2 * df['BB_Std'])
    df['BB_Lower'] = df['BB_Mid'] - (2 * df['BB_Std'])

    # 5. Volume SMA (20)
    df['Vol_SMA20'] = df['Volume'].rolling(window=20).mean()

    return df

def _fetch_history(stock: yf.Ticker, period: str, interval: str) -> pd.DataFrame:
    """Senkron olarak yfinance history indirir. Thread pool icinde calisacaktir."""
    return stock.history(period=period, interval=interval)

async def analyze_ticker(ticker: str, semaphore: asyncio.Semaphore) -> dict:
    """
    Belirli bir BIST hissesi icin yfinance verilerini asenkron indirerek 
    teknik analiz yapar ve Al/Sat kararini dondurur.
    """
    yahoo_ticker = f"{ticker}.IS"
    async with semaphore:
        try:
            logger.info(f"Teknik analiz icin veri indiriliyor -> {yahoo_ticker}")
            stock = yf.Ticker(yahoo_ticker)
            # Scalp islemi icin 5 dakikalik kisa vade veriler (Thread pool'da)
            df = await asyncio.to_thread(_fetch_history, stock, "5d", "5m")
            
            if df.empty or len(df) < 50:
                logger.warning(f"{ticker} icin yetersiz veri (Satir sayisi: {len(df)})")
                return {"ticker": ticker, "action": "HOLD", "price": 0.0, "quantity": 0.0, "reasoning": "Yetersiz piyasa verisi."}

            df = calculate_indicators(df)
            
            # Son iki barin verileri
            curr = df.iloc[-1]
            prev = df.iloc[-2]

            close = float(curr['Close'])
            volume = float(curr['Volume'])
            
            # Indikator degerleri
            ema9, ema21, ema50 = float(curr['EMA9']), float(curr['EMA21']), float(curr['EMA50'])
            rsi = float(curr['RSI'])
            macd, macd_sig = float(curr['MACD']), float(curr['MACD_Signal'])
            bb_upper, bb_lower = float(curr['BB_Upper']), float(curr['BB_Lower'])
            vol_sma20 = float(curr['Vol_SMA20']) if curr['Vol_SMA20'] > 0 else 1.0

            # Gecmis indikator degerleri
            prev_macd, prev_macd_sig = float(prev['MACD']), float(prev['MACD_Signal'])
            prev_rsi = float(prev['RSI'])

            # Temel durum analizleri
            is_bullish_trend = close > ema50 and ema9 > ema21
            is_bearish_trend = close < ema50 or ema9 < ema21
            
            vol_ratio = volume / vol_sma20
            vol_pct = (vol_ratio - 1.0) * 100

            # Kesisimler
            macd_crossed_above = prev_macd <= prev_macd_sig and macd > macd_sig
            macd_crossed_below = prev_macd >= prev_macd_sig and macd < macd_sig
            rsi_crossed_above_30 = prev_rsi <= 30 and rsi > 30
            rsi_crossed_below_70 = prev_rsi >= 70 and rsi < 70

            # Bollinger temasi
            touches_lower = close <= bb_lower * 1.003
            touches_upper = close >= bb_upper * 0.997

            # Veritabani baglantisi ile mevcut portfoyu sorgula (Asenkron)
            conn = await database.get_async_db_connection()
            try:
                # 1. TRY Nakit bakiye sorgula
                async with conn.execute("SELECT quantity FROM portfolio WHERE ticker = 'TRY'") as cursor:
                    try_row = await cursor.fetchone()
                    cash = try_row["quantity"] if try_row else 0.0

                # 2. Hisse varligi sorgula
                async with conn.execute("SELECT quantity FROM portfolio WHERE ticker = ?", (ticker,)) as cursor:
                    stock_row = await cursor.fetchone()
                    held_qty = stock_row["quantity"] if stock_row else 0.0
            finally:
                await conn.close()

            action = "HOLD"
            reasoning = ""
            quantity = 0.0

            # ALIM KARARI (BUY)
            is_technical_buy = is_bullish_trend and (macd_crossed_above or rsi_crossed_above_30 or (touches_lower and rsi < 40))
            is_flow_buy = vol_ratio >= 1.5 and rsi > 50  # Hacim ortalamanin 1.5 kati ve RSI 50 uzeri momentumlu
            
            if is_technical_buy and is_flow_buy:
                action = "AL"
                target_amount = min(cash * 0.1, 10000.0)
                if target_amount < 500.0:
                    target_amount = min(cash, 500.0)
                
                quantity = float(int(target_amount / close))
                
                if quantity >= 1.0:
                    reasoning = (
                        f"Dostlar, #{ticker} senedinde 5 dakikalik grafikte ani Hacim Patlamasi tespit edildi. "
                        f"Fiyat, EMA 50 ({ema50:.2f} TL) uzerinde ve MACD pozitif. "
                        f"Hacim: Ortalamanin %{vol_pct:.0f} uzerinde. RSI: {rsi:.1f}. "
                        f"Kisa vadeli para girisi tespit edildigi icin bu seviyelerden scalp yonlu pozisyon acmak makuldur."
                    )
                else:
                    action = "HOLD"
                    reasoning = f"#{ticker} icin AL sinyali var ancak bakiye yetersiz."

            # SATIM KARARI (SELL)
            elif held_qty > 0 and (is_bearish_trend or macd_crossed_below or rsi_crossed_below_70 or touches_upper):
                action = "SAT"
                quantity = held_qty
                
                trigger_reason = ""
                if macd_crossed_below:
                    trigger_reason = "MACD tetik cizgisini tepede asagi kesti."
                elif rsi_crossed_below_70:
                    trigger_reason = f"RSI {rsi:.1f} seviyesinde asiri alim bolgesinden geri cekildi."
                else:
                    trigger_reason = "Bollinger ust direncine carpildi veya trend kirildi."

                reasoning = (
                    f"Degerli ortaklar, #{ticker} pozisyonumuzda kari cebe koyma vakti. "
                    f"{trigger_reason} Scalp yaparken inatlasilmaz, momentum bittiğinde nakde gecilir. "
                    f"Eldeki {held_qty} lot hissenin tamami satilmalidir."
                )

            # Karar yoksa analiz ozeti
            if action == "HOLD":
                trend_str = "Yukari" if is_bullish_trend else ("Asagi" if is_bearish_trend else "Yatay")
                macd_str = "Pozitif kesisim" if macd > macd_sig else "Negatif kesisim"
                reasoning = f"Trend: {trend_str} | RSI: {rsi:.1f} (Notr) | MACD: {macd_str} | Hacim: {vol_ratio:.2f}x. Islem icin kosullar henüz olgunlasmadi."

            return {
                "ticker": ticker,
                "action": action,
                "price": close,
                "quantity": quantity,
                "reasoning": reasoning
            }

        except Exception as e:
            logger.error(f"{ticker} analiz edilirken beklenmedik hata: {str(e)}")
            return {"ticker": ticker, "action": "HOLD", "price": 0.0, "quantity": 0.0, "reasoning": f"Hata: {str(e)}"}

async def scan_all_and_report() -> dict:
    """
    BIST30 hisselerini ayni anda asenkron olarak tarar (Semaphore ile hiz sinirlamasi uygulanir).
    Al/Sat sinyali olusan hisseleri asenkron olarak bot veritabanina ve simulyasyona iletir.
    """
    logger.info("BIST30 hisseleri asenkron taranıyor...")
    start_time = time.time()
    
    # Rate limit engellemek icin ayni anda en fazla 5 istek yapilacak
    sem = asyncio.Semaphore(5)
    
    # Tum analiz gorevlerini hazirla
    tasks = [analyze_ticker(ticker, sem) for ticker in BIST30_TICKERS]
    
    # Eşzamanlı (paralel) olarak analizleri baslat
    results = await asyncio.gather(*tasks)
    
    signals_sent = []
    for analysis in results:
        if analysis["action"] in ["AL", "SAT"] and analysis["quantity"] > 0:
            signals_sent.append(analysis)
            # Asenkron olarak sinyali bota ilet
            await inject_signal_to_bot(analysis)
            
    scan_duration = time.time() - start_time
    
    summary = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
        "scan_duration_seconds": round(scan_duration, 2),
        "total_scanned": len(BIST30_TICKERS),
        "signals_generated_count": len(signals_sent),
        "signals": signals_sent,
        "details": results
    }
    logger.info(f"Tarama tamamlandı. Taranan: {len(BIST30_TICKERS)} | Sinyal: {len(signals_sent)} | Sure: {summary['scan_duration_seconds']} sn")
    return summary

async def inject_signal_to_bot(analysis: dict):
    """
    Uretilen sinyali asenkron trade_manager uzerinden veritabanina iletir.
    """
    ticker = analysis["ticker"]
    action = analysis["action"]
    price = analysis["price"]
    quantity = analysis["quantity"]
    reasoning = analysis["reasoning"]
    
    try:
        # trade_manager ile asenkron islet
        await trade_manager.process_trade_signal(
            ticker=ticker,
            action=action,
            price=price,
            quantity=quantity,
            reasoning=reasoning
        )
    except trade_manager.TradeExecutionError as e:
        logger.warning(f"Auto-Analyst islem iptal edildi: {str(e)}")
    except Exception as e:
        logger.error(f"Auto-Analyst sinyal islenirken beklenmedik hata: {str(e)}")
