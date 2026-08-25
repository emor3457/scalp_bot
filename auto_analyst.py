"""
auto_analyst.py — Multi-Timeframe BIST Otomatik Analiz ve Sinyal Motoru (v2)
----------------------------------------------------------------------------
4 Zaman Dilimi (15m, 1h, 4h, 1d) + Temel Analiz + Haber Analizi
3 Kisa Vadeli Strateji (Kademeli, Swing, Momentum) Entegrasyonu
"""

import time
import logging
import asyncio
import os
import database
import trade_manager
import news_analyst
import market_data
import bist_fundamentals
import mtf_data
import strategy_engine

logger = logging.getLogger("BistScalpBot")

# BIST50 Tarama Listesi
BIST50_TICKERS = [
    "THYAO", "EREGL", "ASELS", "YKBNK", "AKBNK", "TUPRS", "KCHOL", "SAHOL", "GARAN", "ISCTR",
    "BIMAS", "SISE", "PGSUS", "EKGYO", "TCELL", "FROTO", "TOASO", "PETKM", "KOZAA", "KOZAL",
    "TAVHL", "ENKAI", "SASA", "HEKTS", "GUBRF", "DOAS", "ODAS", "KRDMD", "VESTL", "ARCLK",
    "ALARK", "ASTOR", "SMRTG", "ALFAS", "GESAN", "KMPUR", "ENJSA", "TTRAK", "YYLGD", "GWIND",
    "TKFEN", "MGROS", "CCOLA", "AEFES", "SOKM", "OTKAR", "KORDS", "BRISA", "SELEC", "ALBRK"
]

BUY_THRESHOLD = 65.0    # Kompozit skor >= 65 -> AL
SCAN_INTERVAL_SECONDS = 900  # 15 dakika


def calculate_fundamental_score(ticker: str) -> tuple[float, dict]:
    """BIST sirketleri icin uzmanpara/yfinance temel skorunu hesaplar (0-100)."""
    clean_ticker = ticker.upper().replace(".IS", "")
    data = bist_fundamentals.get_fundamentals(clean_ticker)
    
    score = 50.0  # Notr baslangic
    details = {"source": "none"}

    if data and len(data) > 1:
        details["source"] = "uzmanpara"
        score = 0.0

        fk = data.get("fk")
        if fk is not None and fk > 0:
            details["fk"] = fk
            if fk < 5:
                score += 30.0
            elif fk < 8:
                score += 25.0
            elif fk < 12:
                score += 15.0
            elif fk < 20:
                score += 5.0
        else:
            score += 10.0

        pd_dd = data.get("pd_dd")
        if pd_dd is not None and pd_dd > 0:
            details["pd_dd"] = pd_dd
            if pd_dd < 1.0:
                score += 30.0
            elif pd_dd < 2.0:
                score += 20.0
            elif pd_dd < 4.0:
                score += 10.0
        else:
            score += 10.0

        roe = data.get("roe")
        if roe is not None:
            details["roe"] = roe
            if roe > 0.35:
                score += 25.0
            elif roe > 0.20:
                score += 18.0
            elif roe > 0.10:
                score += 10.0
        else:
            score += 10.0

        temettu = data.get("temettu_verimi_pct")
        if temettu is not None and temettu > 0:
            details["temettu_verimi_pct"] = temettu
            if temettu > 5.0:
                score += 15.0
            elif temettu > 2.0:
                score += 10.0
        else:
            score += 5.0

        score = max(0.0, min(100.0, score))
        return round(score, 1), details

    return 50.0, {"source": "neutral_fallback"}


