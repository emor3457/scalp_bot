"""
auto_analyst.py — Kisa Vadeli Vizyon (v2)
------------------------------------------
BIST50 hisselerini cift zaman dilimli teknik analiz, temel analiz ve 
haber duyarliligi kullanarak tarar. Kompozit skor sistemiyle (0-100)
yalnizca yuksek kaliteli kisa vadeli (1-5 gun) firsatlarda sinyal uretir.

Karar Mantigi:
    Kompozit Skor = (Teknik x 0.50) + (Temel x 0.25) + (Haber x 0.25)
    Sinyal Esigi  = >= 65 (LONG), <= 30 pozisyon cikisi
    Kar Hedefleri = +5% (TP1), +10% (TP2), +15% (TP3)
    Stop-Loss     = -5%
"""

import time
import logging
import asyncio
import yfinance as yf
import pandas as pd
import numpy as np
import database
import trade_manager
import news_analyst

logger = logging.getLogger("BistScalpBot")

# BIST50 genisletilmis tarama listesi
BIST50_TICKERS = [
    "THYAO", "EREGL", "ASELS", "YKBNK", "AKBNK", "TUPRS", "KCHOL", "SAHOL", "GARAN", "ISCTR",
    "BIMAS", "SISE", "PGSUS", "EKGYO", "TCELL", "FROTO", "TOASO", "PETKM", "KOZAA", "KOZAL",
    "TAVHL", "ENKAI", "SASA", "HEKTS", "GUBRF", "DOAS", "ODAS", "KRDMD", "VESTL", "ARCLK",
    "ALARK", "ASTOR", "SMRTG", "ALFAS", "GESAN", "KMPUR", "ENJSA", "TTRAK", "YYLGD", "GWIND",
    "TKFEN", "MGROS", "CCOLA", "AEFES", "SOKM", "OTKAR", "KORDS", "BRISA", "SELEC", "ALBRK"
]

# TP/SL seviyeleri
TP1_PCT = 0.05   # +%5 — pozisyonun %40'i satilir
TP2_PCT = 0.10   # +%10 — pozisyonun %40'i satilir
TP3_PCT = 0.15   # +%15 — kalan %20 satilir
SL_PCT  = 0.05   # -%5  — tam pozisyon satilir

# Sinyal esikleri
BUY_THRESHOLD  = 65   # Kompozit skor >= 65 → AL
SELL_THRESHOLD = 30   # Kompozit skor <= 30 → SAT (tutuldugunda)

# Tarama araligi (saniye)
SCAN_INTERVAL_SECONDS = 900  # 15 dakika


# ---------------------------------------------------------------------------
# Teknik Analiz: Gunluk + Saatlik cift zaman dilimi
# ---------------------------------------------------------------------------

