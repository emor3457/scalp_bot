import time
import logging
import asyncio
import yfinance as yf

logger = logging.getLogger("BistScalpBot")

# Basit onbellek (cache) sozluk yapisi: { "ticker": (price, timestamp) }
PRICE_CACHE = {}
CACHE_EXPIRE_SECONDS = 300 # 5 dakika onbellek suresi

def _fetch_yfinance_price(yahoo_ticker: str) -> float:
    """Senkron olarak Yahoo Finance'ten fiyat verisi ceker. Thread pool icinde calistirilacaktir."""
    stock = yf.Ticker(yahoo_ticker)
    
    # fast_info ile son fiyati alalim
    info = stock.fast_info
    price = info.get('lastPrice') or info.get('previousClose')
    
    if price is None:
        # history yedek yontemi
        hist = stock.history(period="1d")
        if not hist.empty:
            price = hist['Close'].iloc[-1]
            
    if price is not None and price > 0:
        return float(price)
    return None

async def get_stock_price(ticker: str) -> float:
    """
    Yahoo Finance uzerinden belirtilen BIST hissesinin gecikmeli guncel fiyatini ceker (Asenkron).
    5 dakika omurlu yerel onbellek (caching) kullanir.
    Hata durumunda rate-limit veya baglanti sorunlarini tolere etmek icin eski onbellek degerini doner.
    """
    if ticker == 'TRY':
        return 1.0

    now = time.time()
    
    # 1. Onbellek Kontrolu
    if ticker in PRICE_CACHE:
        cached_price, cached_time = PRICE_CACHE[ticker]
        if now - cached_time < CACHE_EXPIRE_SECONDS:
            logger.debug(f"Onbellekten fiyat donduruldu -> {ticker}: {cached_price} TL")
            return cached_price

    # 2. Yahoo Finance'ten Canli Veri Cekme (Thread'e tasiyarak)
    yahoo_ticker = f"{ticker}.IS"
    try:
        logger.info(f"Yahoo Finance'ten fiyat cekiliyor -> {yahoo_ticker}")
        price = await asyncio.to_thread(_fetch_yfinance_price, yahoo_ticker)
        
        if price is not None:
            # Onbellege yaz
            PRICE_CACHE[ticker] = (price, now)
            logger.info(f"Fiyat basariyla guncellendi -> {ticker}: {price} TL")
            return price
        else:
            raise ValueError("Fiyat verisi alinamadi veya gecersiz.")

    except Exception as e:
        logger.error(f"Yahoo Finance'ten veri cekilirken hata olustu ({ticker}): {str(e)}")
        # Hata durumunda onbellekte eski deger varsa onu don
        if ticker in PRICE_CACHE:
            logger.warning(f"Hata nedeniyle eski onbellek fiyati kullaniliyor -> {ticker}: {PRICE_CACHE[ticker][0]} TL")
            return PRICE_CACHE[ticker][0]
        return None
