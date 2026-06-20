"""
news_analyst.py
---------------
BIST hisseleri icin Yahoo Finance RSS beslemeleri uzerinden haber ceker
ve basit anahtar kelime tabanli bir duyarlilik skoru (0-100) uretir.

Pozitif haberler skoru arttirir, negatif haberler skoru dusurur.
Haber verisi yoksa veya hata olursa nötr skor (50) doner.
"""

import asyncio
import logging
import time
import urllib.request
from xml.etree import ElementTree

logger = logging.getLogger("BistScalpBot")

# --- Kelime Sozlukleri ---
POSITIVE_WORDS = [
    "yukseldi", "artti", "kazanc", "kar", "rekor", "yuksek", "guclu", "pozitif",
    "buy", "upgrade", "rise", "gain", "profit", "growth", "beat", "surpass",
    "record", "strong", "bullish", "rally", "surge", "outperform", "dividend",
    "acquisition", "expansion", "approved", "contract", "deal", "partnership",
    "yukselis", "kâr", "büyüme", "ihracat", "ihale", "anlaşma", "onay",
    "siparis", "ihracat", "yatirim", "temettü",
]

NEGATIVE_WORDS = [
    "düştü", "azaldi", "zarar", "kayip", "dusuk", "zayif", "negatif",
    "sell", "downgrade", "fall", "loss", "decline", "weak", "miss", "below",
    "bearish", "crash", "drop", "underperform", "fine", "penalty", "lawsuit",
    "investigation", "fraud", "default", "bankruptcy", "risk",
    "düsüs", "kayıp", "ceza", "dava", "sorusturma", "konkordato",
    "iflas", "borclanma", "zarar", "kriz",
]

STRONG_POSITIVE = ["rekor", "record", "surge", "rally", "beat", "outperform", "acquisition"]
STRONG_NEGATIVE = ["fraud", "bankruptcy", "default", "lawsuit", "iflas", "konkordato", "ceza"]

# Onbellek: { "ticker": (score, timestamp) }
NEWS_CACHE: dict = {}
NEWS_CACHE_EXPIRE = 1800  # 30 dakika


def _score_headline(title: str) -> int:
    """
    Bir haber basligini analiz ederek +/- puan uretir.
    Kuvvetli kelimeler 2 kat agirlik tasir.
    """
    title_lower = title.lower()
    score = 0

    for word in POSITIVE_WORDS:
        if word in title_lower:
            score += 2 if word in STRONG_POSITIVE else 1

    for word in NEGATIVE_WORDS:
        if word in title_lower:
            score -= 2 if word in STRONG_NEGATIVE else 1

    return score


def _fetch_yahoo_rss(ticker_is: str) -> list[str]:
    """
    Yahoo Finance RSS beslemesinden hisse haberlerini senkron olarak ceker.
    BIST hissesi icin 'TICKER.IS' formatinda sorgu yapilir.
    """
    url = f"https://finance.yahoo.com/rss/headline?s={ticker_is}"
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; BistBot/1.0)"}
        )
        with urllib.request.urlopen(req, timeout=8) as response:
            content = response.read()

        root = ElementTree.fromstring(content)
        titles = []
        for item in root.iter("item"):
            title_el = item.find("title")
            if title_el is not None and title_el.text:
                titles.append(title_el.text.strip())

        return titles[:15]  # En fazla 15 haber al

    except Exception as e:
        logger.debug(f"RSS haberleri cekilemedi ({ticker_is}): {str(e)}")
        return []


async def get_news_score(ticker: str) -> float:
    """
    Belirtilen BIST hissesi icin haber duyarlilik skoru doner (0-100).
    30 dakika onbellek kullanir. Hata veya haber yoksa 50 (notr) doner.

    Puan yorumu:
        >= 70  → Guclu pozitif haber ortami
        50-69  → Notr / karma
        30-49  → Zayif / dikkatli
        < 30   → Negatif haber baskisi (sinyal bloklayici)
    """
    now = time.time()

    # Onbellek kontrolu
    if ticker in NEWS_CACHE:
        cached_score, cached_time = NEWS_CACHE[ticker]
        if now - cached_time < NEWS_CACHE_EXPIRE:
            logger.debug(f"Haber skoru onbellekten alindi -> {ticker}: {cached_score:.1f}")
            return cached_score

    yahoo_ticker = f"{ticker}.IS"

    try:
        logger.info(f"Yahoo Finance RSS haberleri cekiliyor -> {yahoo_ticker}")
        headlines = await asyncio.to_thread(_fetch_yahoo_rss, yahoo_ticker)

        if not headlines:
            logger.debug(f"{ticker} icin haber bulunamadi, notr skor (50) donuluyor.")
            return 50.0

        # Her baslik icin puan hesapla
        raw_scores = [_score_headline(h) for h in headlines]
        total_raw = sum(raw_scores)
        n = len(raw_scores)

        # Normalize et: ham skoru -2*n ile +2*n arasina gore 0-100'e cevir
        max_possible = 2 * n
        normalized = (total_raw + max_possible) / (2 * max_possible) * 100
        final_score = max(0.0, min(100.0, normalized))

        # Onbellege yaz
        NEWS_CACHE[ticker] = (final_score, now)

        logger.info(
            f"Haber analizi tamamlandi -> {ticker}: {n} haber, "
            f"ham={total_raw:+d}, skor={final_score:.1f}"
        )
        return final_score

    except Exception as e:
        logger.error(f"{ticker} haber skoru hesaplanirken hata: {str(e)}")
        return 50.0


async def get_news_headlines(ticker: str) -> list[str]:
    """
    Haber basliklarini metin olarak doner (reasoning icin kullanilir).
    """
    yahoo_ticker = f"{ticker}.IS"
    try:
        headlines = await asyncio.to_thread(_fetch_yahoo_rss, yahoo_ticker)
        return headlines[:5]
    except Exception:
        return []
