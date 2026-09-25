"""
bist_screener.py — Tüm Borsa İstanbul (~650 hisse) Hızlı Makro Tarama Modülü
---------------------------------------------------------------------------
2 Aşamalı Hibrit Huni (Two-Stage Funnel) 1. Aşaması:
1. Tüm BIST evrenini TradingView Türkiye tarama motoru üzerinden sorgular (~100-200ms).
2. Likidite ve Güvenlik Filtresi: Günlük işlem hacmi < 20M TL olan sığ, tahtası kilitlenebilir,
   manipülasyona açık hisseleri eler.
3. Çoklu Strateji Aday Havuzu:
   - Dip Avcısı Adayları: RSI <= 32 veya Stoch.RSI aşırı satım bölgesinde olanlar.
   - Momentum / Hacim Kırılımı Adayları: Hacim artış oranı > 1.3x ve pozitif momentum.
   - Güçlü Trend Adayları: Fiyat > EMA20 > EMA50 veya MACD pozitif kesişim.
4. Harici servis yanıt vermezse otomatik olarak yerel BIST50 listesine döner (Fallback).
"""

import json
import logging
import time
import urllib.request
import urllib.error

logger = logging.getLogger("BistScalpBot")

SCANNER_URL = "https://scanner.tradingview.com/turkey/scan"
MIN_DAILY_VOLUME_TRY = 20_000_000.0  # Minimum 20 Milyon TL günlük işlem hacmi
SCANNER_TIMEOUT_SECONDS = 10

# Fallback için BIST50 listesi
FALLBACK_TICKERS = [
    "THYAO", "EREGL", "ASELS", "YKBNK", "AKBNK", "TUPRS", "KCHOL", "SAHOL", "GARAN", "ISCTR",
    "BIMAS", "SISE", "PGSUS", "EKGYO", "TCELL", "FROTO", "TOASO", "PETKM", "KOZAA", "KOZAL",
    "TAVHL", "ENKAI", "SASA", "HEKTS", "GUBRF", "DOAS", "ODAS", "KRDMD", "VESTL", "ARCLK",
    "ALARK", "ASTOR", "SMRTG", "ALFAS", "GESAN", "KMPUR", "ENJSA", "TTRAK", "YYLGD", "GWIND",
    "TKFEN", "MGROS", "CCOLA", "AEFES", "SOKM", "OTKAR", "KORDS", "BRISA", "SELEC", "ALBRK"
]


def fetch_raw_bist_universe() -> dict:
    """
    TradingView Türkiye Scanner API'sinden tüm hisseleri ve temel teknik metrikleri çeker.
    Dönen sözlük: {"total_count": int, "rows": list}
    """
    payload = {
        "filter": [
            {"left": "volume", "operation": "nempty"},
            {"left": "close", "operation": "nempty"}
        ],
        "options": {"lang": "tr"},
        "symbols": {"query": {"types": []}, "tickers": []},
        "columns": [
            "name",
            "close",
            "change",
            "volume",
            "Value.Traded",        # İşlem hacmi (TL)
            "RSI",                 # RSI (14)
            "MACD.macd",
            "MACD.signal",
            "Stoch.RSI.K",
            "EMA20",
            "EMA50",
            "average_volume_10d_calc"
        ],
        "sort": {"sortBy": "Value.Traded", "sortOrder": "desc"},
        "range": [0, 800]
    }

    req = urllib.request.Request(
        SCANNER_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Content-Type": "application/json"
        }
    )

    try:
        with urllib.request.urlopen(req, timeout=SCANNER_TIMEOUT_SECONDS) as response:
            data = json.loads(response.read().decode("utf-8"))
            total_count = data.get("totalCount", 0)
            rows = data.get("data", [])
            return {"total_count": total_count, "rows": rows}
    except Exception as e:
        logger.warning(f"TradingView Scanner API bağlantı hatası: {e}")
        return {"total_count": 0, "rows": []}


