"""
bist_analysis.py — BIST derin analiz modulu.

bist-stock-analysis skill'inin (SKILL.md v1.0.0) veri katmani ve rapor ureticisi.
Hem dashboard `/api/deep-analysis` endpoint'i hem de skill'in `bist_data.py` CLI'i
bu modulu kullanir (tek kaynak, kopya yok).

    collect(ticker)      -> JSON benzeri veri (teknik/temel/haber/kompozit)
    build_markdown(t)    -> SKILL.md sablonuna uygun Turkce Markdown rapor

Veri kaynaklari: yfinance ({TICKER}.IS) + proje modulleri (auto_analyst,
news_analyst, market_data). KAP/isYatirim verisiyle dogrulanmasi onerilir;
yfinance BIST temel verisi kismi/kirli olabilir (degerleme bolumunde
mantiksiz degerler atlanir ve rapora not dusulur).
"""

import asyncio
import datetime
import logging

import yfinance as yf

import auto_analyst
import news_analyst
import market_data
import bist_fundamentals

logger = logging.getLogger("BistScalpBot")

# BIST sektor endeksleri -> hisse eslemesi (emsal karsilastirma icin)
SEKTOR_ENDEX = {
    "XBANK": ["AKBNK", "GARAN", "YKBNK", "ISCTR", "ALBRK", "TSKB", "VAKBN", "HALKB", "SKBNK"],
    "XUSIN": ["THYAO", "FROTO", "TOASO", "OTKAR", "TTRAK", "KCHOL", "SAHOL", "ARCLK",
              "VESTL", "EREGL", "KRDMD", "SISE", "CCOLA", "AEFES", "TUPRS"],
    "XULAS": ["THYAO", "PGSUS", "TAVHL", "CLEBI"],
    "XGMYO": ["EKGYO", "TRGYO", "ISGYO", "YKGYO"],
    "XTRZM": ["MAVI", "MGROS", "BIMAS", "SOKM", "BIZIM", "MPARK"],
    "XGIDA": ["CCOLA", "AEFES", "ULKER", "TUKAS", "ERSU", "PNSUT"],
    "XUTEK": ["ASELS", "ASTOR", "GESAN", "KMPUR", "SMRTG", "ALFAS", "GWIND", "SELEC"],
    "XKMYA": ["SASA", "HEKTS", "GUBRF", "PETKM", "AKSA", "ALKIM"],
    "XHOLD": ["KCHOL", "SAHOL", "ALARK", "YYLGD", "GSDHO"],
    "XTAST": ["BRISA", "KORDS", "GOZDE", "BOLUC"],
    "XILTM": ["TCELL", "TTKOM", "ASUZU"],
}


def _sector(ticker: str) -> str:
    for idx, members in SEKTOR_ENDEX.items():
        if ticker in members:
            return idx
    return "XUMAL"  # varsayilan: mali olmayan genel


def _clean_info(info: dict) -> dict:
    """JSON'a uygun temel veri alt kumesi (None/NaN temiz)."""
    keys = [
        "longName", "sector", "industry", "marketCap", "trailingPE", "forwardPE",
        "priceToBook", "returnOnEquity", "profitMargins", "operatingMargins",
        "grossMargins", "revenueGrowth", "earningsGrowth", "trailingEps",
        "forwardEps", "debtToEquity", "currentRatio", "freeCashflow",
        "dividendYield", "totalRevenue", "netIncome",
    ]
    out = {}
    for k in keys:
        v = info.get(k)
        if v is None:
            continue
        if isinstance(v, float) and (v != v):  # NaN
            continue
        out[k] = v
    return out


def _tr(v, nd: int = 2) -> str:
    """Turkce sayi bicimi: 1.234,56 (binlik ayrac . , ondalik ,)."""
    try:
        s = f"{float(v):,.{nd}f}"
        return s.replace(",", "§").replace(".", ",").replace("§", ".")
    except (TypeError, ValueError):
        return "veri yok"