async def analyze_single_ticker(ticker: str) -> dict:
    """Tek bir BIST hissesi icin 4 timeframe MTF + Temel + Haber analizi yapar."""
    clean_ticker = ticker.upper().replace(".IS", "")

    # 1. Multi-Timeframe Teknik Analiz
    mtf_res = await mtf_data.fetch_all_mtf_data(clean_ticker)
    mtf_score = mtf_res.get("mtf_score", 50.0)

    # 2. Temel Analiz
    fund_score, fund_details = calculate_fundamental_score(clean_ticker)

    # 3. Haber Duyarlilik Analizi
    try:
        news_score = await news_analyst.get_news_score(clean_ticker)
    except Exception:
        news_score = 50.0

    # 4. Kompozit Skor (Teknik %50, Temel %25, Haber %25)
    composite_score = round((mtf_score * 0.50) + (fund_score * 0.25) + (news_score * 0.25), 1)

    # 5. Strateji Onerisi
    strategy_mode = await database.get_setting("strategy_mode", "auto")
    strategy_plan = strategy_engine.select_best_strategy(mtf_res, preferred_mode=strategy_mode)

    confluence_count = mtf_res.get("confluence_count", 0)
    current_price = mtf_res.get("current_price", 0.0)

    # Sinyal Karari
    signal = "NOTR"
    if composite_score >= BUY_THRESHOLD and confluence_count >= 2:
        signal = "AL"
    elif composite_score <= 35.0:
        signal = "SAT"

    return {
        "ticker": clean_ticker,
        "current_price": current_price,
        "composite_score": composite_score,
        "technical_score": mtf_score,
        "fundamental_score": fund_score,
        "news_score": news_score,
        "signal": signal,
        "confluence_status": mtf_res.get("confluence_status", "NEUTRAL"),
        "confluence_count": confluence_count,
        "bullish_tfs": mtf_res.get("bullish_tfs", []),
        "bearish_tfs": mtf_res.get("bearish_tfs", []),
        "strategy_plan": strategy_plan,
        "mtf_details": mtf_res.get("timeframes", {}),
        "fundamental_details": fund_details
    }


async def scan_all_and_report(report_only: bool = None) -> dict:
    """
    BIST50 listesini tarar, acik pozisyonlari kontrol eder ve gerekiyorsa yeni pozisyon acar.
    """
    if report_only is None:
        scan_mode_env = os.getenv("SCAN_MODE", "trade").strip().lower()
        report_only = (scan_mode_env == "report")

    logger.info(f"BIST50 Multi-Timeframe Taramasi Baslatildi (report_only={report_only})...")

    # 1. Once mevcut acik pozisyonlarin TP/SL ve seans sonu kontrollerini yap
    await trade_manager.evaluate_open_positions()

    # 2. Hisseleri gruplar halinde tara (rate-limit asmamak icin 5'erli chunk'lar)
    chunk_size = 5
    all_results = []
    
    for i in range(0, len(BIST50_TICKERS), chunk_size):
        chunk = BIST50_TICKERS[i:i + chunk_size]
        tasks = [analyze_single_ticker(t) for t in chunk]
        chunk_res = await asyncio.gather(*tasks, return_exceptions=True)
        for r in chunk_res:
            if isinstance(r, dict):
                all_results.append(r)
        await asyncio.sleep(0.5)

    # Sonuclari skora gore sirala
    all_results.sort(key=lambda x: x.get("composite_score", 0), reverse=True)

    # 3. AL Sinyali Ureten Hisseler
    buy_signals = [r for r in all_results if r.get("signal") == "AL"]
    open_count = await trade_manager.get_active_open_positions_count()

    # 4. Eger Canli Moddaysa ve pozisyon limiti asilmadiysa en iyi sinyaller icin pozisyon ac
    executed_trades = []
    if not report_only and buy_signals and open_count < strategy_engine.MAX_CONCURRENT_POSITIONS:
        for candidate in buy_signals:
            if open_count >= strategy_engine.MAX_CONCURRENT_POSITIONS:
                break
            
            ticker = candidate["ticker"]
            price = candidate["current_price"]
            strat_info = candidate.get("strategy_plan", {})
            reasoning = (
                f"MTF Confluence: {candidate.get('confluence_status')} "
                f"({candidate.get('confluence_count')}/4 TF Onayli) | "
                f"Skor: {candidate.get('composite_score')}/100"
            )

            try:
                trade_res = await trade_manager.open_strategy_position(
                    ticker=ticker,
                    price=price,
                    strategy_info=strat_info,
                    reasoning=reasoning
                )
                executed_trades.append(trade_res)
                open_count += 1
                logger.info(f"[{ticker}] Yeni kisa vadeli pozisyon acildi -> Strateji: {strat_info.get('strategy')}")
            except Exception as ex:
                logger.debug(f"[{ticker}] Pozisyon acilamadi: {ex}")

    # 5. Guncel Acik Pozisyonlari Al
    current_open_positions = await trade_manager.get_all_open_positions()

    report = {
        "status": "success",
        "timestamp": time.time(),
        "report_only": report_only,
        "total_scanned": len(all_results),
        "buy_signals_count": len(buy_signals),
        "open_positions_count": len(current_open_positions),
        "top_picks": all_results[:10],
        "all_results": all_results,
        "open_positions": current_open_positions,
        "executed_trades": executed_trades
    }

    logger.info(f"BIST50 Taramasi Tamamlandi. {len(buy_signals)} AL Sinyali, {len(current_open_positions)} Acik Pozisyon.")
    return report