def parse_and_filter_candidates(
    raw_data: dict,
    min_volume_try: float = MIN_DAILY_VOLUME_TRY,
    target_candidate_count: int = 20
) -> dict:
    """
    Ham TradingView verisini ayrıştırır, likidite filtresini uygular ve
    çoklu strateji adaylarını skorlayarak en iyi adayları seçer.
    """
    rows = raw_data.get("rows", [])
    total_scanned = raw_data.get("total_count", len(rows))

    if not rows:
        logger.warning("Tarayıcıdan hisse verisi gelmedi. Fallback listesi devreye alınıyor.")
        return {
            "source": "fallback_bist50",
            "total_scanned": len(FALLBACK_TICKERS),
            "liquid_count": len(FALLBACK_TICKERS),
            "candidates": [{"ticker": t, "initial_tag": "BIST50_DEFAULT"} for t in FALLBACK_TICKERS[:target_candidate_count]]
        }

    liquid_stocks = []
    
    # 1. Likidite ve Veri Bütünlüğü Filtresi
    for item in rows:
        d = item.get("d", [])
        if len(d) < 12:
            continue

        ticker = d[0]
        close = d[1] or 0.0
        change_pct = d[2] or 0.0
        volume = d[3] or 0.0
        value_traded = d[4] or 0.0
        rsi = d[5] if d[5] is not None else 50.0
        macd = d[6] or 0.0
        macd_signal = d[7] or 0.0
        stoch_k = d[8] if d[8] is not None else 50.0
        ema20 = d[9] or 0.0
        ema50 = d[10] or 0.0
        avg_vol_10d = d[11] or 1.0

        # Varantları, hakları, geçersiz sembolleri ve sığ tahtaları filtrele
        if not ticker or "." in ticker or len(ticker) > 6:
            continue
        if close <= 0.1 or value_traded < min_volume_try:
            continue

        vol_ratio = (volume / avg_vol_10d) if avg_vol_10d > 0 else 1.0

        stock_info = {
            "ticker": ticker,
            "close": round(close, 2),
            "change_pct": round(change_pct, 2),
            "value_traded": round(value_traded, 0),
            "volume": int(volume),
            "rsi": round(rsi, 1),
            "macd": round(macd, 3),
            "macd_signal": round(macd_signal, 3),
            "stoch_k": round(stoch_k, 1),
            "vol_ratio": round(vol_ratio, 2),
            "ema20": round(ema20, 2),
            "ema50": round(ema50, 2),
            "is_dip_candidate": False,
            "is_momentum_candidate": False,
            "is_trend_candidate": False,
            "candidate_score": 0.0,
            "reason": []
        }

        # 2. Aday Kategori Tespiti
        # A) Dip Avcısı Adayı (RSI <= 32 veya Stoch RSI < 20)
        if rsi <= 32.0 or (rsi <= 38.0 and stoch_k < 20.0):
            stock_info["is_dip_candidate"] = True
            stock_info["candidate_score"] += (40.0 - min(40.0, rsi)) * 2.0  # RSI düştükçe puan artar
            stock_info["reason"].append(f"Aşırı Satım (RSI: {stock_info['rsi']})")

        # B) Momentum / Hacim Patlaması Adayı (Hacim > 1.3x ve pozitif gün)
        if vol_ratio >= 1.3 and change_pct > 0.5:
            stock_info["is_momentum_candidate"] = True
            stock_info["candidate_score"] += min(35.0, vol_ratio * 10.0)
            stock_info["reason"].append(f"Hacim Patlaması ({vol_ratio:.1f}x)")

        # C) Trend ve Kırılım Adayı (Fiyat > EMA20 > EMA50 veya MACD pozitif kesişim)
        if close > ema20 >= ema50 and ema20 > 0:
            stock_info["is_trend_candidate"] = True
            stock_info["candidate_score"] += 15.0
            stock_info["reason"].append("EMA Kırılımı")
        if macd > macd_signal and macd_signal != 0:
            stock_info["candidate_score"] += 10.0
            stock_info["reason"].append("MACD Alım")

        liquid_stocks.append(stock_info)

    liquid_count = len(liquid_stocks)

    # 3. Dengeli Havuz Seçimi (Hem Dip Avcısı hem Momentum hem Trend adaylarını al)
    # Adayları puanlarına göre sırala
    liquid_stocks.sort(key=lambda x: x["candidate_score"], reverse=True)

    # Öncelikle belirgin aday olanları öne al
    dip_candidates = [s for s in liquid_stocks if s["is_dip_candidate"]]
    momentum_candidates = [s for s in liquid_stocks if s["is_momentum_candidate"]]
    trend_candidates = [s for s in liquid_stocks if s["is_trend_candidate"] and not s["is_momentum_candidate"] and not s["is_dip_candidate"]]

    selected_tickers = set()
    final_candidates = []

    # Dip Avcısı kontenjanı (en az 5 aday veya mevcutlar)
    for s in dip_candidates[:8]:
        if s["ticker"] not in selected_tickers:
            selected_tickers.add(s["ticker"])
            final_candidates.append(s)

    # Momentum kontenjanı
    for s in momentum_candidates[:8]:
        if s["ticker"] not in selected_tickers:
            selected_tickers.add(s["ticker"])
            final_candidates.append(s)

    # Kalan kontenjanı en yüksek puanlılarla tamamla
    for s in liquid_stocks:
        if len(final_candidates) >= target_candidate_count:
            break
        if s["ticker"] not in selected_tickers:
            selected_tickers.add(s["ticker"])
            final_candidates.append(s)

    # Eğer likit hisselerden yeterli aday çıkmadıysa BIST50'den tamamla
    if len(final_candidates) < 10:
        for t in FALLBACK_TICKERS:
            if len(final_candidates) >= target_candidate_count:
                break
            if t not in selected_tickers:
                selected_tickers.add(t)
                final_candidates.append({"ticker": t, "initial_tag": "BIST50_FILL"})

    return {
        "source": "tradingview_scanner",
        "total_scanned": total_scanned,
        "liquid_count": liquid_count,
        "dip_candidates_count": len(dip_candidates),
        "momentum_candidates_count": len(momentum_candidates),
        "candidates": final_candidates[:target_candidate_count]
    }


