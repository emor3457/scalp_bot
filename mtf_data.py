"""
mtf_data.py — Multi-Timeframe Veri ve Teknik Analiz Motoru (v2)
--------------------------------------------------------------
BIST hisseleri icin 4 ayri zaman diliminde (15m, 1h, 4h, 1d)
OHLCV verilerini paralel olarak ceker ve teknik indikatorleri hesaplar.

Timeframe Dagilimi:
    - 15dk (15m): Giris zamanlamasi, kisa vadeli momentum (%15 agirlik)
    - 1 Saat (1h): Ana sinyal uretici (%30 agirlik)
    - 4 Saat (4h): Trend dogrulama (%35 agirlik)
    - Gunluk (1d): Makro trend filtresi (%20 agirlik)
"""

import time
import logging
import asyncio
import yfinance as yf
import pandas as pd
import numpy as np

logger = logging.getLogger("BistScalpBot")

# Onbellek: { f"{ticker}_{tf}": (data_dict, timestamp) }
MTF_CACHE = {}
CACHE_TTL = {
    "15m": 180,   # 3 dakika
    "1h": 600,    # 10 dakika
    "4h": 1200,   # 20 dakika
    "1d": 3600    # 1 saat
}


def _calc_indicators(df: pd.DataFrame, tf_name: str) -> dict:
    """Tek bir timeframe DataFrame'i uzerinde temel ve gelismis gostergeleri hesaplar."""
    if df is None or len(df) < 15:
        return {"valid": False, "tf": tf_name, "error": "Yetersiz veri"}

    df = df.copy()

    # Temel Fiyatlar
    current_price = float(df['Close'].iloc[-1])
    prev_close = float(df['Close'].iloc[-2]) if len(df) > 1 else current_price
    change_pct = ((current_price - prev_close) / prev_close * 100) if prev_close > 0 else 0.0

    # EMA'lar
    df['EMA9'] = df['Close'].ewm(span=9, adjust=False).mean()
    df['EMA21'] = df['Close'].ewm(span=21, adjust=False).mean()
    df['EMA50'] = df['Close'].ewm(span=50, adjust=False).mean()
    if len(df) >= 150:
        df['EMA200'] = df['Close'].ewm(span=200, adjust=False).mean()
    else:
        df['EMA200'] = df['EMA50']

    # RSI (14)
    delta = df['Close'].diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_g = gain.ewm(alpha=1/14, adjust=False).mean()
    avg_l = loss.ewm(alpha=1/14, adjust=False).mean()
    rs = avg_g / np.where(avg_l == 0, 1e-10, avg_l)
    df['RSI'] = 100 - (100 / (1 + rs))

    # MACD (12, 26, 9)
    ema12 = df['Close'].ewm(span=12, adjust=False).mean()
    ema26 = df['Close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = ema12 - ema26
    df['MACD_Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
    df['MACD_Hist'] = df['MACD'] - df['MACD_Signal']

    # Bollinger Bands (20, 2)
    bb_period = min(20, len(df))
    df['BB_Mid'] = df['Close'].rolling(bb_period).mean()
    df['BB_Std'] = df['Close'].rolling(bb_period).std().fillna(0)
    df['BB_Upper'] = df['BB_Mid'] + 2 * df['BB_Std']
    df['BB_Lower'] = df['BB_Mid'] - 2 * df['BB_Std']

    # ATR (Average True Range - 14)
    high_low = df['High'] - df['Low']
    high_close = (df['High'] - df['Close'].shift()).abs()
    low_close = (df['Low'] - df['Close'].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df['ATR'] = tr.rolling(min(14, len(df))).mean().bfill()

    # ADX (Average Directional Index - 14)
    up_move = df['High'].diff()
    down_move = -df['Low'].diff()
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    tr_14 = tr.rolling(min(14, len(df))).sum().replace(0, 1e-10)
    plus_di = 100 * (pd.Series(plus_dm, index=df.index).rolling(min(14, len(df))).sum() / tr_14)
    minus_di = 100 * (pd.Series(minus_dm, index=df.index).rolling(min(14, len(df))).sum() / tr_14)
    dx = 100 * (plus_di - minus_di).abs() / np.where((plus_di + minus_di) == 0, 1e-10, (plus_di + minus_di))
    df['ADX'] = dx.rolling(min(14, len(df))).mean().fillna(20.0)

    # Stochastic RSI (14, 3, 3)
    rsi_min = df['RSI'].rolling(min(14, len(df))).min()
    rsi_max = df['RSI'].rolling(min(14, len(df))).max()
    stoch_rsi = (df['RSI'] - rsi_min) / np.where((rsi_max - rsi_min) == 0, 1e-10, (rsi_max - rsi_min))
    df['StochRSI_K'] = stoch_rsi.rolling(3).mean().fillna(0.5) * 100
    df['StochRSI_D'] = df['StochRSI_K'].rolling(3).mean().fillna(0.5)

    # Hacim Analizi
    vol_period = min(20, len(df))
    df['Vol_SMA20'] = df['Volume'].rolling(vol_period).mean().bfill()

    last = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else last

    # Gosterge Degerleri
    rsi_val = float(last['RSI']) if not np.isnan(last['RSI']) else 50.0
    macd_hist = float(last['MACD_Hist']) if not np.isnan(last['MACD_Hist']) else 0.0
    macd_hist_prev = float(prev['MACD_Hist']) if not np.isnan(prev['MACD_Hist']) else 0.0
    ema9_val = float(last['EMA9']) if not np.isnan(last['EMA9']) else current_price
    ema21_val = float(last['EMA21']) if not np.isnan(last['EMA21']) else current_price
    ema50_val = float(last['EMA50']) if not np.isnan(last['EMA50']) else current_price
    ema200_val = float(last['EMA200']) if not np.isnan(last['EMA200']) else current_price
    bb_upper = float(last['BB_Upper']) if not np.isnan(last['BB_Upper']) else current_price * 1.05
    bb_lower = float(last['BB_Lower']) if not np.isnan(last['BB_Lower']) else current_price * 0.95
    bb_mid = float(last['BB_Mid']) if not np.isnan(last['BB_Mid']) else current_price
    atr_val = float(last['ATR']) if not np.isnan(last['ATR']) else (current_price * 0.02)
    adx_val = float(last['ADX']) if not np.isnan(last['ADX']) else 20.0
    stoch_k = float(last['StochRSI_K']) if not np.isnan(last['StochRSI_K']) else 50.0
    vol_ratio = float(last['Volume'] / last['Vol_SMA20']) if (not np.isnan(last['Vol_SMA20']) and last['Vol_SMA20'] > 0) else 1.0

    # Puanlama (0 - 100)
    sub_score = 0.0
    bullish_signals = 0
    bearish_signals = 0

    # 1. Trend & Hareketli Ortalamalar (Max 35p)
    if current_price > ema9_val > ema21_val:
        sub_score += 20.0
        bullish_signals += 1
    elif current_price > ema21_val:
        sub_score += 10.0
    else:
        bearish_signals += 1

    if current_price > ema50_val:
        sub_score += 10.0
        bullish_signals += 1
    if current_price > ema200_val:
        sub_score += 5.0

    # 2. RSI (Max 25p)
    if 45 <= rsi_val <= 65:
        sub_score += 25.0  # Saglikli yukselis alani
        bullish_signals += 1
    elif 30 <= rsi_val < 45:
        sub_score += 15.0  # Toparlanma alani
    elif rsi_val < 30:
        sub_score += 10.0  # Asiri satim (tepki ihtimali)
    elif 65 < rsi_val <= 75:
        sub_score += 12.0  # Guclu ama dikkat
    else:
        sub_score += 0.0   # Asiri alim (>75)
        bearish_signals += 1

    # 3. MACD Momentum (Max 20p)
    if macd_hist > 0 and macd_hist >= macd_hist_prev:
        sub_score += 20.0  # Guclenen yukselis
        bullish_signals += 1
    elif macd_hist > 0:
        sub_score += 12.0
    elif macd_hist < 0 and macd_hist > macd_hist_prev:
        sub_score += 8.0   # Dusus zayifliyor
    else:
        bearish_signals += 1

    # 4. Hacim ve Volatilite (Max 20p)
    if vol_ratio >= 1.5:
        sub_score += 15.0
    elif vol_ratio >= 1.1:
        sub_score += 10.0
    else:
        sub_score += 5.0

    if adx_val >= 25:
        sub_score += 5.0   # Trend var

    sub_score = max(0.0, min(100.0, sub_score))

    # Trend Yönü Kararı
    if sub_score >= 62:
        trend = "BULLISH"
    elif sub_score <= 40:
        trend = "BEARISH"
    else:
        trend = "NEUTRAL"

    return {
        "valid": True,
        "tf": tf_name,
        "price": current_price,
        "change_pct": round(change_pct, 2),
        "score": round(sub_score, 1),
        "trend": trend,
        "rsi": round(rsi_val, 1),
        "macd_hist": round(macd_hist, 4),
        "macd_increasing": bool(macd_hist > macd_hist_prev),
        "ema9": round(ema9_val, 2),
        "ema21": round(ema21_val, 2),
        "ema50": round(ema50_val, 2),
        "ema200": round(ema200_val, 2),
        "bb_upper": round(bb_upper, 2),
        "bb_lower": round(bb_lower, 2),
        "bb_mid": round(bb_mid, 2),
        "atr": round(atr_val, 2),
        "atr_pct": round((atr_val / current_price * 100) if current_price > 0 else 0.0, 2),
        "adx": round(adx_val, 1),
        "stoch_k": round(stoch_k, 1),
        "vol_ratio": round(vol_ratio, 2),
        "bullish_signals": bullish_signals,
        "bearish_signals": bearish_signals
    }


def _fetch_single_tf(yahoo_ticker: str, tf_name: str) -> dict:
    """Belirli bir zaman dilimi icin senkron olarak veri ceker ve analiz eder."""
    try:
        stock = yf.Ticker(yahoo_ticker)
        
        if tf_name == "15m":
            df = stock.history(period="5d", interval="15m")
        elif tf_name == "1h":
            df = stock.history(period="1mo", interval="1h")
        elif tf_name == "4h":
            df_1h = stock.history(period="3mo", interval="1h")
            if df_1h is not None and not df_1h.empty:
                df = df_1h.resample('4h').agg({
                    'Open': 'first',
                    'High': 'max',
                    'Low': 'min',
                    'Close': 'last',
                    'Volume': 'sum'
                }).dropna()
            else:
                df = pd.DataFrame()
        elif tf_name == "1d":
            df = stock.history(period="6mo", interval="1d")
        else:
            df = pd.DataFrame()

        if df is None or df.empty:
            return {"valid": False, "tf": tf_name, "error": "Veri bos"}

        return _calc_indicators(df, tf_name)
    except Exception as e:
        logger.warning(f"TF veri cekme hatasi [{yahoo_ticker} - {tf_name}]: {e}")
        return {"valid": False, "tf": tf_name, "error": str(e)}


async def fetch_timeframe_analysis(ticker: str, tf_name: str) -> dict:
    """Tek bir timeframe icin asenkron onbellekli veri dondurur."""
    clean_ticker = ticker.upper().replace(".IS", "")
    cache_key = f"{clean_ticker}_{tf_name}"
    now = time.time()
    ttl = CACHE_TTL.get(tf_name, 300)

    if cache_key in MTF_CACHE:
        cached_data, cached_time = MTF_CACHE[cache_key]
        if now - cached_time < ttl:
            return cached_data

    yahoo_ticker = f"{clean_ticker}.IS"
    result = await asyncio.to_thread(_fetch_single_tf, yahoo_ticker, tf_name)
    
    if result.get("valid"):
        MTF_CACHE[cache_key] = (result, now)
        
    return result


async def fetch_all_mtf_data(ticker: str) -> dict:
    """
    Belirtilen BIST hissesi icin 4 zaman dilimini (15m, 1h, 4h, 1d) paralel olarak ceker.
    Kompozit MTF skorunu ve Confluence (uyum) analizini hesaplar.
    """
    clean_ticker = ticker.upper().replace(".IS", "")
    
    tasks = [
        fetch_timeframe_analysis(clean_ticker, "15m"),
        fetch_timeframe_analysis(clean_ticker, "1h"),
        fetch_timeframe_analysis(clean_ticker, "4h"),
        fetch_timeframe_analysis(clean_ticker, "1d")
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    tf_results = {}
    valid_count = 0
    timeframes = ["15m", "1h", "4h", "1d"]

    for idx, tf in enumerate(timeframes):
        res = results[idx]
        if isinstance(res, dict) and res.get("valid"):
            tf_results[tf] = res
            valid_count += 1
        else:
            tf_results[tf] = {
                "valid": False,
                "tf": tf,
                "score": 50.0,
                "trend": "NEUTRAL",
                "price": 0.0,
                "error": str(res) if isinstance(res, Exception) else "Bilinmeyen hata"
            }

    # Timeframe Agirliklari (15m: %15 | 1h: %30 | 4h: %35 | 1d: %20)
    weights = {
        "15m": 0.15,
        "1h": 0.30,
        "4h": 0.35,
        "1d": 0.20
    }

    mtf_score = 0.0
    bullish_tfs = []
    bearish_tfs = []
    neutral_tfs = []

    for tf, weight in weights.items():
        sub = tf_results.get(tf, {})
        s = sub.get("score", 50.0) if sub.get("valid") else 50.0
        mtf_score += s * weight

        trend = sub.get("trend", "NEUTRAL")
        if trend == "BULLISH":
            bullish_tfs.append(tf)
        elif trend == "BEARISH":
            bearish_tfs.append(tf)
        else:
            neutral_tfs.append(tf)

    mtf_score = round(max(0.0, min(100.0, mtf_score)), 1)
    confluence_count = len(bullish_tfs)

    # Confluence Gucu
    if confluence_count >= 3:
        confluence_status = "STRONG_BULLISH"
    elif confluence_count == 2:
        confluence_status = "MODERATE_BULLISH"
    elif len(bearish_tfs) >= 3:
        confluence_status = "STRONG_BEARISH"
    elif len(bearish_tfs) == 2:
        confluence_status = "MODERATE_BEARISH"
    else:
        confluence_status = "NEUTRAL"

    current_price = (
        tf_results.get("15m", {}).get("price") or
        tf_results.get("1h", {}).get("price") or
        tf_results.get("1d", {}).get("price") or
        0.0
    )

    atr_val = tf_results.get("1h", {}).get("atr") or tf_results.get("1d", {}).get("atr") or (current_price * 0.02)
    atr_pct = tf_results.get("1h", {}).get("atr_pct") or tf_results.get("1d", {}).get("atr_pct") or 2.0
    adx_val = tf_results.get("1h", {}).get("adx") or tf_results.get("4h", {}).get("adx") or 20.0

    return {
        "ticker": clean_ticker,
        "current_price": current_price,
        "mtf_score": mtf_score,
        "confluence_status": confluence_status,
        "confluence_count": confluence_count,
        "bullish_tfs": bullish_tfs,
        "bearish_tfs": bearish_tfs,
        "neutral_tfs": neutral_tfs,
        "atr": atr_val,
        "atr_pct": atr_pct,
        "adx": adx_val,
        "timeframes": tf_results,
        "timestamp": time.time()
    }


def clear_mtf_cache(ticker: str = None):
    """Onbellek temizleyici."""
    global MTF_CACHE
    if ticker:
        clean = ticker.upper().replace(".IS", "")
        for tf in ["15m", "1h", "4h", "1d"]:
            MTF_CACHE.pop(f"{clean}_{tf}", None)
    else:
        MTF_CACHE.clear()