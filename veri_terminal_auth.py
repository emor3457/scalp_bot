"""
Telethon ile Telegram'a giris yap ve Veri Terminali Mini App URL'ini al.
Bu script terminal'de calisir, once telefon numarasi ister.
"""
import asyncio
import json
from telethon import TelegramClient
from telethon.tl.functions.messages import RequestWebViewRequest

API_ID = 36209058
API_HASH = "1cb5ac78f6b178125e4f4c4b17d5733f"
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
    print(f"\ntgWebAppData (ilk 200 karakter):\n{init_data[:200]}")

    # Kaydet
    with open("tg_init_data.txt", "w", encoding="utf-8") as f:
        f.write(init_data)
    print("\ntgWebAppData 'tg_init_data.txt' dosyasina kaydedildi.")

    await client.disconnect()
    return init_data


if __name__ == "__main__":
    asyncio.run(main())