def get_screened_candidates(
    min_volume_try: float = MIN_DAILY_VOLUME_TRY,
    target_candidate_count: int = 20
) -> dict:
    """
    Dışarıdan çağrılan ana tarama fonksiyonu.
    Tüm BIST'i tarar, likidite filtresini uygular ve en potansiyelli adayları döner.
    """
    logger.info(f"Tüm Borsa (~650 hisse) taranıyor (Min Hacim: {min_volume_try/1_000_000:.0f}M TL)...")
    start_time = time.time()
    
    raw = fetch_raw_bist_universe()
    result = parse_and_filter_candidates(
        raw_data=raw,
        min_volume_try=min_volume_try,
        target_candidate_count=target_candidate_count
    )
    
    duration = time.time() - start_time
    logger.info(
        f"Tarama tamamlandı ({duration:.2f}s). Toplam: {result.get('total_scanned')}, "
        f"Likit: {result.get('liquid_count')}, Seçilen Aday: {len(result.get('candidates', []))}"
    )
    return result


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    res = get_screened_candidates()
    print(f"Kaynak: {res['source']}")
    print(f"Toplam Taranan: {res['total_scanned']}, Likit: {res['liquid_count']}")
    print(f"Dip Adayları: {res.get('dip_candidates_count', 0)}, Momentum: {res.get('momentum_candidates_count', 0)}")
    print("\nSeçilen Adaylar:")
    for c in res["candidates"]:
        print(f" - {c.get('ticker')}: {c.get('close', 0)} TL | Hacim: {c.get('value_traded', 0)/1e6:.1f}M TL | RSI: {c.get('rsi')} | Neden: {', '.join(c.get('reason', []))}")