def calculate_technical_score(df_daily: pd.DataFrame, df_hourly: pd.DataFrame) -> tuple[float, dict]:
    """
    Gunluk ve saatlik grafik verilerinden teknik skor hesaplar (0-100).
    Donulen tuple: (skor, gostergeler_dict)
    """
    score = 0.0
    details = {}

    # --- GUNLUK VERI ANALIZI ---
    if df_daily is None or len(df_daily) < 50:
        return 0.0, {"error": "Gunluk veri yetersiz"}

    df_d = df_daily.copy()
    df_d['EMA9']  = df_d['Close'].ewm(span=9, adjust=False).mean()
    df_d['EMA21'] = df_d['Close'].ewm(span=21, adjust=False).mean()
    df_d['EMA50'] = df_d['Close'].ewm(span=50, adjust=False).mean()
    df_d['EMA200']= df_d['Close'].ewm(span=200, adjust=False).mean()

    # RSI (14)
    delta = df_d['Close'].diff()
    gain  = delta.where(delta > 0, 0.0)
    loss  = -delta.where(delta < 0, 0.0)
    avg_g = gain.ewm(alpha=1/14, adjust=False).mean()
    avg_l = loss.ewm(alpha=1/14, adjust=False).mean()
    rs    = avg_g / np.where(avg_l == 0, 1e-10, avg_l)
    df_d['RSI'] = 100 - (100 / (1 + rs))

    # MACD (12, 26, 9)
    ema12 = df_d['Close'].ewm(span=12, adjust=False).mean()
    ema26 = df_d['Close'].ewm(span=26, adjust=False).mean()
    df_d['MACD']       = ema12 - ema26
    df_d['MACD_Signal']= df_d['MACD'].ewm(span=9, adjust=False).mean()
    df_d['MACD_Hist']  = df_d['MACD'] - df_d['MACD_Signal']

    # Bollinger Bands (20, 2)
    df_d['BB_Mid'] = df_d['Close'].rolling(20).mean()
    df_d['BB_Std'] = df_d['Close'].rolling(20).std()
    df_d['BB_Upper'] = df_d['BB_Mid'] + 2 * df_d['BB_Std']
    df_d['BB_Lower'] = df_d['BB_Mid'] - 2 * df_d['BB_Std']
    df_d['BB_Width'] = (df_d['BB_Upper'] - df_d['BB_Lower']) / df_d['BB_Mid']

    # Hacim
    df_d['Vol_SMA20'] = df_d['Volume'].rolling(20).mean()

    curr  = df_d.iloc[-1]
    prev  = df_d.iloc[-2]
    prev2 = df_d.iloc[-3]

    close   = float(curr['Close'])
    ema9    = float(curr['EMA9'])
    ema21   = float(curr['EMA21'])
    ema50   = float(curr['EMA50'])
    ema200  = float(curr['EMA200']) if not pd.isna(curr['EMA200']) else close
    rsi     = float(curr['RSI'])
    macd    = float(curr['MACD'])
    macd_s  = float(curr['MACD_Signal'])
    macd_h  = float(curr['MACD_Hist'])
    prev_h  = float(prev['MACD_Hist'])
    prev2_h = float(prev2['MACD_Hist'])
    bb_up   = float(curr['BB_Upper'])
    bb_low  = float(curr['BB_Lower'])
    bb_mid  = float(curr['BB_Mid'])
    bb_wid  = float(curr['BB_Width'])
    vol     = float(curr['Volume'])
    vol_sma = float(curr['Vol_SMA20']) if curr['Vol_SMA20'] > 0 else 1.0
    vol_r   = vol / vol_sma

    # 52 haftalik dusuk hesapla
    low_52w = df_d['Close'].min() if len(df_d) >= 252 else df_d['Close'].min()
    high_52w= df_d['Close'].max() if len(df_d) >= 252 else df_d['Close'].max()
    dist_from_low  = (close - low_52w) / low_52w * 100
    dist_from_high = (high_52w - close) / high_52w * 100

    details.update({
        "close": close, "ema9": ema9, "ema21": ema21, "ema50": ema50,
        "rsi": rsi, "macd": macd, "macd_signal": macd_s, "macd_hist": macd_h,
        "bb_upper": bb_up, "bb_lower": bb_low, "bb_mid": bb_mid,
        "vol_ratio": vol_r, "dist_from_52w_low": dist_from_low,
        "dist_from_52w_high": dist_from_high,
    })

    # --- PUAN HESAPLAMA ---

    # 1. EMA Dizilimi: 30 puan max
    #    Guclu yukari trend: EMA9 > EMA21 > EMA50 ve fiyat EMA50 uzerinde
    if close > ema50 and ema9 > ema21:
        score += 30
    elif close > ema21 and ema9 > ema21:
        score += 20
    elif close > ema9:
        score += 10

    # 2. RSI Zonu: 20 puan max
    #    Ideal: RSI 40-60 (momentum var ama asirilık yok)
    #    Cok iyi: 30-40 arasinda (asilim dipten don)
    if 45 <= rsi <= 60:
        score += 20
    elif 35 <= rsi < 45 or 60 < rsi <= 65:
        score += 14
    elif 30 <= rsi < 35:
        score += 10  # Asilim dip bolgesinden geri donus firsati
    elif rsi > 70:
        score -= 5   # Asiri alim — cazip degil

    # 3. MACD Momentum: 20 puan max
    #    Histogram boluyor ve pozitif, momentum artiyor
    macd_growing = macd_h > prev_h > prev2_h
    macd_positive = macd_h > 0 and macd > macd_s
    if macd_growing and macd_positive:
        score += 20
    elif macd_growing:
        score += 12
    elif macd_positive:
        score += 8
    elif macd_h < prev_h:  # Momentum dusuyor
        score -= 5

    # 4. Bollinger Pozisyonu: 15 puan max
    #    Fiyat orta bant uzerinde ve bant genisliyorsa momentum var
    if close > bb_mid and bb_wid > 0.05:
        score += 15
    elif close > bb_mid:
        score += 8
    elif close <= bb_low * 1.01:
        score += 5   # Alt banda yakin — potansiyel destek
    elif close >= bb_up * 0.99:
        score -= 5   # Ust banda yakin — baskı bolgesinde

    # 5. Hacim Teyidi: 15 puan max
    if vol_r >= 2.0:
        score += 15
    elif vol_r >= 1.5:
        score += 10
    elif vol_r >= 1.2:
        score += 5
    elif vol_r < 0.7:
        score -= 5  # Cok dusuk hacim — guvenilmez hareket

    # --- SAATLIK TEYIT (+/- 10 bonus) ---
    if df_hourly is not None and len(df_hourly) >= 20:
        df_h = df_hourly.copy()
        df_h['EMA9'] = df_h['Close'].ewm(span=9, adjust=False).mean()
        df_h['EMA21']= df_h['Close'].ewm(span=21, adjust=False).mean()
        h_curr = df_h.iloc[-1]
        h_close = float(h_curr['Close'])
        h_ema9  = float(h_curr['EMA9'])
        h_ema21 = float(h_curr['EMA21'])
        if h_close > h_ema9 > h_ema21:
            score += 10   # Saatlik de yukari trend → guclu teyit
            details["hourly_trend"] = "yukari"
        elif h_close < h_ema9 < h_ema21:
            score -= 10   # Saatlik karsi trend → zayiflama
            details["hourly_trend"] = "asagi"
        else:
            details["hourly_trend"] = "yatay"

    final_score = max(0.0, min(100.0, float(score)))
    details["technical_score"] = final_score
    return final_score, details


