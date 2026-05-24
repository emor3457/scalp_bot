import random
import time
import json
import logging
from auto_analyst import inject_signal_to_bot

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
logger = logging.getLogger("TestScenario")

def run_test_scenario():
    logger.info("Test senaryosu baslatiliyor...")
    
    # 1. 615 hisselik listeyi welcome mesajindan alalim
    try:
        with open('sample_welcome.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
        btum_dict = data['data']['symbol_categories']['BTUM']
        all_tickers = list(btum_dict.keys())
    except Exception as e:
        logger.error(f"Hisse listesi okunamadi: {e}. Varsayilan liste kullanilacak.")
        all_tickers = ["THYAO", "ASELS", "EREGL", "TUPRS", "KCHOL", "GARAN", "AKBNK", "YKBNK", "ISCTR", "SAHOL",
                       "BIMAS", "SISE", "PGSUS", "EKGYO", "TCELL", "FROTO", "TOASO", "PETKM", "KOZAA", "KOZAL"]

    # 2. Test veritabanina bolca nakit ve sahte hisse ekle (sinyallerin iptal olmamasi icin)
    import database
    conn = database.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO portfolio (ticker, quantity, average_cost) VALUES ('TRY', 500000.0, 1.0)")
    for ticker in all_tickers[:100]:
        cursor.execute("INSERT OR REPLACE INTO portfolio (ticker, quantity, average_cost) VALUES (?, 1000.0, 10.0)", (ticker,))
    conn.commit()
    conn.close()
    
    # 20 rastgele hisse sec
    test_tickers = random.sample(all_tickers[:100], min(20, len(all_tickers[:100])))
    logger.info(f"Secilen 20 Rastgele Hisse: {test_tickers}")
    
    # Her hisse icin sahte (fake) ama gercekci gorunen sinyaller uret
    for i, ticker in enumerate(test_tickers):
        # Rastgele AL veya SAT secimi
        action = random.choice(["AL", "SAT"])
        
        # Sahte bir fiyat
        fake_price = round(random.uniform(10.0, 500.0), 2)
        fake_qty = int(random.uniform(10, 500))
        
        if action == "AL":
            reasoning = (
                f"TEST SİNYALİ: #{ticker} senedinde teknik formasyon canli tahta verisiyle teyit edildi. "
                f"Fiyat, EMA 50 üzerinde ve MACD pozitif. "
                f"Canlı Derinlik: Alıcı baskısı %68.5 seviyesinde (BUY). "
                f"Kurumsal İşlem Akışı: BUY yönlü para girişi görülüyor. "
                f"Bu seviyelerden scalp yönlü pozisyon açmak makuldür."
            )
        else:
            reasoning = (
                f"TEST SİNYALİ: Değerli ortaklar, #{ticker} pozisyonumuzda kârı cebe koyma vakti. "
                f"Canlı Emir Defterinde Satıcı baskısı (%72.1) arttı. "
                f"Scalp yaparken inatlaşılmaz, momentum bittiğinde nakde geçilir. "
            )
            
        analysis = {
            "ticker": ticker,
            "action": action,
            "price": fake_price,
            "quantity": fake_qty,
            "reasoning": reasoning
        }
        
        logger.info(f"Sinyal uretildi: {ticker} -> {action}")
        
        # Sinyali bota enjekte et (DB'ye yazar ve Telegram'a atar)
        inject_signal_to_bot(analysis)
        
        # Telegram tarafinda spam'e (rate limit) dusmemek icin 1 saniye bekle
        time.sleep(1.2)
        
    logger.info("Test senaryosu tamamlandi! Telegram'a 20 sinyal gonderilmis olmali.")

if __name__ == "__main__":
    run_test_scenario()
