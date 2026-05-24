import os
import urllib.request
import urllib.parse
import json
import logging
from dotenv import load_dotenv

# .env yukle
load_dotenv()

logger = logging.getLogger("BistScalpBot")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

def send_telegram_message(message: str):
    """
    Telegram API uzerinden belirtilen Chat ID'ye mesaj gonderir.
    Hata durumunda programin cokmesini engellemek icin try-except kullanir.
    """
    # Token veya Chat ID doldurulmadiysa veya varsayilan degerdeyse mesaj atma
    if (not TELEGRAM_BOT_TOKEN or 
        not TELEGRAM_CHAT_ID or 
        "YOUR_TELEGRAM" in TELEGRAM_BOT_TOKEN or 
        "YOUR_TELEGRAM" in TELEGRAM_CHAT_ID):
        logger.warning("Telegram ayarlari yapilmamis veya eksik. Bildirim gonderilmedi.")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }

    try:
        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(
            url,
            data=data,
            headers={'Content-Type': 'application/json'},
            method='POST'
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            res_body = response.read().decode('utf-8')
            res_json = json.loads(res_body)
            if res_json.get("ok"):
                logger.info("Telegram bildirimi basariyla gonderildi.")
                return True
            else:
                logger.error(f"Telegram API hatasi: {res_body}")
                return False
    except Exception as e:
        logger.error(f"Telegram bildirimi gonderilemedi: {str(e)}")
        return False
