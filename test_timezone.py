import datetime
import pytz

def is_market_open_at(dt: datetime.datetime) -> bool:
    tz = pytz.timezone("Europe/Istanbul")
    istanbul_dt = dt.astimezone(tz)
    # Hafta içi ve 10:00 - 18:00 arası
    return istanbul_dt.weekday() < 5 and (10 <= istanbul_dt.hour < 18)

# Test senaryoları
if __name__ == "__main__":
    tz_istanbul = pytz.timezone("Europe/Istanbul")
    
    # 1. Hafta içi, çalışma saatleri içinde (Çarşamba 14:30)
    dt1 = tz_istanbul.localize(datetime.datetime(2026, 6, 17, 14, 30))
    print(f"Test 1 (17 Haziran 2026 Çarşamba 14:30 TR): {is_market_open_at(dt1)} (Beklenen: True)")
    
    # 2. Hafta içi, çalışma saatleri dışında (Çarşamba 08:30)
    dt2 = tz_istanbul.localize(datetime.datetime(2026, 6, 17, 8, 30))
    print(f"Test 2 (17 Haziran 2026 Çarşamba 08:30 TR): {is_market_open_at(dt2)} (Beklenen: False)")
    
    # 3. Hafta sonu (Cumartesi 12:00)
    dt3 = tz_istanbul.localize(datetime.datetime(2026, 6, 20, 12, 0))
    print(f"Test 3 (20 Haziran 2026 Cumartesi 12:00 TR): {is_market_open_at(dt3)} (Beklenen: False)")
    
    # 4. UTC saat diliminde bir makineye göre simülasyon (BIST açıkken UTC 11:30, TR 14:30)
    dt_utc = pytz.utc.localize(datetime.datetime(2026, 6, 17, 11, 30))
    print(f"Test 4 (UTC makine 17 Haziran 11:30 UTC): {is_market_open_at(dt_utc)} (Beklenen: True)")
