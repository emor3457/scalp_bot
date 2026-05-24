"""
Veri Terminali - Toplu Veri Cekme
Tek WebSocket baglantisi uzerinden tum listeyi ayni anda ceker.
"""
import asyncio
import json
import ssl
import urllib.parse
import logging
from telethon import TelegramClient
from telethon.tl.functions.messages import RequestWebViewRequest

logger = logging.getLogger("BistScalpBot")

API_ID = 36209058
API_HASH = "1cb5ac78f6b178125e4f4c4b17d5733f"
SESSION_FILE = "veri_terminal_session"
BOT_USERNAME = "ucretsizderinlikbot"
APP_URL = "https://7k2v9x1r0z8t4m3n5p7w.com"
WS_URL = "wss://ws.7k2v9x1r0z8t4m3n5p7w.com"


async def get_fresh_init_data() -> str:
    """Telethon ile taze initData token'i alir."""
    client = TelegramClient(SESSION_FILE, API_ID, API_HASH)
    await client.start()
    try:
        bot = await client.get_entity(BOT_USERNAME)
        result = await client(RequestWebViewRequest(
            peer=bot, bot=bot, platform="android",
            url=APP_URL, from_bot_menu=True,
        ))
        from urllib.parse import urlparse, unquote
        fragment = urlparse(result.url).fragment
        params = {}
        for part in fragment.split("&"):
            if "=" in part:
                k, v = part.split("=", 1)
                params[k] = unquote(v)
        init_data = params.get("tgWebAppData", "")
        return init_data
    finally:
        await client.disconnect()


async def fetch_bulk_stock_data(symbols: list, timeout: int = 15) -> dict:
    """
    Belirtilen tum hisseler icin tek baglanti uzerinden canli derinlik, fiyat ve islem verisi ceker.
    Returns: {
        "ASELS": {"price": ..., "bid": ..., "ask": ..., "depth": ..., "trades": ...},
        "THYAO": {...}
    }
    """
    import websockets

    init_data = await get_fresh_init_data()
    if not init_data:
        raise RuntimeError("initData alinamadi")

    ws_url = f"{WS_URL}?init_data={urllib.parse.quote(init_data)}"
    ssl_ctx = ssl.create_default_context()

    results = {}
    for sym in symbols:
        results[sym] = {
            "symbol": sym,
            "price": 0.0, "bid": 0.0, "ask": 0.0,
            "high": 0.0, "low": 0.0, "volume": 0,
            "change_pct": 0.0, "prev_close": 0.0,
            "depth": {"bids": [], "asks": []},
            "trades": [],
        }

    try:
        async with websockets.connect(
            ws_url, ssl=ssl_ctx,
            additional_headers={
                "Origin": APP_URL,
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            },
            ping_interval=15, open_timeout=10,
        ) as ws:
            # Tum hisselere abone ol ve islem verilerini iste
            for sym in symbols:
                await ws.send(json.dumps({"type": "subscribe", "data": {"symbol": sym}}))
                await ws.send(json.dumps({"type": "get_trades", "data": {"symbol": sym}}))

            deadline = asyncio.get_event_loop().time() + timeout
            
            # Ne kadar veri aldik takip et
            snapshots_received = set()
            
            while asyncio.get_event_loop().time() < deadline:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=2)
                    data = json.loads(msg)
                    msg_type = data.get("type", "")

                    if msg_type == "snapshot":
                        sym = data.get("data", {}).get("symbol")
                        if not sym or sym not in results:
                            continue
                            
                        raw = data.get("data", {}).get("data", [])
                        flat = {}
                        if isinstance(raw, list):
                            for item in raw:
                                if isinstance(item, list):
                                    it = iter(item)
                                    for k in it:
                                        try:
                                            flat[k] = next(it)
                                        except StopIteration:
                                            break
                        
                        if not flat and isinstance(raw, list) and raw and not isinstance(raw[0], list):
                            it = iter(raw)
                            for k in it:
                                try:
                                    flat[k] = next(it)
                                except StopIteration:
                                    break

                        results[sym]["price"] = float(flat.get("last_price", 0) or 0)
                        results[sym]["bid"] = float(flat.get("bid_price", 0) or 0)
                        results[sym]["ask"] = float(flat.get("ask_price", 0) or 0)
                        results[sym]["high"] = float(flat.get("high_price", 0) or 0)
                        results[sym]["low"] = float(flat.get("low_price", 0) or 0)
                        results[sym]["volume"] = int(float(flat.get("volume", 0) or 0))
                        results[sym]["prev_close"] = float(flat.get("previous_close_alt", 0) or 0)
                        
                        if results[sym]["prev_close"] > 0 and results[sym]["price"] > 0:
                            results[sym]["change_pct"] = round(
                                (results[sym]["price"] - results[sym]["prev_close"]) / results[sym]["prev_close"] * 100, 2
                            )

                        bids = data.get("data", {}).get("bids", [])
                        asks = data.get("data", {}).get("asks", [])
                        if bids or asks:
                            results[sym]["depth"] = {"bids": bids, "asks": asks}
                            
                        snapshots_received.add(sym)

                    elif msg_type == "update":
                        sym = data.get("data", {}).get("symbol")
                        if not sym or sym not in results:
                            continue
                            
                        updates = data.get("data", {}).get("data", [])
                        if isinstance(updates, list):
                            for item in updates:
                                if isinstance(item, list):
                                    it = iter(item)
                                    for k in it:
                                        try:
                                            v = next(it)
                                            if k == "last_price" and v:
                                                results[sym]["price"] = float(v)
                                            elif k == "bid_price" and v:
                                                results[sym]["bid"] = float(v)
                                            elif k == "ask_price" and v:
                                                results[sym]["ask"] = float(v)
                                        except StopIteration:
                                            break

                    elif msg_type == "trades_data":
                        sym = data.get("data", {}).get("symbol")
                        if not sym or sym not in results:
                            continue
                        trades_raw = data.get("data", {}).get("trades", [])
                        results[sym]["trades"] = trades_raw[:100]  # Son 100 islem yeterli

                    elif msg_type == "depth_data":
                        sym = data.get("data", {}).get("symbol")
                        if not sym or sym not in results:
                            continue
                        results[sym]["depth"]["bids"] = data.get("data", {}).get("bids", [])
                        results[sym]["depth"]["asks"] = data.get("data", {}).get("asks", [])

                    # Tum hisselerin snapshot'i geldiyse hizli cikis
                    if len(snapshots_received) == len(symbols):
                        # Biraz daha bekle ki trade verileri de gelsin (1-2 sn)
                        await asyncio.sleep(2)
                        break

                except asyncio.TimeoutError:
                    if len(snapshots_received) >= len(symbols) * 0.8: # %80 basari yeterli
                        break
                    continue

    except Exception as e:
        logger.error(f"Toplu Veri Terminali baglanti hatasi: {e}")

    return results


