import time
import logging
import asyncio
import yfinance as yf
import pandas as pd
import numpy as np
import database

logger = logging.getLogger("BistScalpBot")

main_loop = None

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
    Herhangi bir harici C-based kutuphaneye (ta-lib vb.) ihtiyac duymaz.
    """
    df = df.copy()
    if len(df) < 50:
        return df

    # 1. EMA (Exponential Moving Average)
    df['EMA9'] = df['Close'].ewm(span=9, adjust=False).mean()
    df['EMA21'] = df['Close'].ewm(span=21, adjust=False).mean()
    df['EMA50'] = df['Close'].ewm(span=50, adjust=False).mean()

    # 2. RSI (Relative Strength Index) - Wilder's Smoothing
    delta = df['Close'].diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    
    avg_gain = gain.ewm(alpha=1/14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/14, adjust=False).mean()
    
    # Sifira bolme hatasini engelle
    rs = avg_gain / np.where(avg_loss == 0, 1e-10, avg_loss)
    df['RSI'] = 100 - (100 / (1 + rs))

    # 3. MACD (Moving Average Convergence Divergence)
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

def analyze_ticker(ticker: str) -> dict:
    """
    Belirli bir BIST hissesi icin yfinance verilerini (5 dakikalik) kullanarak 
    salt teknik analiz yapar (Hacim patlamalari ve momentum).
    """
    yahoo_ticker = f"{ticker}.IS"
    try:
        logger.info(f"Teknik analiz icin veri indiriliyor -> {yahoo_ticker}")
        stock = yf.Ticker(yahoo_ticker)
        # Scalp islemi icin 5 dakikalik kisa vade veriler kullanalim
        df = stock.history(period="5d", interval="5m")
        
        if df.empty or len(df) < 50:
            logger.warning(f"{ticker} icin yetersiz veri (Satir sayisi: {len(df)})")
            return {"ticker": ticker, "action": "HOLD", "price": 0.0, "quantity": 0.0, "reasoning": "Yetersiz piyasa verisi."}

        df = calculate_indicators(df)
        
        # Son iki barin verilerini alalim (kesisimler ve anlik durumlar icin)
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

        # Gecmis indikator degerleri (crossover tespiti icin)
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

        # Veritabani baglantisi ile mevcut portfoyu sorgula
        conn = database.get_db_connection()
        cursor = conn.cursor()
        
        # 1. TRY Nakit bakiye sorgula
        cursor.execute("SELECT quantity FROM portfolio WHERE ticker = 'TRY'")
        try_row = cursor.fetchone()
        cash = try_row["quantity"] if try_row else 0.0

        # 2. Hisse varligi sorgula
        cursor.execute("SELECT quantity FROM portfolio WHERE ticker = ?", (ticker,))
        stock_row = cursor.fetchone()
        held_qty = stock_row["quantity"] if stock_row else 0.0
        
        conn.close()

        action = "HOLD"
        reasoning = ""
        quantity = 0.0

        # ALIM KARARI (BUY)
        # Teknik sinyaller (Volume Spikes + Momentum)
        is_technical_buy = is_bullish_trend and (macd_crossed_above or rsi_crossed_above_30 or (touches_lower and rsi < 40))
        # Hacim patlamasi ve para girisi teyidi
        is_flow_buy = vol_ratio >= 1.5 and rsi > 50  # Hacim ortalamanin 1.5 kati ve RSI 50 uzeri momentumlu
        
        if is_technical_buy and is_flow_buy:
            action = "AL"
            target_amount = min(cash * 0.1, 10000.0)
            if target_amount < 500.0:
                target_amount = min(cash, 500.0)
            
            quantity = float(int(target_amount / close))
            
            if quantity >= 1.0:
                reasoning = (
                    f"Dostlar, #{ticker} senedinde 5 dakikalık grafikte ani Hacim Patlaması tespit edildi. "
                    f"Fiyat, EMA 50 ({ema50:.2f} TL) üzerinde ve MACD pozitif. "
                    f"Hacim: Ortalamanın %{vol_pct:.0f} üzerinde. RSI: {rsi:.1f}. "
                    f"Kısa vadeli para girişi tespit edildiği için bu seviyelerden scalp yönlü pozisyon açmak makuldür."
                )
            else:
                action = "HOLD"
                reasoning = f"#{ticker} için AL sinyali var ancak bakiye yetersiz."

        # SATIM KARARI (SELL)
        elif held_qty > 0 and (is_bearish_trend or macd_crossed_below or rsi_crossed_below_70 or touches_upper):
            action = "SAT"
            quantity = held_qty
            
            trigger_reason = ""
            if macd_crossed_below:
                trigger_reason = "MACD tetik çizgisini tepede aşağı kesti."
            elif rsi_crossed_below_70:
                trigger_reason = f"RSI {rsi:.1f} seviyesinde asiri alim bolgesinden geri cekildi."
            else:
                trigger_reason = "Bollinger ust direncine carpildi veya trend kirildi."

            reasoning = (
                f"Değerli ortaklar, #{ticker} pozisyonumuzda kârı cebe koyma vakti. "
                f"{trigger_reason} Scalp yaparken inatlaşılmaz, momentum bittiğinde nakde geçilir. "
                f"Eldeki {held_qty} lot hissenin tamamı satılmalıdır."
            )

        # Karar yoksa analiz ozeti
        if action == "HOLD":
            trend_str = "Yukarı" if is_bullish_trend else ("Aşağı" if is_bearish_trend else "Yatay")
            macd_str = "Pozitif kesişim" if macd > macd_sig else "Negatif kesişim"
            reasoning = f"Trend: {trend_str} | RSI: {rsi:.1f} (Nötr) | MACD: {macd_str} | Hacim: {vol_ratio:.2f}x. İşlem için koşullar henüz olgunlaşmadı."

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

def scan_all_and_report() -> dict:
    """
    Tum BIST 30 secili hisselerini tarar ve bir analiz ozet raporu doner.
    Al/Sat sinyali olusan hisseleri veritabanina ve simulyasyona iletir.
    """
    logger.info("Hisseler taranıyor...")
    results = []
    signals_sent = []
    
    start_time = time.time()
    
    for ticker in BIST30_TICKERS:
        analysis = analyze_ticker(ticker)
        results.append(analysis)
        
        # Sinyal olustuysa dogrudan simule et/kaydet
        if analysis["action"] in ["AL", "SAT"] and analysis["quantity"] > 0:
            signals_sent.append(analysis)
            # Bu sinyali veritabanina / webhook akisina sokalim
            inject_signal_to_bot(analysis)
            # API hiz siniri yememek icin kısa bir ara verelim
            time.sleep(0.5)
            
    scan_duration = time.time() - start_time
    
    summary = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
        "scan_duration_seconds": round(scan_duration, 2),
        "total_scanned": len(BIST30_TICKERS),
        "signals_generated_count": len(signals_sent),
        "signals": signals_sent,
        "details": results
    }
    logger.info(f"Tarama tamamlandı. Taranan: {len(BIST30_TICKERS)} | Sinyal: {len(signals_sent)}")
    return summary

def inject_signal_to_bot(analysis: dict):
    """
    Uretilen sinyali dogrudan veritabani islem motoruna iletir (webhook endpoint'ini taklit eder).
    Lokalde calisildigi icin asenkron deadlock riskinden kacinmak adina dogrudan veritabani islemlerini yapar.
    """
    ticker = analysis["ticker"]
    action = analysis["action"]
    price = analysis["price"]
    quantity = analysis["quantity"]
    reasoning = analysis["reasoning"]
    
    conn = database.get_db_connection()
    cursor = conn.cursor()
    
    demo_mode = True # Auto-analyst sinyalleri varsayilan demo modda isletilir.
    mode_text = " (Simule)"
    
    try:
        # 1. Sinyali kaydet
        cursor.execute(
            "INSERT INTO signals (ticker, action, price, quantity, reasoning) VALUES (?, ?, ?, ?, ?)",
            (ticker, action, price, quantity, reasoning)
        )
        conn.commit()
        
        # 2. Islem Hesaplamalari
        total_cost = price * quantity
        
        cursor.execute("SELECT quantity FROM portfolio WHERE ticker = 'TRY'")
        try_row = cursor.fetchone()
        cash = try_row["quantity"] if try_row else 0.0
        
        if action == "AL":
            if cash < total_cost:
                logger.warning(f"Auto-Analyst: Bakiye yetersiz! {ticker} alimi iptal edildi.")
                return
            
            # Nakit dusur
            new_cash = cash - total_cost
            cursor.execute("UPDATE portfolio SET quantity = ? WHERE ticker = 'TRY'", (new_cash,))
            
            # Portfoye ekle/guncelle
            cursor.execute("SELECT quantity, average_cost FROM portfolio WHERE ticker = ?", (ticker,))
            stock_row = cursor.fetchone()
            
            if stock_row:
                old_qty = stock_row["quantity"]
                old_cost = stock_row["average_cost"]
                new_qty = old_qty + quantity
                new_avg_cost = ((old_qty * old_cost) + total_cost) / new_qty
                cursor.execute(
                    "UPDATE portfolio SET quantity = ?, average_cost = ? WHERE ticker = ?",
                    (new_qty, new_avg_cost, ticker)
                )
            else:
                cursor.execute(
                    "INSERT INTO portfolio (ticker, quantity, average_cost) VALUES (?, ?, ?)",
                    (ticker, quantity, price)
                )
                
        elif action == "SAT":
            cursor.execute("SELECT quantity FROM portfolio WHERE ticker = ?", (ticker,))
            stock_row = cursor.fetchone()
            stock_qty = stock_row["quantity"] if stock_row else 0.0
            
            if stock_qty < quantity:
                logger.warning(f"Auto-Analyst: Elde yetersiz {ticker} hissesi var. Satis iptal.")
                return
                
            # Hisseyi dusur veya sil
            new_qty = stock_qty - quantity
            if new_qty == 0:
                cursor.execute("DELETE FROM portfolio WHERE ticker = ?", (ticker,))
            else:
                cursor.execute("UPDATE portfolio SET quantity = ? WHERE ticker = ?", (new_qty, ticker))
                
            # Nakit artir
            new_cash = cash + total_cost
            cursor.execute("UPDATE portfolio SET quantity = ? WHERE ticker = 'TRY'", (new_cash,))
            
        # 3. Gerceklesen islemi trades tablosuna yaz
        cursor.execute(
            "INSERT INTO trades (ticker, action, price, quantity, total_value, reasoning) VALUES (?, ?, ?, ?, ?, ?)",
            (ticker, action, price, quantity, total_cost, reasoning)
        )
        conn.commit()
        
        logger.info(
            f"Auto-Analyst Islem Basarili -> Hisse: {ticker} | "
            f"Yon: {action} | Fiyat: {price} | Miktar: {quantity} | Toplam: {total_cost} TL"
        )
        
        # 4. Telegram Bildirimi Gonder (Gerekceli HTML formatli)
        emoji = "🟢" if action == "AL" else "🔴"
        telegram_msg = (
            f"{emoji} <b>DUAYEN BORSA SİNYALİ{mode_text}</b>\n\n"
            f"📌 <b>Hisse:</b> #{ticker}\n"
            f"👉 <b>Yön:</b> {action}\n"
            f"💵 <b>Fiyat:</b> {price:.2f} TL\n"
            f"📦 <b>Miktar:</b> {quantity:.0f} Lot\n"
            f"💰 <b>Toplam Değer:</b> {total_cost:.2f} TL\n\n"
            f"✍️ <b>Analiz Gerekçesi (30 Yıllık Tecrübe):</b>\n<i>{reasoning}</i>"
        )
        
        # Telegram fonksiyonunu cagir
        from telegram_utils import send_telegram_message
        try:
            success = send_telegram_message(telegram_msg)
            if success:
                logger.info("Auto-Analyst: Telegram bildirimi basariyla gonderildi.")
            else:
                logger.warning("Auto-Analyst: Telegram bildirimi gonderilemedi.")
        except Exception as te:
            logger.error(f"Auto-Analyst Telegram gonderim hatasi: {str(te)}")
            
    except Exception as e:
        conn.rollback()
        logger.error(f"Auto-Analyst sinyal islenirken hata: {str(e)}")
    finally:
        conn.close()
