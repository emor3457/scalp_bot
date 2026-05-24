import os
import time
import logging
from playwright.sync_api import sync_playwright

logger = logging.getLogger("BistScalpBot")

SESSION_FILE = "session.json"
# Otomasyonun hedeflenecegi web adresi (Orn: Ziraat Yatirim, Ak Yatirim vb. giris sayfasi)
TARGET_URL = "https://www.example-broker.com/login" # Buraya kendi araci kurumunuzun giris adresini yazin

def execute_order(ticker: str, action: str, price: float, quantity: float):
    """
    Playwright (Senkron) kullanarak tarayici uzerinden otomatik BIST emri gonderir.
    FastAPI BackgroundTasks tarafından bir thread icinde calistirilacagi icin event loop cakismasi yasanmaz.
    """
    logger.info(f"Tarayici otomasyonu baslatiliyor... Emir -> Hisse: {ticker} | Yon: {action} | Fiyat: {price} | Miktar: {quantity}")

    with sync_playwright() as p:
        try:
            # Tarayiciyi gorunur (headful) modda aciyoruz (SMS kodu ve giris islemlerini yapabilmeniz icin)
            browser = p.chromium.launch(headless=False, args=["--start-maximized"])
            
            # Eger daha once kaydedilmis bir oturum varsa onu yukle
            if os.path.exists(SESSION_FILE):
                logger.info("Mevcut oturum dosyasi bulundu. Oturum yukleniyor...")
                context = browser.new_context(storage_state=SESSION_FILE, no_viewport=True)
            else:
                logger.info("Oturum dosyasi bulunamadi. Yeni oturum baslatiliyor...")
                context = browser.new_context(no_viewport=True)

            page = context.new_page()
            page.goto(TARGET_URL)
            
            # Eger session.json yoksa veya oturum dusmusse kullanicinin giris yapmasi beklenir:
            if not os.path.exists(SESSION_FILE):
                logger.info("Lutfen acilan tarayici penceresinden giris yapin (Kullanici adi, sifre ve SMS onayini girin).")
                
                # Giris yapildiginda belirecek olan bir elementi bekliyoruz (Orn: Portfoy tablosu veya cikis butonu)
                dashboard_selector = "#portfolio-table, .user-profile-menu, #logout-btn"
                
                try:
                    # Giris yapmaniz icin 2 dakika (120000 ms) sure taniyoruz
                    page.wait_for_selector(dashboard_selector, timeout=120000)
                    logger.info("Giris basariyla algilandi. Oturum kaydediliyor...")
                    context.storage_state(path=SESSION_FILE)
                except Exception as ex:
                    logger.error("Giris suresi doldu veya giris algilanamadi. Islem iptal edildi.")
                    browser.close()
                    return False
            
            # 2. Emir Giriş Paneline Gitme
            logger.info("Emir iletim ekranina geciliyor...")
            
            # Simülasyon amacli log atip 5 saniye bekletiyoruz
            logger.info(f"OTOMASYON EMIR SABLONU TETIKLENDI: {ticker} icin {action} yonunde {quantity} lot {price} TL'den iletiliyor.")
            time.sleep(5)
            
            browser.close()
            return True

        except Exception as e:
            logger.error(f"Tarayici otomasyonu sirasinda hata olustu: {str(e)}")
            try:
                browser.close()
            except:
                pass
            return False

if __name__ == "__main__":
    # Test calistirmasi
    execute_order("KRONT", "AL", 75.0, 10.0)
