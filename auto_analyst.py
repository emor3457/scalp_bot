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
import bist_screener

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
    chosen_strat = strategy_plan.get("strategy")
    rsi_15m = mtf_res.get("timeframes", {}).get("15m", {}).get("rsi", 50.0)
    rsi_1h = mtf_res.get("timeframes", {}).get("1h", {}).get("rsi", 50.0)

    # Dip Avcısı: Aşırı satım dönüşü (RSI <= 32)
    if chosen_strat == "dip_avcisi" and (rsi_15m <= 32.0 or rsi_1h <= 32.0):
        signal = "AL"
    elif composite_score >= BUY_THRESHOLD and confluence_count >= 2:
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


async def scan_all_and_report(report_only: bool = None, force_tickers: list = None) -> dict:
    """
    2 Aşamalı Hibrit Huni (Two-Stage Funnel):
    1. Aşama: Tüm Borsa (~650 hisse) TradingView motoru ile taranır ve min. 20M TL hacim filtresinden
       geçirilerek en yüksek potansiyelli 20 hisse seçilir.
    2. Aşama: Bu 20 hisseye 4 timeframe MTF, temel veri ve haber analizi uygulanarak nihai skorlar hesaplanır.
    """
    if report_only is None:
        scan_mode_env = os.getenv("SCAN_MODE", "trade").strip().lower()
        report_only = (scan_mode_env == "report")

    logger.info(f"Tüm Borsa 2 Aşamalı Tarama Başlatıldı (report_only={report_only})...")

    # 1. Önce mevcut açık pozisyonların TP/SL ve seans sonu kontrollerini yap
    await trade_manager.evaluate_open_positions()

    # 2. Aşama 1: Makro Tarama (TradingView Screener)
    screener_meta = {}
    if force_tickers:
        candidate_tickers = force_tickers
        screener_meta = {
            "source": "manual_override",
            "total_scanned": len(force_tickers),
            "liquid_count": len(force_tickers),
            "dip_candidates_count": 0,
            "momentum_candidates_count": 0
        }
    else:
        screen_res = await asyncio.to_thread(bist_screener.get_screened_candidates, 20_000_000.0, 20)
        candidate_tickers = [c["ticker"] for c in screen_res.get("candidates", [])]
        screener_meta = {
            "source": screen_res.get("source", "tradingview_scanner"),
            "total_scanned": screen_res.get("total_scanned", 0),
            "liquid_count": screen_res.get("liquid_count", 0),
            "dip_candidates_count": screen_res.get("dip_candidates_count", 0),
            "momentum_candidates_count": screen_res.get("momentum_candidates_count", 0)
        }

    if not candidate_tickers:
        candidate_tickers = BIST50_TICKERS[:20]

    # 3. Aşama 2: Mikro MTF & Temel Analiz (5'erli chunk'lar)
    chunk_size = 5
    all_results = []

    for i in range(0, len(candidate_tickers), chunk_size):
        chunk = candidate_tickers[i:i + chunk_size]
        tasks = [analyze_single_ticker(t) for t in chunk]
        chunk_res = await asyncio.gather(*tasks, return_exceptions=True)
        for r in chunk_res:
            if isinstance(r, dict) and r.get("ticker"):
                all_results.append(r)
        await asyncio.sleep(0.3)

    # Sonuçları skora göre sırala
    all_results.sort(key=lambda x: x.get("composite_score", 0), reverse=True)

    # 4. AL Sinyali Üreten Hisseler
    buy_signals = [r for r in all_results if r.get("signal") == "AL"]
    open_count = await trade_manager.get_active_open_positions_count()

    # 5. Eğer Canlı Moddaysa ve pozisyon limiti aşılmadıysa en iyi sinyaller için pozisyon aç
    executed_trades = []
    if not report_only and buy_signals and open_count < strategy_engine.MAX_CONCURRENT_POSITIONS:
        for candidate in buy_signals:
            if open_count >= strategy_engine.MAX_CONCURRENT_POSITIONS:
                break
            
            ticker = candidate["ticker"]
            price = candidate["current_price"]
            strat_info = candidate.get("strategy_plan", {})
            strat_name = strat_info.get("strategy", "scaling")
            reasoning = (
                f"[{strat_name.upper()}] Confluence: {candidate.get('confluence_status')} "
                f"({candidate.get('confluence_count')}/4 TF) | "
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
                logger.info(f"[{ticker}] Yeni kısa vadeli pozisyon açıldı -> Strateji: {strat_name}")
            except Exception as ex:
                logger.debug(f"[{ticker}] Pozisyon açılamadı: {ex}")

    # 6. Güncel Açık Pozisyonları Al
    current_open_positions = await trade_manager.get_all_open_positions()

    report = {
        "status": "success",
        "timestamp": time.time(),
        "report_only": report_only,
        "screener_meta": screener_meta,
        "total_scanned": screener_meta.get("total_scanned", len(all_results)),
        "liquid_count": screener_meta.get("liquid_count", len(all_results)),
        "analyzed_count": len(all_results),
        "buy_signals_count": len(buy_signals),
        "open_positions_count": len(current_open_positions),
        "top_picks": all_results[:15],
        "all_results": all_results,
        "open_positions": current_open_positions,
        "executed_trades": executed_trades
    }

    logger.info(
        f"Tarama Tamamlandı. {screener_meta.get('total_scanned', 0)} Hisse -> "
        f"{screener_meta.get('liquid_count', 0)} Likit -> {len(all_results)} Detaylı Analiz -> "
        f"{len(buy_signals)} AL Sinyali."
    )
    return report