import os
import time
import logging

logger = logging.getLogger("BistScalpBot")

def execute_order(ticker: str, action: str, price: float, quantity: float):
    """
    Simüle edilmis emir gonderimi (Hafifletilmis versiyon).
    Playwright kaldirildi. Arka planda log atip bekler.
    """
    logger.info(f"Emir simulasyonu baslatiliyor... Hisse: {ticker} | Yon: {action} | Fiyat: {price} | Miktar: {quantity}")

    try:
        # Simülasyon amacli log atip 5 saniye bekletiyoruz
        logger.info(f"OTOMASYON EMIR SABLONU TETIKLENDI: {ticker} icin {action} yonunde {quantity} lot {price} TL'den iletildi.")
        time.sleep(5)
        
        return True

    except Exception as e:
        logger.error(f"Emir iletimi sirasinda hata olustu: {str(e)}")
        return False

if __name__ == "__main__":
    # Test calistirmasi
    execute_order("KRONT", "AL", 75.0, 10.0)