def calculate_fundamental_score(ticker_info: dict, dist_from_52w_low: float) -> float:
    """
    Yahoo Finance temel analiz verilerinden bir 0-100 skoru hesaplar.
    """
    score = 50.0  # Baslangic notr skor

    try:
        pe  = ticker_info.get("trailingPE") or ticker_info.get("forwardPE")
        eps = ticker_info.get("trailingEps")
        roe = ticker_info.get("returnOnEquity")

        # F/K Oranı değerlendirmesi
        if pe is not None:
            if 5 < pe < 12:
                score += 20   # Ucuz
            elif 12 <= pe < 20:
                score += 10   # Makul
            elif pe > 30:
                score -= 10   # Pahali
            elif pe < 0:
                score -= 15   # Zarar ediyor

        # ROE (Ozsermaye Karliligi)
        if roe is not None:
            if roe > 0.25:
                score += 15   # Cok iyi (>%25)
            elif roe > 0.15:
                score += 8
            elif roe < 0:
                score -= 15   # Zarar ediyor

        # EPS Pozitiflik
        if eps is not None:
            if eps > 0:
                score += 10
            else:
                score -= 10

        # 52 haftalik dip yakinligi (alim firsati)
        if 0 <= dist_from_52w_low <= 15:
            score += 15   # Diplere yakin, potansiyel dip yapma
        elif dist_from_52w_low <= 30:
            score += 5

    except Exception as e:
        logger.debug(f"Temel analiz skoru hesaplanamadi: {str(e)}")

    return max(0.0, min(100.0, score))


# ---------------------------------------------------------------------------
# Ana Analiz Fonksiyonu
# ---------------------------------------------------------------------------

