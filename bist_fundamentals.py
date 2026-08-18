"""
bist_fundamentals.py — BIST temel veri saglayicisi.

Kaynak: uzmanpara.milliyet.com.tr "Oranlar / Mali Degerler" tablosu
(Foreks/BIST kaynakli veri, 15 dk gecikmeli) — F/K, PD/DD, ROE
(NetKar/Ozsermaye), temettu verimliligi, piyasa degeri, oz sermaye,
net kar, halka aciklik gibi gercek BIST oranlarini icerir.

Neden bu kaynak:
  - isYatirim'in "Temel Degerler" tablosu sunucu tarafi DataTables POST ile
    yukleniyor (session/JS reverse-engineering gerektirir, kirilgan).
  - KAP mali tablolari ASP.NET session + sirket ID gerektirir; bilanco
    kalemleri icin bu modul ileride genisletilebilir (TODO).
  - uzmanpara statik HTML doner ve BIST kaynakli ayni oranlari icerir.

Kullanim:
    import bist_fundamentals
    veri = bist_fundamentals.get_fundamentals("THYAO")
    # -> {"fk": 3.76, "pd_dd": 0.41, "roe": 0.02, "temettu_verimi_pct": 1.5599,
    #     "piyasa_degeri": 421245000000, "oz_sermaye": 1018517000000,
    #     "net_kar": 18864000000, "halka_aciklik_pct": 50.34,
    #     "period": "2026-06", ...}  — hata durumunda {}
    30 dakika onbellek kullanir.
"""

import logging
import re
import ssl
import time
import unicodedata
import urllib.request

logger = logging.getLogger("BistScalpBot")

BASE_URL = "https://uzmanpara.milliyet.com.tr/borsa/anahtar-oranlar/{ticker}/"

CACHE = {}
CACHE_TTL = 1800  # 30 dakika

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
# SSL: Sistem sertifikalari kullanilir (guvenli)
_CTX = ssl.create_default_context()

# Etiket eslemesi (aksansizlastirilmis -> anahtar)
LABEL_MAP = {
    "halka aciklik": "halka_aciklik_pct",
    "f/k": "fk",
    "pd/dd": "pd_dd",
    "netkar/ ozsermaye": "roe",
    "sermaye": "sermaye",
    "oz sermaye": "oz_sermaye",
    "temettu verimliligi": "temettu_verimi_pct",
    "nakit net temettu": "nakit_net_temettu",
    "net kar": "net_kar",
    "piyasa degeri": "piyasa_degeri",
    "senet sayisi": "senet_sayisi",
}


_TURKISH_MAP = str.maketrans({
    "ı": "i", "İ": "i", "Ş": "s", "ş": "s", "Ğ": "g", "ğ": "g",
    "Ü": "u", "ü": "u", "Ö": "o", "ö": "o", "Ç": "c", "ç": "c",
})


def _fold(text: str) -> str:
    """Aksansizlastirma + kucuk harf (Turkce karakterlere dayanikli)."""
    text = text.translate(_TURKISH_MAP)  # noktasiz i (U+0131) NFKD'de cozulmez, acikca eşle
    folded = "".join(
        ch for ch in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(ch)
    ).lower()
    return folded.replace("\ufffd", "")  # cozumlenemeyen baytlari at


def _parse_tr_number(s: str):
    """Turkce sayi: 1.234,56 -> 1234.56; 1.380.000.000 -> 1380000000; 3,76 -> 3.76."""
    s = s.strip().replace("%", "").replace("\xa0", "").replace(" ", "")
    if not s or s in ("-", "--", "A/D", "a/d"):
        return None
    try:
        if "," in s and "." in s:
            return float(s.replace(".", "").replace(",", "."))
        if "," in s:
            return float(s.replace(",", "."))
        if "." in s:
            return float(s.replace(".", ""))  # binlik ayirici
        return float(s)
    except ValueError:
        return None


def _fetch_page(ticker: str) -> str:
    url = BASE_URL.format(ticker=ticker)
    req = urllib.request.Request(url, headers=HEADERS)
    raw = urllib.request.urlopen(req, timeout=20, context=_CTX).read()
    # Sayfa UTF-8 kodludur (dogrulandi: "A\xc3\xa7\xc4\xb1kl\xc4\xb1k" = "Aciklik")
    for enc in ("utf-8", "cp1254", "latin-1"):
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", "replace")


def _parse_table(html: str) -> dict:
    """'Oranlar / Mali Degerler' tablosundan (etiket, deger) ciftlerini cikarir."""
    start = html.find("Oranlar / Mali De")
    if start == -1:
        start = html.find("Mali De")
    if start == -1:
        return {}

    # Tablonun basindaki donem (ornek: 2026-06)
    period = None
    pm = re.search(r"<th[^>]*class=\"currency\"[^>]*>\s*([0-9]{4}-[0-9]{2})", html[start:start + 4000])
    if pm:
        period = pm.group(1)

    data = {"period": period}
    # <td class="currency">ETIKET</td><td class="">DEGER</td>
    pattern = re.compile(
        r"<td[^>]*class=\"currency\"[^>]*>\s*([^<]+?)\s*</td>\s*<td[^>]*class=\"\"[^>]*>\s*([^<]+?)\s*</td>"
    )
    for label_raw, value_raw in pattern.findall(html[start:start + 20000]):
        key = LABEL_MAP.get(_fold(label_raw))
        if key is None:
            continue
        val = _parse_tr_number(value_raw)
        if val is not None:
            data[key] = val
    return data


def get_fundamentals(ticker: str) -> dict:
    """BIST hissesi icin temel oranlari dondurur; hata/bos ise {}."""
    ticker = ticker.upper().replace(".IS", "")
    now = time.time()

    cached = CACHE.get(ticker)
    if cached and now - cached[1] < CACHE_TTL:
        return cached[0]

    try:
        html = _fetch_page(ticker)
        data = _parse_table(html)
        if not data or len(data) <= 1:
            logger.warning(f"uzmanpara temel veri bulunamadi: {ticker}")
            return {}
        CACHE[ticker] = (data, now)
        logger.info(f"uzmanpara temel veri alindi -> {ticker}: F/K={data.get('fk')}, "
                    f"PD/DD={data.get('pd_dd')}, donem={data.get('period')}")
        return data
    except Exception as e:
        logger.warning(f"uzmanpara temel veri hatasi [{ticker}]: {e}")
        return {}


def clear_cache(ticker: str = None):
    """Test/uygulama icin onbellek temizleme."""
    if ticker:
        CACHE.pop(ticker.upper().replace(".IS", ""), None)
    else:
        CACHE.clear()


if __name__ == "__main__":
    import sys
    t = sys.argv[1] if len(sys.argv) > 1 else "THYAO"
    print(get_fundamentals(t))
