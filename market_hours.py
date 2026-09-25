"""
market_hours.py — Türkiye Saati (Europe/Istanbul / UTC+3) ve BIST Seans Yönetimi
-------------------------------------------------------------------------------
Tüm sistemdeki zaman damgalarını, veritabanı kayıtlarını ve BIST seans kontrollerini
tek bir standartta birleştirir.

BIST Seans Saatleri:
- Sürekli Müzayede: 10:00 - 18:00
- Kapanış Seansı: 18:00 - 18:10
- Momentum Pozisyon Çıkışı: 17:50
- Hafta Sonu: Kapalı (Cumartesi, Pazar)
"""

import datetime
import pytz
import logging

logger = logging.getLogger("BistScalpBot")

TR_TIMEZONE = pytz.timezone("Europe/Istanbul")


def get_tr_now() -> datetime.datetime:
    """Anlık Türkiye yerel saatini (Europe/Istanbul aware) döner."""
    return datetime.datetime.now(TR_TIMEZONE)


def get_tr_now_str(fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    """Anlık Türkiye saatini string formatında döner."""
    return get_tr_now().strftime(fmt)


def is_bist_open(dt: datetime.datetime = None) -> bool:
    """
    Belirtilen veya anlık zamanın BIST işlem saatleri (10:00 - 18:10) içinde olup olmadığını kontrol eder.
    Hafta içi (Pazartesi=0, Cuma=4) ve saat 10:00:00 ile 18:10:00 arası True döner.
    """
    if dt is None:
        dt = get_tr_now()
    elif dt.tzinfo is None:
        dt = TR_TIMEZONE.localize(dt)
    else:
        dt = dt.astimezone(TR_TIMEZONE)

    # 1. Hafta sonu kontrolü
    if dt.weekday() >= 5:
        return False

    # 2. Saat aralığı: 10:00 <= zaman <= 18:10
    start_time = datetime.time(10, 0, 0)
    end_time = datetime.time(18, 10, 0)
    curr_time = dt.time()

    return start_time <= curr_time <= end_time


def is_session_closing(dt: datetime.datetime = None) -> bool:
    """
    Seans sonu kapanış periyodu (17:50 ve sonrası) kontrolü.
    Gün içi momentum ve vadesi dolan pozisyonların tasfiyesi için kullanılır.
    """
    if dt is None:
        dt = get_tr_now()
    elif dt.tzinfo is None:
        dt = TR_TIMEZONE.localize(dt)
    else:
        dt = dt.astimezone(TR_TIMEZONE)

    if dt.weekday() >= 5:
        return False

    return (dt.hour == 17 and dt.minute >= 50) or (dt.hour >= 18)


def format_tr_timestamp(ts: str) -> str:
    """
    Herhangi bir zaman damgasını veya veritabanı kaydını temiz TR formatına dönüştürür.
    """
    if not ts:
        return "-"
    try:
        # ISO veya SQLite formatını ayrıştır
        cleaned = ts.replace("T", " ").split(".")[0]
        return cleaned
    except Exception:
        return str(ts)