def _fetch_history(stock, period, interval):
    """Thread pool icinde calisacak senkron veri indirici."""
    return stock.history(period=period, interval=interval)


def _fetch_info(stock):
    """Thread pool icinde calisacak senkron info indirici."""
    try:
        return stock.info
    except Exception:
        return {}


async def analyze_ticker(ticker: str, semaphore: asyncio.Semaphore) -> dict:
    """
    Tek bir BIST hissesi icin:
      1. Gunluk + saatlik fiyat verisi indir
      2. Teknik skor hesapla (0-100)
      3. Temel analiz skoru hesapla (0-100)
      4. Haber duyarliligi skoru al (0-100)
      5. Kompozit skor hesapla ve sinyal uret
    """
    yahoo_ticker = f"{ticker}.IS"
    async with semaphore:
        try:
            logger.info(f"Analiz baslatiliyor -> {yahoo_ticker}")
            stock = yf.Ticker(yahoo_ticker)

            # Veri indir — thread pool ile (blocking IO)
            df_daily, df_hourly, info = await asyncio.gather(
                asyncio.to_thread(_fetch_history, stock, "6mo", "1d"),
                asyncio.to_thread(_fetch_history, stock, "1mo", "1h"),
                asyncio.to_thread(_fetch_info, stock),
            )

            # Haber skoru (ayri, non-blocking)
            news_score = await news_analyst.get_news_score(ticker)

            # Veri kontrolu
            if df_daily is None or df_daily.empty or len(df_daily) < 50:
                logger.warning(f"{ticker}: Yetersiz gunluk veri ({len(df_daily) if df_daily is not None else 0} satir)")
                return _hold_result(ticker, 0.0, "Yetersiz piyasa verisi.")

            # Skor hesapla
            tech_score, tech_details = calculate_technical_score(df_daily, df_hourly)
            fund_score = calculate_fundamental_score(info, tech_details.get("dist_from_52w_low", 50))

            # Kompozit Skor: Teknik %50, Temel %25, Haber %25
            composite = (tech_score * 0.50) + (fund_score * 0.25) + (news_score * 0.25)

            close  = tech_details.get("close", 0.0)
            rsi    = tech_details.get("rsi", 50.0)
            vol_r  = tech_details.get("vol_ratio", 1.0)
            macd_h = tech_details.get("macd_hist", 0.0)
            dist_low = tech_details.get("dist_from_52w_low", 50.0)

            logger.info(
                f"{ticker} | Teknik={tech_score:.1f} Temel={fund_score:.1f} "
                f"Haber={news_score:.1f} -> Kompozit={composite:.1f}"
            )

            # --- Portfoy durumu ---
            conn = await database.get_async_db_connection()
            try:
                async with conn.execute("SELECT quantity FROM portfolio WHERE ticker = 'TRY'") as cur:
                    row = await cur.fetchone()
                    cash = row["quantity"] if row else 0.0

                async with conn.execute("SELECT quantity, average_cost FROM portfolio WHERE ticker = ?", (ticker,)) as cur:
                    stock_row = await cur.fetchone()
                    held_qty  = stock_row["quantity"]   if stock_row else 0.0
                    avg_cost  = stock_row["average_cost"] if stock_row else 0.0
            finally:
                await conn.close()

            action   = "HOLD"
            quantity = 0.0
            reasoning = ""

            # --- SATIS KARARI: Tutulu pozisyon + zarar durdur veya zayif skor ---
            if held_qty > 0:
                current_return = (close - avg_cost) / avg_cost * 100 if avg_cost > 0 else 0.0

                # Stop-Loss tetiklendi
                if current_return <= -(SL_PCT * 100):
                    action   = "SAT"
                    quantity = held_qty
                    reasoning = (
                        f"[STOP-LOSS] #{ticker} stop-loss seviyesine ulasti! "
                        f"Giris fiyati: {avg_cost:.2f} TL, Mevcut: {close:.2f} TL, "
                        f"Kayip: %{current_return:.1f}. "
                        f"Zararı durdur kurali geregi {held_qty:.0f} lot tamamen satilmali."
                    )

                # TP1 — +5% kar al, pozisyonun %40'ini sat
                elif current_return >= TP1_PCT * 100 and current_return < TP2_PCT * 100:
                    sell_qty = int(held_qty * 0.4)
                    if sell_qty >= 1:
                        action   = "SAT"
                        quantity = float(sell_qty)
                        reasoning = (
                            f"[KAR AL - TP1] #{ticker} ilk kar hedefine ulasti (+%{current_return:.1f}). "
                            f"Pozisyonun %%40'i ({sell_qty:.0f} lot) satilarak kar realize ediliyor. "
                            f"Kalan pozisyon TP2 (+%%10) hedefine tasiniyor."
                        )

                # TP2 — +10% kar al, pozisyonun %40'ini sat
                elif current_return >= TP2_PCT * 100 and current_return < TP3_PCT * 100:
                    sell_qty = int(held_qty * 0.4)
                    if sell_qty >= 1:
                        action   = "SAT"
                        quantity = float(sell_qty)
                        reasoning = (
                            f"[KAR AL - TP2] #{ticker} ikinci kar hedefine ulasti (+%{current_return:.1f}). "
                            f"%%40 daha ({sell_qty:.0f} lot) satiliyor. "
                            f"Kalan pozisyon TP3 (+%%15) hedefine tasiniyor."
                        )

                # TP3 — +15% veya ustu, tamamen cik
                elif current_return >= TP3_PCT * 100:
                    action   = "SAT"
                    quantity = held_qty
                    reasoning = (
                        f"[KAR AL - TP3] #{ticker} tam kar hedefine ulasti (+%{current_return:.1f}). "
                        f"Tum pozisyon ({held_qty:.0f} lot) satilarak kar realize ediliyor. "
                        f"Mükemmel ticaret tamamlandi!"
                    )

                # Skor cok duste, cikis sinyali
                elif composite <= SELL_THRESHOLD and current_return > -2:
                    action   = "SAT"
                    quantity = held_qty
                    reasoning = (
                        f"[POZISYON KAPAT] #{ticker} analiz skoru kritik seviyeye dustu "
                        f"(Kompozit: {composite:.1f}/100). "
                        f"Mevcut getiri: %{current_return:.1f}. "
                        f"Tum pozisyon likide ediliyor."
                    )

            # --- ALIM KARARI: Yuksek skor + nakit yeterli ---
            elif composite >= BUY_THRESHOLD and held_qty == 0:
                # Negatif haber baskisi varsa sinyal bloke et
                if news_score < 30:
                    action    = "HOLD"
                    reasoning = (
                        f"{ticker}: Teknik skor yeterli ({composite:.1f}) ancak "
                        f"haber ortami negatif ({news_score:.1f}/100). "
                        f"Sinyal bloke edildi."
                    )
                else:
                    # Pozisyon buyuklugu: nakit x %15, maks 15.000 TL
                    target_amount = min(cash * 0.15, 15000.0)
                    if target_amount < 500.0:
                        target_amount = min(cash, 500.0)

                    quantity = float(int(target_amount / close)) if close > 0 else 0.0

                    if quantity >= 1.0:
                        action = "AL"
                        news_headlines = await news_analyst.get_news_headlines(ticker)
                        haber_ozet = " | ".join(news_headlines[:2]) if news_headlines else "Haberler yükleniyor..."
                        reasoning = (
                            f"[KISA VADELI FIRSAT] #{ticker} kuvvetli kompozit skor: {composite:.1f}/100 "
                            f"(Teknik: {tech_score:.1f}, Temel: {fund_score:.1f}, Haber: {news_score:.1f}). "
                            f"Fiyat: {close:.2f} TL | RSI: {rsi:.1f} | Hacim: {vol_r:.1f}x ortalama | "
                            f"MACD Hist: {macd_h:+.3f} | 52H Dipten Uzaklik: %{dist_low:.1f}. "
                            f"Haberler: {haber_ozet}. "
                            f"1-5 gunluk pozisyon. TP1:+%%5 TP2:+%%10 TP3:+%%15 SL:-%%5."
                        )
                    else:
                        reasoning = f"{ticker}: AL sinyali var ({composite:.1f}) ancak bakiye yetersiz."

            # HOLD durumu
            if action == "HOLD" and not reasoning:
                trend  = "Yukari" if tech_details.get("close", 0) > tech_details.get("ema50", 0) else "Asagi"
                reasoning = (
                    f"{ticker} | Kompozit: {composite:.1f}/100 | "
                    f"Teknik: {tech_score:.1f} | Temel: {fund_score:.1f} | Haber: {news_score:.1f} | "
                    f"Trend: {trend} | RSI: {rsi:.1f} | "
                    f"Sinyal esigine ({BUY_THRESHOLD}) ulasilamadi."
                )

            return {
                "ticker":    ticker,
                "action":    action,
                "price":     close,
                "quantity":  quantity,
                "reasoning": reasoning,
                "scores": {
                    "composite": round(composite, 1),
                    "technical": round(tech_score, 1),
                    "fundamental": round(fund_score, 1),
                    "news": round(news_score, 1),
                }
            }

        except Exception as e:
            logger.error(f"{ticker} analiz hatasi: {str(e)}")
            return _hold_result(ticker, 0.0, f"Hata: {str(e)}")