async def collect(ticker: str) -> dict:
    """Tek hisse icin tum analiz verisini toplar (bist_data.py ile ayni)."""
    yahoo = f"{ticker}.IS"
    stock = yf.Ticker(yahoo)

    df_daily, df_hourly, info = await asyncio.gather(
        asyncio.to_thread(auto_analyst._fetch_history, stock, "6mo", "1d"),
        asyncio.to_thread(auto_analyst._fetch_history, stock, "1mo", "1h"),
        asyncio.to_thread(auto_analyst._fetch_info, stock),
    )

    # Gercek BIST temel oranlari (uzmanpara/Foreks) — hata durumunda {} (yfinance fallback)
    # Skor hesabindan ONCE alinir ki temel skor da gercek oranlari kullansin
    # (canli tarama ile ayni mantik, bkz. auto_analyst.analyze_ticker).
    bist_ratios = await asyncio.to_thread(bist_fundamentals.get_fundamentals, ticker)

    tech_score, tech_details = auto_analyst.calculate_technical_score(df_daily, df_hourly)
    fund_score = auto_analyst.calculate_fundamental_score(
        info, tech_details.get("dist_from_52w_low", 50.0), bist=bist_ratios
    )
    news_score = await news_analyst.get_news_score(ticker)
    headlines = await news_analyst.get_news_headlines(ticker)
    live_price = await market_data.get_stock_price(ticker)

    composite = (tech_score * 0.50) + (fund_score * 0.25) + (news_score * 0.25)
    if composite >= auto_analyst.BUY_THRESHOLD:
        hint = "AL (kompozit >= 65)"
    elif composite <= auto_analyst.SELL_THRESHOLD:
        hint = "SAT (kompozit <= 30)"
    else:
        hint = "HOLD (beklemede)"

    tech_keys = ["close", "rsi", "macd", "macd_signal", "macd_hist",
                 "ema9", "ema21", "ema50", "bb_upper", "bb_lower", "bb_mid",
                 "vol_ratio", "dist_from_52w_low", "dist_from_52w_high"]
    tech_out = {k: (round(float(tech_details[k]), 2) if k in tech_details and tech_details[k] is not None else None)
                for k in tech_keys}
    tech_out["ema200"] = tech_details.get("ema200")

    return {
        "meta": {
            "ticker": ticker,
            "yahoo_ticker": yahoo,
            "sector_index": _sector(ticker),
            "analysis_date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        },
        "prices": {
            "live_price_tl": round(live_price, 2) if live_price else None,
            "last_close_tl": round(float(tech_details.get("close", 0.0)), 2),
            "dist_from_52w_low_pct": tech_details.get("dist_from_52w_low"),
            "dist_from_52w_high_pct": tech_details.get("dist_from_52w_high"),
        },
        "technical": {"score_0_100": round(tech_score, 1), "indicators": tech_out},
        "fundamental": {
            "score_0_100": round(fund_score, 1),
            "info": _clean_info(info),
            "bist": bist_ratios or None,
        },
        "news": {"score_0_100": round(news_score, 1), "headlines": headlines[:5]},
        "composite": {
            "score_0_100": round(composite, 1),
            "weight": {"technical": 0.50, "fundamental": 0.25, "news": 0.25},
            "signal_hint": hint,
        },
    }


# ---------------------------------------------------------------------------
# Rapor uretici (SKILL.md sablonu)
# ---------------------------------------------------------------------------

def _pe(data: dict):
    """Guvenilir F/K: trailing ya da forward, sadece 0 < pe < 100 ise."""
    info = data["fundamental"]["info"]
    for k in ("trailingPE", "forwardPE"):
        v = info.get(k)
        if isinstance(v, (int, float)) and 0 < v < 100:
            return round(float(v), 1)
    return None


def _pb(data: dict):
    """Guvenilir PD/DD: yfinance BIST verisi kirli olabilir (ornek: THYAO 19.3)."""
    v = data["fundamental"]["info"].get("priceToBook")
    if isinstance(v, (int, float)) and 0 < v < 10:
        return round(float(v), 2)
    return None


def _assess(composite: float) -> tuple:
    if composite >= 65:
        return "Guclu", "AL esigini asiyor — firsat gorunumu"
    if composite >= 50:
        return "Notr-Guclu", "esigin altinda ama pozitif egilim"
    if composite >= 35:
        return "Notr", "sinyal esiginden uzak"
    return "Zayif", "zayif gorunum — bekleme"


async def build_markdown(ticker: str) -> str:
    """SKILL.md sablonuna uygun Turkce Markdown rapor dondurur."""
    ticker = ticker.upper().replace(".IS", "")
    data = await collect(ticker)

    meta = data["meta"]
    p = data["prices"]
    t = data["technical"]
    f = data["fundamental"]
    n = data["news"]
    c = data["composite"]
    info = f["info"]
    ind = t["indicators"]

    close = ind.get("close")
    rsi = ind.get("rsi")
    macd_h = ind.get("macd_hist")
    vol = ind.get("vol_ratio")
    ema9, ema21, ema50 = ind.get("ema9"), ind.get("ema21"), ind.get("ema50")
    bb_low, bb_up = ind.get("bb_lower"), ind.get("bb_upper")
    d_low, d_high = p.get("dist_from_52w_low_pct"), p.get("dist_from_52w_high_pct")

    low52 = close / (1 + d_low / 100) if (close and d_low is not None) else None
    high52 = close / (1 - d_high / 100) if (close and d_high is not None) else None

    deger, deger_yorum = _assess(c["score_0_100"])

    # Trend yorumu
    if close and ema9 and ema21 and ema50:
        if close > ema50 and ema9 > ema21:
            trend = "Yukari (fiyat EMA50 uzerinde, EMA9 > EMA21)"
        elif close > ema21 and ema9 > ema21:
            trend = "Yukari egilim (EMA9 > EMA21)"
        elif close < ema9 < ema21:
            trend = "Asagi (fiyat EMA9/EMA21 altinda)"
        else:
            trend = "Karisik / yatay"
    else:
        trend = "veri yok"

    risk = "Dusuk" if c["score_0_100"] >= 60 else ("Orta" if c["score_0_100"] >= 40 else "Yuksek")

    # Tercih: gercek BIST oranlari (uzmanpara/Foreks); yoksa yfinance fallback
    bist = f.get("bist") or {}

    pe = bist.get("fk") if bist else _pe(data)
    pb = bist.get("pd_dd") if bist else _pb(data)
    roe_bist = bist.get("roe")
    div_bist = bist.get("temettu_verimi_pct")

    roe = roe_bist if roe_bist is not None else info.get("returnOnEquity")
    rev_g = info.get("revenueGrowth")
    net_m = info.get("profitMargins")

    # yfinance normalize etme: dividendYield ve debtToEquity bazen yuzde bazen kesir gelir
    div_y = info.get("dividendYield")
    div_pct = (div_y if div_y is not None and div_y > 1 else (div_y * 100 if div_y is not None else None))
    if div_bist is not None:
        div_pct = div_bist  # uzmanpara yuzde olarak verir (1,56 = %1,56)

    d_e_raw = info.get("debtToEquity")
    if d_e_raw is not None:
        d_e_ratio = d_e_raw / 100 if d_e_raw > 5 else d_e_raw  # yfinance cogunlukla yuzde verir
    else:
        d_e_ratio = None

    m = []
    m.append(f"# BIST Analiz Raporu: {ticker}")
    m.append("")
    m.append(f"**Sirket**: {info.get('longName', ticker)} | **Sektor**: {meta['sector_index']} | "
             f"**Analiz Tarihi**: {meta['analysis_date']} | **Fiyat**: {_tr(close)} TL")
    m.append("")
    m.append("---")
    m.append("")
    m.append("## Ozet")
    m.append("")
    m.append(f"{info.get('longName', ticker)} icin kompozit skor **{_tr(c['score_0_100'])}/100** "
             f"({deger_yorum}). Teknik skor {_tr(t['score_0_100'])}/100, temel {_tr(f['score_0_100'])}/100, "
             f"haber {_tr(n['score_0_100'])}/100. Degerlendirme: **{deger}** | Risk: **{risk}**.")
    m.append("")
    m.append("---")
    m.append("")
    m.append("## Kompozit Skor")
    m.append("")
    m.append("| Bilesen | Agirlik | Skor |")
    m.append("|---|---|---|")
    m.append(f"| Teknik | %50 | {_tr(t['score_0_100'])} |")
    m.append(f"| Temel | %25 | {_tr(f['score_0_100'])} |")
    m.append(f"| Haber | %25 | {_tr(n['score_0_100'])} |")
    m.append(f"| **Kompozit** | | **{_tr(c['score_0_100'])}** — {c['signal_hint']} |")
    m.append("")
    m.append("---")
    m.append("")
    m.append("## Temel Analiz")
    m.append("")
    if bist:
        m.append(f"### Degerleme & Karlilik (uzmanpara/Foreks — bilanco donemi {bist.get('period') or 'bilinmiyor'})")
        m.append("")
        m.append("| Gosterge | Deger | Yorum |")
        m.append("|---|---|---|")
        m.append(f"| F/K | {_tr(pe)} | {('cok ucuz (<6)' if pe and pe < 6 else ('makul (6-12)' if pe and pe < 12 else ('pahali (>20)' if pe and pe > 20 else 'veri yok'))) if pe else 'veri yok'} |")
        m.append(f"| PD/DD | {_tr(pb)} | {('defter degerinin altinda (<1)' if pb and pb < 1 else ('makul (1-3)' if pb and pb < 3 else 'pahali (>3)')) if pb else 'veri yok'} |")
        m.append(f"| ROE (NetKar/Ozsermaye) | {_tr(roe * 100, 1) + '%' if roe is not None else 'veri yok'} | {('guclu (>%15)' if roe and roe > 0.15 else ('notr' if roe and roe > 0 else 'zayif')) if roe is not None else 'veri yok'} |")
        m.append(f"| Temettu Verimi | {_tr(div_pct, 2) + '%' if div_pct is not None else 'veri yok'} | {'cezbedici (>%3)' if div_pct and div_pct > 3 else ('dusuk' if div_pct is not None else 'veri yok')} |")
        m.append(f"| Piyasa Degeri | {_tr(bist.get('piyasa_degeri'), 0)} TL | halka aciklik %{_tr(bist.get('halka_aciklik_pct'), 1) if bist.get('halka_aciklik_pct') is not None else 'veri yok'} |")
        m.append(f"| Net Kar | {_tr(bist.get('net_kar'), 0)} TL | oz sermaye {_tr(bist.get('oz_sermaye'), 0)} TL |")
        m.append("")
        m.append("### Buyume & Bilanco (yfinance)")
        m.append("")
        m.append("| Gosterge | Deger | Yorum |")
        m.append("|---|---|---|")
        m.append(f"| Net Marj | {_tr(net_m * 100, 1) + '%' if net_m is not None else 'veri yok'} | {'saglikli' if net_m and net_m > 0.10 else ('zayif' if net_m is not None else 'veri yok')} |")
        m.append(f"| Nominal Buyume | {_tr(rev_g * 100, 1) + '%' if rev_g is not None else 'veri yok'} | yuksek enflasyonda reel buyume = nominal - enflasyon |")
        m.append(f"| Borc/Ozsermaye | {_tr(d_e_ratio * 100, 1) + '%' if d_e_ratio is not None else 'veri yok'} | {'yuksek (>%150)' if d_e_ratio and d_e_ratio > 1.5 else ('dikkat' if d_e_ratio and d_e_ratio > 1 else ('makul' if d_e_ratio is not None else 'veri yok'))} |")
    else:
        m.append("### Finansal Gorunum (yfinance; uzmanpara verisi alinamadi)")
        m.append("")
        m.append("| Gosterge | Deger | Yorum |")
        m.append("|---|---|---|")
        m.append(f"| F/K | {_tr(pe) if pe else 'veri yok'} | {('cok ucuz' if pe and pe < 6 else ('makul' if pe and pe < 12 else ('pahali' if pe and pe > 20 else 'veri yok'))) if pe else 'KAP verisi onerilir'} |")
        m.append(f"| PD/DD | {_tr(pb) if pb else 'veri yok'} | {('defter degerinin altinda' if pb and pb < 1 else ('makul' if pb and pb < 3 else 'veri yok')) if pb else 'KAP verisi onerilir'} |")
        m.append(f"| ROE | {_tr(roe * 100, 1) + '%' if roe is not None else 'veri yok'} | {('guclu (>%15)' if roe and roe > 0.15 else ('notr' if roe and roe > 0 else 'zayif')) if roe is not None else 'veri yok'} |")
        m.append(f"| Net Marj | {_tr(net_m * 100, 1) + '%' if net_m is not None else 'veri yok'} | {'saglikli' if net_m and net_m > 0.10 else ('zayif' if net_m is not None else 'veri yok')} |")
        m.append(f"| Nominal Buyume | {_tr(rev_g * 100, 1) + '%' if rev_g is not None else 'veri yok'} | yuksek enflasyonda reel buyume = nominal - enflasyon |")
        m.append(f"| Borc/Ozsermaye | {_tr(d_e_ratio * 100, 1) + '%' if d_e_ratio is not None else 'veri yok'} | {'yuksek (>%150)' if d_e_ratio and d_e_ratio > 1.5 else ('dikkat' if d_e_ratio and d_e_ratio > 1 else ('makul' if d_e_ratio is not None else 'veri yok'))} |")
        m.append(f"| Temettu Verimi | {_tr(div_pct, 2) + '%' if div_pct is not None else 'veri yok'} | {'cezbedici (>%3)' if div_pct and div_pct > 3 else ('dusuk' if div_pct is not None else 'veri yok')} |")
        m.append("")
        m.append("> Not: Gercek BIST temel verisi alinamadi. Derin degerleme icin KAP mali tablolari "
                 "veya uzmanpara/isYatirim 'Temel Degerler' sayfasi kullanilmalidir.")
    m.append("")
    m.append("---")
    m.append("")
    m.append("## Teknik Analiz (auto_analyst)")
    m.append("")
    m.append("### Fiyat Trendi")
    m.append("")
    m.append("| Gosterge | Deger | Yorum |")
    m.append("|---|---|---|")
    m.append(f"| Fiyat / EMA9 / EMA21 / EMA50 | {_tr(close)} / {_tr(ema9)} / {_tr(ema21)} / {_tr(ema50)} | {trend} |")
    m.append(f"| RSI (14) | {_tr(rsi)} | {'asiri satim (<30)' if rsi and rsi < 30 else ('notr-zayif' if rsi and rsi < 45 else ('notr' if rsi and rsi <= 60 else 'asiri alim (>70)'))} |")
    m.append(f"| MACD Hist | {_tr(macd_h)} | {'pozitif momentum' if macd_h and macd_h > 0 else 'negatif momentum'} |")
    m.append(f"| Hacim | {_tr(vol)}x ortalama | {'teyitli' if vol and vol >= 1.2 else ('normal' if vol and vol >= 0.7 else 'teyitsiz / dusuk')} |")
    m.append("")
    m.append("### Onemli Seviyeler")
    m.append("")
    m.append(f"- Destek: {_tr(bb_low)} TL (Bollinger alt bant), {_tr(low52)} TL (52 haftalik dip)")
    m.append(f"- Direnc: {_tr(bb_up)} TL (Bollinger ust bant), {_tr(high52)} TL (52 haftalik tepe)")
    m.append(f"- 52 Haftalik Aralik: {_tr(low52)} - {_tr(high52)} TL (dip mesafesi +%{_tr(d_low, 1)}, tepe mesafesi %{_tr(d_high, 1)})")
    m.append("")
    m.append("---")
    m.append("")
    m.append("## Haber Gorunumu")
    m.append("")
    m.append(f"**Skor: {_tr(n['score_0_100'])}/100**" + (" (negatif <30 — sinyal bloklayici)" if n["score_0_100"] < 30 else ""))
    m.append("")
    for h in n["headlines"] or ["Haber bulunamadi"]:
        m.append(f"- {h}")
    m.append("")
    m.append("---")
    m.append("")
    m.append("## Risk Faktorleri")
    m.append("")
    m.append(f"1. Teknik gorunum {trend.lower()} — trend yon degisikligi onaylanmadan erken pozisyon riski.")
    m.append(f"2. Makro: Turkkiye'de enflasyon, faiz (TCMB) ve kur (USD/TRY) oynakligi degerleme varsayimlarini hizla degistirebilir.")
    m.append(f"3. yfinance temel verisinin kirli/eksik olmasi (KAP ile dogrulama gerektirir).")
    m.append(f"4. Haber skoru yalnizca RSS kaynaklarina dayanir; ozel durum ve KAP bildirimleri kapsanmaz.")
    m.append("")
    m.append("---")
    m.append("")
    m.append("## Yatirim Tezi")
    m.append("")
    if c["score_0_100"] >= 50:
        m.append("### Yapici (Bull)")
        m.append("")
        m.append(f"Kompozit skor {_tr(c['score_0_100'])}/100 ile pozitif tarafta; haber ortami olumlu "
                 f"({_tr(n['score_0_100'])}/100). Degerleme makul ise trend donusuyle birlikte firsat olusabilir.")
        m.append("")
        m.append("### Yikici (Bear)")
        m.append("")
        m.append(f"Teknik skor {_tr(t['score_0_100'])}/100 zayif; trend donusu onaylanmadan alim riskli. "
                 "Makro belirsizlik kari baskılayabilir.")
    else:
        m.append("### Yapici (Bull)")
        m.append("")
        m.append(f"Dusuk degerleme varsa (F/K, PD/DD) ve haber ortami iyilesirse ({_tr(n['score_0_100'])}/100) "
                 "toparlanma potansiyeli olabilir; ancak once teknik sinyal beklenmeli.")
        m.append("")
        m.append("### Yikici (Bear)")
        m.append("")
        m.append(f"Kompozit {_tr(c['score_0_100'])}/100 esigin altinda ve teknik skor {_tr(t['score_0_100'])}/100. "
                 "Mevcut gorunumde sinyal yok; deger tuzagi riskine karsi KAP finansallariyla dogrulama sart.")
    m.append("")
    m.append("---")
    m.append("")
    m.append("**Uyari**: Bu analiz yalnizca bilgilendirme amaclidir, yatirim tavsiyesi degildir. "
             "Veriler gecikmeli olabilir; gecmis performans gelecekteki sonuclari garanti etmez.")

    return "\n".join(m)


if __name__ == "__main__":
    import sys
    t = sys.argv[1] if len(sys.argv) > 1 else "THYAO"
    print(asyncio.run(build_markdown(t)))
