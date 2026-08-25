"""
strategy_engine.py — Borsa Scalper Kisa Vadeli Kar Alma ve Pozisyon Motoru (v2)
---------------------------------------------------------------------------------
3 Farkli Kisa Vadeli Strateji:
1. Kademeli Cikis (Scaling Out - 'scaling'):
   - TP1: +%2.5 ~ %3.5 (Pozisyonun %40'i satilir, SL basabas seviyesine cekilir)
   - TP2: +%5.0 ~ %7.0 (Pozisyonun %40'i satilir, Trailing Stop baslar)
   - TP3: Trailing Stop (Zirveden -%2 geri cekilmede kalan %20 satilir)
   - SL: -%3.0

2. Swing Trade (1-3 Gun - 'swing'):
   - TP: +%4.5 ~ %8.0 (Direncli tek hedefli cikis)
   - SL: -%2.5 ~ %3.5 (4h destek seviyesi alti)
   - Vade: 3 is gunu

3. Momentum Yakalama (Gun Ici - 'momentum'):
   - TP: +%3.5 (Hizli cikis)
   - SL: -%1.5 (Siki stop)
   - Vade: Ayni gun 17:50 seans kapanisinda otomatik cikis (gece riski yok)

Risk Yonetimi Kurallari:
   - Maksimum 5 eszamanli pozisyon
   - Pozisyon basina maksimum %12 portfoy payi
"""

import math
import time
import datetime
import pytz
import logging

logger = logging.getLogger("BistScalpBot")

MAX_CONCURRENT_POSITIONS = 5
MAX_POSITION_PORTFOLIO_RATIO = 0.12  # %12

STRATEGY_DESCRIPTIONS = {
    "auto": "Akilli Otomatik (Piyasa dinamiklerine gore secilir)",
    "scaling": "Kademeli Kar Alma (%40 TP1 + %40 TP2 + %20 Trailing Stop)",
    "swing": "Swing Trade (1-3 Gun, Direnc Hedefli %5-8)",
    "momentum": "Momentum Scalp (Gun Ici %3.5 Hizli, 17:50 Kapanis)"
}


def calculate_session_expire_time(strategy: str) -> str:
    """Stratejiye gore pozisyon vade sonu tarih/saatini hesaplar (Europe/Istanbul)."""
    tz = pytz.timezone("Europe/Istanbul")
    now = datetime.datetime.now(tz)

    if strategy == "momentum":
        # Ayni gun seans sonu (17:50)
        expire_dt = now.replace(hour=17, minute=50, second=0, microsecond=0)
        if now >= expire_dt:
            # Eger seans sonrasinda olustuysa bir sonraki seans kapanisi
            expire_dt += datetime.timedelta(days=1)
    else:
        # Swing veya Scaling icin 3 is gunu sonra 17:50
        days_added = 0
        cur = now
        while days_added < 3:
            cur += datetime.timedelta(days=1)
            if cur.weekday() < 5:  # Pazartesi-Cuma
                days_added += 1
        expire_dt = cur.replace(hour=17, minute=50, second=0, microsecond=0)

    return expire_dt.strftime("%Y-%m-%d %H:%M:%S")