def _hold_result(ticker: str, price: float, reason: str) -> dict:
    """Hata veya eksik veri durumunda standart HOLD sonucu dondurur."""
    return {
        "ticker": ticker, "action": "HOLD",
        "price": price, "quantity": 0.0,
        "reasoning": reason,
        "scores": {"composite": 0, "technical": 0, "fundamental": 0, "news": 0}
    }


# ---------------------------------------------------------------------------
# Asenkron Tarama Dongusu
# ---------------------------------------------------------------------------

async def scan_all_and_report() -> dict:
    """
    BIST50 hisselerini asenkron olarak tarar (Semaphore=3 ile hiz sinirlamasi).
    AL/SAT sinyali olanlari trade_manager'a iletir.
    """
    logger.info("BIST50 kisa vadeli tarama baslatiliyor...")
    start_time = time.time()

    # Ayni anda max 3 istek (gunluk veri + fundamentals icin daha ihtiyatli)
    sem = asyncio.Semaphore(3)
    tasks = [analyze_ticker(ticker, sem) for ticker in BIST50_TICKERS]
    results = await asyncio.gather(*tasks)

    signals_sent = []
    for analysis in results:
        if analysis["action"] in ["AL", "SAT"] and analysis["quantity"] > 0:
            signals_sent.append(analysis)
            await inject_signal_to_bot(analysis)

    scan_duration = time.time() - start_time
    summary = {
        "timestamp":               time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
        "scan_duration_seconds":   round(scan_duration, 2),
        "total_scanned":           len(BIST50_TICKERS),
        "signals_generated_count": len(signals_sent),
        "signals":                 signals_sent,
        "details":                 results,
    }
    logger.info(
        f"Tarama tamamlandi. Taranan: {len(BIST50_TICKERS)} | "
        f"Sinyal: {len(signals_sent)} | Sure: {scan_duration:.1f} sn"
    )
    return summary


async def inject_signal_to_bot(analysis: dict):
    """AL/SAT sinyalini trade_manager uzerinden veritabanina iletir."""
    try:
        await trade_manager.process_trade_signal(
            ticker=analysis["ticker"],
            action=analysis["action"],
            price=analysis["price"],
            quantity=analysis["quantity"],
            reasoning=analysis["reasoning"],
        )
    except trade_manager.TradeExecutionError as e:
        logger.warning(f"Auto-Analyst islem iptal edildi [{analysis['ticker']}]: {str(e)}")
    except Exception as e:
        logger.error(f"Auto-Analyst sinyal iletiminde hata [{analysis['ticker']}]: {str(e)}")
