import os
import logging
import asyncio
import database
import telegram_utils
import order_executor

logger = logging.getLogger("BistScalpBot")

class TradeExecutionError(Exception):
    """Islem gerceklestirme sirasinda olusan hatalar."""
    def __init__(self, message: str, details: dict = None):
        super().__init__(message)
        self.details = details or {}

async def process_trade_signal(ticker: str, action: str, price: float, quantity: float, reasoning: str = None) -> dict:
    """
    Hem webhook hem de auto_analyst tarafindan uretilen sinyalleri ortak bir asenkron portfoy ve veritabani
    motoru uzerinden isler. Risk kontrollerini yapar, islemleri kaydeder ve Telegram bildirimlerini tetikler.
    """
    demo_mode = os.getenv("DEMO_MODE", "True").strip().lower() == "true"
    mode_text = " (Simule)" if demo_mode else " (GERCEK)"
    total_cost = price * quantity

    conn = await database.get_async_db_connection()

    try:
        # 1. Sinyali signals tablosuna kaydet
        await conn.execute(
            "INSERT INTO signals (ticker, action, price, quantity, reasoning) VALUES (?, ?, ?, ?, ?)",
            (ticker, action, price, quantity, reasoning)
        )
        await conn.commit()

        # 2. Portfoy Islemleri & Risk Kontrolleri
        # TRY Bakiyesini al
        async with conn.execute("SELECT quantity FROM portfolio WHERE ticker = 'TRY'") as cursor:
            try_row = await cursor.fetchone()
            cash = try_row["quantity"] if try_row else 0.0

        if action == "AL":
            if cash < total_cost:
                logger.warning(f"Bakiye yetersiz! Gerekli: {total_cost} TL, Mevcut: {cash} TL. Islem iptal edildi.")
                # Telegram Bildirimi (Asenkron thread ile)
                err_msg = (
                    f"⚠️ <b>ISLEM IPTAL [Yetersiz Bakiye]{mode_text}</b>\n\n"
                    f"📌 <b>Hisse:</b> #{ticker}\n"
                    f"👉 <b>Yon:</b> AL\n"
                    f"💵 <b>Fiyat:</b> {price:.2f} TL\n"
                    f"📦 <b>Miktar:</b> {quantity} Lot\n"
                    f"💰 <b>Gerekli:</b> {total_cost:.2f} TL\n"
                    f"❌ <b>Mevcut Bakiye:</b> {cash:.2f} TL"
                )
                await asyncio.to_thread(telegram_utils.send_telegram_message, err_msg)
                raise TradeExecutionError("Bakiye yetersiz", {"required": total_cost, "available": cash})

            # Nakit bakiyesini dusur
            new_cash = cash - total_cost
            await conn.execute("UPDATE portfolio SET quantity = ? WHERE ticker = 'TRY'", (new_cash,))

            # Portfoyde hisseyi guncelle veya ekle
            async with conn.execute("SELECT quantity, average_cost FROM portfolio WHERE ticker = ?", (ticker,)) as cursor:
                stock_row = await cursor.fetchone()

            if stock_row:
                old_qty = stock_row["quantity"]
                old_cost = stock_row["average_cost"]
                new_qty = old_qty + quantity
                new_avg_cost = ((old_qty * old_cost) + total_cost) / new_qty
                await conn.execute(
                    "UPDATE portfolio SET quantity = ?, average_cost = ? WHERE ticker = ?",
                    (new_qty, new_avg_cost, ticker)
                )
            else:
                await conn.execute(
                    "INSERT INTO portfolio (ticker, quantity, average_cost) VALUES (?, ?, ?)",
                    (ticker, quantity, price)
                )

        elif action == "SAT":
            # Portfoyde hisse kontrolu
            async with conn.execute("SELECT quantity, average_cost FROM portfolio WHERE ticker = ?", (ticker,)) as cursor:
                stock_row = await cursor.fetchone()
                stock_qty = stock_row["quantity"] if stock_row else 0.0

            if stock_qty < quantity:
                logger.warning(f"Hisse miktari yetersiz! Satilmak istenen: {quantity}, Mevcut: {stock_qty}. Islem iptal edildi.")
                # Telegram Bildirimi
                err_msg = (
                    f"⚠️ <b>ISLEM IPTAL [Yetersiz Hisse]{mode_text}</b>\n\n"
                    f"📌 <b>Hisse:</b> #{ticker}\n"
                    f"👉 <b>Yon:</b> SAT\n"
                    f"💵 <b>Fiyat:</b> {price:.2f} TL\n"
                    f"📦 <b>Satilmak Istenen:</b> {quantity} Lot\n"
                    f"❌ <b>Mevcut Hisse:</b> {stock_qty} Lot"
                )
                await asyncio.to_thread(telegram_utils.send_telegram_message, err_msg)
                raise TradeExecutionError("Yetersiz hisse miktari", {"requested": quantity, "available": stock_qty})

            # Hisse miktarini dusur veya portfoyden kaldir
            new_qty = stock_qty - quantity
            if new_qty == 0:
                await conn.execute("DELETE FROM portfolio WHERE ticker = ?", (ticker,))
            else:
                await conn.execute("UPDATE portfolio SET quantity = ? WHERE ticker = ?", (new_qty, ticker))

            # Nakit bakiyesini artir
            new_cash = cash + total_cost
            await conn.execute("UPDATE portfolio SET quantity = ? WHERE ticker = 'TRY'", (new_cash,))

        # 3. Gerceklesen islemi trades tablosuna yaz
        await conn.execute(
            "INSERT INTO trades (ticker, action, price, quantity, total_value, reasoning) VALUES (?, ?, ?, ?, ?, ?)",
            (ticker, action, price, quantity, total_cost, reasoning)
        )
        await conn.commit()

        logger.info(
            f"Islem Basarili{mode_text} -> Hisse: {ticker} | "
            f"Yon: {action} | Fiyat: {price} | Miktar: {quantity} | Toplam: {total_cost} TL"
        )

        # Basarili Islem Bildirimi
        emoji = "🟢" if action == "AL" else "🔴"
        success_msg = (
            f"{emoji} <b>ISLEM BASARILI{mode_text}</b>\n\n"
            f"📌 <b>Hisse:</b> #{ticker}\n"
            f"👉 <b>Yon:</b> {action}\n"
            f"💵 <b>Fiyat:</b> {price:.2f} TL\n"
            f"📦 <b>Miktar:</b> {quantity:.0f} Lot\n"
            f"💰 <b>Toplam:</b> {total_cost:.2f} TL"
        )
        if reasoning:
            success_msg += f"\n\n✍️ <b>Analiz Gerekcesi:</b>\n<i>{reasoning}</i>"
            
        # Telegram bildirimi (Asenkron thread ile)
        await asyncio.to_thread(telegram_utils.send_telegram_message, success_msg)

        # 4. Gercek BIST Emir Otomasyonu (Sanal Mod degilse)
        if not demo_mode:
            logger.info("Gercek emir otomasyonu tetikleniyor...")
            trigger_real_order = True
        else:
            logger.info("Sanal Mod (Demo) aktif. Gercek emir gonderilmedi.")
            trigger_real_order = False

        return {
            "status": "success",
            "message": f"Islem simule edildi. Mod: {'Sanal (Demo)' if demo_mode else 'Gercek'}",
            "trigger_real_order": trigger_real_order,
            "data": {
                "ticker": ticker,
                "action": action,
                "price": price,
                "quantity": quantity
            }
        }

    except TradeExecutionError:
        await conn.rollback()
        raise
    except Exception as e:
        await conn.rollback()
        logger.error(f"Islem sirasinda beklenmeyen hata: {str(e)}")
        raise TradeExecutionError(f"Islem gerceklestirilemedi: {str(e)}")
    finally:
        await conn.close()