def select_best_strategy(mtf_data: dict, preferred_mode: str = "auto") -> dict:
    """
    Piyasa verilerini analiz ederek en uygun stratejiyi ve TP/SL seviyelerini belirler.
    """
    mode = preferred_mode.lower()
    if mode not in ["auto", "scaling", "swing", "momentum"]:
        mode = "auto"

    current_price = mtf_data.get("current_price", 0.0)
    if current_price <= 0:
        return {"strategy": "scaling", "name": STRATEGY_DESCRIPTIONS["scaling"], "valid": False}

    atr = mtf_data.get("atr", current_price * 0.02)
    atr_pct = mtf_data.get("atr_pct", 2.0)
    adx = mtf_data.get("adx", 20.0)
    confluence_count = mtf_data.get("confluence_count", 2)
    vol_15m = mtf_data.get("timeframes", {}).get("15m", {}).get("vol_ratio", 1.0)
    rsi_15m = mtf_data.get("timeframes", {}).get("15m", {}).get("rsi", 50.0)

    chosen_strategy = mode

    # Otomatik Strateji Secim Mantigi
    if mode == "auto":
        # 1. Yuksek Hacim + Guclu Trend -> Momentum
        if adx >= 25.0 and vol_15m >= 1.4 and rsi_15m >= 52.0 and confluence_count >= 3:
            chosen_strategy = "momentum"
        # 2. Orta-Yuksek Volatilite veya Coklu Onay -> Kademeli Cikis
        elif atr_pct >= 2.2 or confluence_count >= 3:
            chosen_strategy = "scaling"
        # 3. Diger haller -> Swing Trade
        else:
            chosen_strategy = "swing"

    # Seviye Hesaplamalari
    if chosen_strategy == "momentum":
        tp1_pct = 0.035
        tp1 = round(current_price * (1 + tp1_pct), 2)
        tp2 = None
        tp3 = None
        sl_pct = 0.015
        sl = round(current_price * (1 - sl_pct), 2)
        trailing_sl_pct = 0.01
        expected_hold = "Gun Ici (17:50 Seans Sonu)"
    elif chosen_strategy == "swing":
        tp_ratio = max(0.045, min(0.08, (2.2 * atr_pct / 100)))
        tp1 = round(current_price * (1 + tp_ratio), 2)
        tp2 = None
        tp3 = None
        sl_ratio = max(0.025, min(0.04, (1.3 * atr_pct / 100)))
        sl = round(current_price * (1 - sl_ratio), 2)
        trailing_sl_pct = 0.015
        expected_hold = "1 - 3 Is Gunu"
    else:  # scaling
        tp1_ratio = max(0.025, min(0.035, (1.2 * atr_pct / 100)))
        tp2_ratio = max(0.050, min(0.075, (2.4 * atr_pct / 100)))
        tp1 = round(current_price * (1 + tp1_ratio), 2)
        tp2 = round(current_price * (1 + tp2_ratio), 2)
        tp3 = round(current_price * (1 + tp2_ratio * 1.4), 2)
        sl_ratio = max(0.030, min(0.045, (1.5 * atr_pct / 100)))
        sl = round(current_price * (1 - sl_ratio), 2)
        trailing_sl_pct = 0.020
        expected_hold = "1 - 3 Is Gunu (Kademeli)"

    expire_time = calculate_session_expire_time(chosen_strategy)

    return {
        "valid": True,
        "strategy": chosen_strategy,
        "name": STRATEGY_DESCRIPTIONS.get(chosen_strategy, chosen_strategy),
        "entry_price": current_price,
        "tp1": tp1,
        "tp2": tp2,
        "tp3": tp3,
        "sl": sl,
        "trailing_sl_pct": trailing_sl_pct,
        "expire_time": expire_time,
        "expected_hold": expected_hold,
        "atr": round(atr, 2),
        "atr_pct": round(atr_pct, 2),
        "adx": round(adx, 1),
        "confluence_count": confluence_count
    }


def calculate_position_size(
    available_cash: float,
    total_portfolio_value: float,
    current_price: float,
    current_open_positions: int = 0,
    max_positions: int = MAX_CONCURRENT_POSITIONS,
    max_ratio: float = MAX_POSITION_PORTFOLIO_RATIO
) -> tuple[float, float, str]:
    """
    Risk ve portfoy sinirlarina gore islem miktarini (lot) hesaplar.
    Donus: (quantity_lot, total_cost_tl, rejection_reason_or_none)
    """
    if current_price <= 0:
        return 0.0, 0.0, "Gecersiz hisse fiyati"

    if current_open_positions >= max_positions:
        return 0.0, 0.0, f"Maksimum acik pozisyon limitine ulasildi ({current_open_positions}/{max_positions})"

    # Pozisyon basi portfoy limiti (%12)
    max_allocation = total_portfolio_value * max_ratio
    
    # Kullanilabilir nakit ile karsilastir
    allocatable_cash = min(available_cash, max_allocation)

    if allocatable_cash < current_price:
        return 0.0, 0.0, f"Yetersiz bakiye (Gereken min: {current_price:.2f} TL, Ayrilabilir: {allocatable_cash:.2f} TL)"

    # Lot sayisi (tam sayi)
    quantity = math.floor(allocatable_cash / current_price)
    if quantity < 1:
        return 0.0, 0.0, "Hesaplanan lot miktari sifir"

    total_cost = round(quantity * current_price, 2)
    return float(quantity), total_cost, None