def analyze_order_book(depth: dict) -> dict:
    bids = depth.get("bids", [])
    asks = depth.get("asks", [])

    if not bids and not asks:
        return {"pressure": "NODATA", "support": 0, "resistance": 0, "bid_ratio": 50.0}

    total_bid_vol = sum(float(b[1]) if isinstance(b, list) and len(b) > 1 else 0 for b in bids)
    total_ask_vol = sum(float(a[1]) if isinstance(a, list) and len(a) > 1 else 0 for a in asks)

    total = total_bid_vol + total_ask_vol
    if total == 0:
        return {"pressure": "NEUTRAL", "support": 0, "resistance": 0, "bid_ratio": 50.0}

    bid_ratio = total_bid_vol / total

    if bid_ratio > 0.65:
        pressure = "BUY"
    elif bid_ratio < 0.35:
        pressure = "SELL"
    else:
        pressure = "NEUTRAL"

    best_bid = float(bids[0][0]) if bids and isinstance(bids[0], list) else 0
    best_ask = float(asks[0][0]) if asks and isinstance(asks[0], list) else 0

    return {
        "pressure": pressure,
        "bid_ratio": round(bid_ratio * 100, 1),
        "total_bid_vol": int(total_bid_vol),
        "total_ask_vol": int(total_ask_vol),
        "best_bid": best_bid,
        "best_ask": best_ask,
        "support": best_bid,
        "resistance": best_ask,
    }


def analyze_trade_flow(trades: list) -> dict:
    if not trades:
        return {"flow": "NODATA", "buy_vol": 0, "sell_vol": 0}

    buy_vol = 0
    sell_vol = 0
    buy_institutions = {}
    sell_institutions = {}

    for trade in trades:
        if isinstance(trade, list) and len(trade) >= 5:
            qty = float(trade[2] or 0)
            buyer = str(trade[3] or "")
            seller = str(trade[4] or "")
            buy_vol += qty
            sell_vol += qty
            if buyer:
                buy_institutions[buyer] = buy_institutions.get(buyer, 0) + qty
            if seller:
                sell_institutions[seller] = sell_institutions.get(seller, 0) + qty

    top_buyers = sorted(buy_institutions.items(), key=lambda x: x[1], reverse=True)[:3]
    top_sellers = sorted(sell_institutions.items(), key=lambda x: x[1], reverse=True)[:3]

    total = buy_vol + sell_vol
    flow_ratio = buy_vol / total if total > 0 else 0.5

    return {
        "flow": "BUY" if flow_ratio > 0.60 else ("SELL" if flow_ratio < 0.40 else "NEUTRAL"),
        "buy_vol": int(buy_vol),
        "sell_vol": int(sell_vol),
        "top_buyers": top_buyers,
        "top_sellers": top_sellers,
        "total_trades": len(trades),
    }


if __name__ == "__main__":
    async def main():
        symbols = ["THYAO", "ASELS", "EREGL", "TUPRS", "KCHOL"]
        print(f"Toplu veri cekiliyor: {symbols}")
        results = await fetch_bulk_stock_data(symbols, timeout=10)
        
        for sym, data in results.items():
            if data["price"] > 0:
                print(f"\n--- {sym} ---")
                print(f"Fiyat: {data['price']} TL (Degisim: %{data['change_pct']})")
                
                ob = analyze_order_book(data["depth"])
                tf = analyze_trade_flow(data["trades"])
                
                print(f"Derinlik: {ob['pressure']} ({ob.get('bid_ratio', 0)}% Alici) - Alici Hacmi: {ob.get('total_bid_vol')}, Satici Hacmi: {ob.get('total_ask_vol')}")
                print(f"Islemler: {tf['flow']} - Son {tf.get('total_trades', 0)} islem. En cok alanlar: {tf.get('top_buyers')}")
            else:
                print(f"\n--- {sym} : Veri Alinamadi ---")

    asyncio.run(main())
