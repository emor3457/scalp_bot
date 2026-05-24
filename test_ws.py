"""
Veri Terminali - Canli WebSocket Baglantisi
Dogru URL formati: wss://ws.7k2v9x1r0z8t4m3n5p7w.com?init_data=<token>
"""
import asyncio
import json
import ssl
import urllib.parse
import sys

# Auth token'i oku
with open("tg_init_data.txt", "r", encoding="utf-8") as f:
    INIT_DATA = f.read().strip()

WS_BASE = "wss://ws.7k2v9x1r0z8t4m3n5p7w.com"


async def fetch_live_data(symbol="ASELS", duration=30):
    import websockets

    ssl_ctx = ssl.create_default_context()
    
    # Dogru URL: init_data parametresi
    ws_url = f"{WS_BASE}?init_data={urllib.parse.quote(INIT_DATA)}"
    
    print(f"Baglaniliyor: {WS_BASE}?init_data=***")
    print(f"Hisse: {symbol}\n")

    try:
        async with websockets.connect(
            ws_url,
            ssl=ssl_ctx,
            additional_headers={
                "Origin": "https://7k2v9x1r0z8t4m3n5p7w.com",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            },
            ping_interval=20,
            open_timeout=10,
        ) as ws:
            print("✅ Baglanti KURULDU!\n")

            # Hisseye abone ol
            await ws.send(json.dumps({"type": "subscribe", "data": {"symbol": symbol}}))
            print(f"📡 {symbol} abonelik mesaji gonderildi\n")

            # Broker listesi
            await ws.send(json.dumps({"type": "get_brokers"}))

            # Gelen tum mesajlari kaydet
            collected = {"depth": None, "trades": None, "market": None, "welcome": None}
            print("--- CANLI VERİ GELİYOR ---")

            end_time = asyncio.get_event_loop().time() + duration
            msg_count = 0

            while asyncio.get_event_loop().time() < end_time:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=5)
                    data = json.loads(msg)
                    msg_type = data.get("type", "?")
                    msg_count += 1

                    # Onemli mesajlari goster
                    if msg_type == "welcome":
                        print(f"[{msg_count}] WELCOME mesaji alindi")
                        collected["welcome"] = data
                        with open("sample_welcome.json", "w", encoding="utf-8") as f:
                            json.dump(data, f, ensure_ascii=False, indent=2)
                        print("  -> sample_welcome.json kaydedildi")
                        
                    elif msg_type in ["snapshot", "depth", "update"]:
                        print(f"[{msg_count}] {msg_type.upper()}: {symbol}")
                        if "depth" in data or msg_type == "depth":
                            collected["depth"] = data
                            with open(f"sample_{msg_type}.json", "w", encoding="utf-8") as f:
                                json.dump(data, f, ensure_ascii=False, indent=2)
                            print(f"  -> sample_{msg_type}.json kaydedildi")
                        # Kisaca goster
                        print(f"  {json.dumps(data, ensure_ascii=False)[:300]}")
                        
                    elif msg_type == "market_data":
                        print(f"[{msg_count}] MARKET DATA: {len(str(data))} byte")
                        collected["market"] = data
                        with open("sample_market.json", "w", encoding="utf-8") as f:
                            json.dump(data, f, ensure_ascii=False, indent=2)
                        
                    elif msg_type == "error":
                        print(f"[{msg_count}] HATA: {data}")
                        
                    else:
                        print(f"[{msg_count}] {msg_type}: {json.dumps(data, ensure_ascii=False)[:200]}")

                except asyncio.TimeoutError:
                    print("  (bekleniyor...)")
                    continue

            print(f"\n✅ Tamamlandi! Toplam {msg_count} mesaj alindi.")
            print(f"Alinan veri tipleri: {[k for k,v in collected.items() if v]}")

    except Exception as e:
        print(f"❌ Hata: {e}")
        
        # Token suresi dolmuş olabilir, yenile
        if "401" in str(e) or "403" in str(e):
            print("\n⚠️  Token suresi dolmus olabilir.")
            print("'python veri_terminal_auth.py' calistirarak yeni token alin.")


async def get_fresh_token_and_connect(symbol="ASELS"):
    """Her baglantida taze token al."""
    from telethon import TelegramClient
    from telethon.tl.functions.messages import RequestWebViewRequest
    
    API_ID = 36209058
    API_HASH = "1cb5ac78f6b178125e4f4c4b17d5733f"
    
    client = TelegramClient("veri_terminal_session", API_ID, API_HASH)
    await client.start()
    
    bot = await client.get_entity("ucretsizderinlikbot")
    result = await client(RequestWebViewRequest(
        peer=bot, bot=bot, platform="android",
        url="https://7k2v9x1r0z8t4m3n5p7w.com",
        from_bot_menu=True,
    ))
    
    from urllib.parse import urlparse, parse_qs, unquote
    fragment = urlparse(result.url).fragment
    params = {}
    for part in fragment.split("&"):
        if "=" in part:
            k, v = part.split("=", 1)
            params[k] = unquote(v)
    
    init_data = params.get("tgWebAppData", "")
    print(f"Taze token alindi ({len(init_data)} karakter)")
    
    with open("tg_init_data.txt", "w", encoding="utf-8") as f:
        f.write(init_data)
    
    await client.disconnect()
    return init_data


if __name__ == "__main__":
    symbol = sys.argv[1] if len(sys.argv) > 1 else "ASELS"
    
    # Once taze token al
    async def main():
        global INIT_DATA
        print("Taze token aliniyor...")
        INIT_DATA = await get_fresh_token_and_connect(symbol)
        print("Baglanti kuruluyor...\n")
        await fetch_live_data(symbol, duration=30)
    
    asyncio.run(main())
