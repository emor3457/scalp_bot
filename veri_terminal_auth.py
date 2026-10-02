"""
Telethon ile Telegram'a giris yap ve Veri Terminali Mini App URL'ini al.
Bu script terminal'de calisir, once telefon numarasi ister.
"""
import asyncio
import json
import os
import sys
from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.tl.functions.messages import RequestWebViewRequest

load_dotenv()
# Kimlik bilgileri ASLA koda yazilmaz; .env dosyasindan okunur.
API_ID = os.getenv("API_ID", "").strip()
API_HASH = os.getenv("API_HASH", "").strip()
if not API_ID or not API_HASH:
    sys.exit("HATA: API_ID ve API_HASH .env dosyasinda tanimli olmali (bkz. .env.example).")
API_ID = int(API_ID)
SESSION_FILE = "veri_terminal_session"
BOT_USERNAME = "ucretsizderinlikbot"
APP_URL = "https://7k2v9x1r0z8t4m3n5p7w.com"


async def main():
    client = TelegramClient(SESSION_FILE, API_ID, API_HASH)
    await client.start()

    me = await client.get_me()
    print(f"Giris yapildi: {me.first_name}")

    bot = await client.get_entity(BOT_USERNAME)
    print(f"Bot bulundu: {bot.id}")

    result = await client(RequestWebViewRequest(
        peer=bot,
        bot=bot,
        platform="android",
        url=APP_URL,
        from_bot_menu=True,
    ))

    url = result.url
    print(f"\nMini App URL alindi!")

    # URL'den tgWebAppData'yi cikart
    from urllib.parse import urlparse, parse_qs, unquote
    fragment = urlparse(url).fragment
    params = {}
    for part in fragment.split("&"):
        if "=" in part:
            k, v = part.split("=", 1)
            params[k] = unquote(v)

    init_data = params.get("tgWebAppData", "")
    print(f"\ntgWebAppData alindi ({len(init_data)} karakter).")

    # Kaydet
    with open("tg_init_data.txt", "w", encoding="utf-8") as f:
        f.write(init_data)
    print("\ntgWebAppData 'tg_init_data.txt' dosyasina kaydedildi.")

    await client.disconnect()
    return init_data


if __name__ == "__main__":
    asyncio.run(main())
