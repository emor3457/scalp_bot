"""
trade_manager.py — Portfoy, Risk ve Kisa Vadeli Pozisyon Motoru (v2)
---------------------------------------------------------------------
- Maksimum 5 eszamanli pozisyon kontrolu
- Pozisyon basi maksimum %12 portfoy risk limiti
- 3 Strateji (Kademeli, Swing, Momentum) icin TP1, TP2, TP3 ve Trailing Stop takibi
- 17:50 BIST seans kapanisi ve vade sonu otomatik pozisyon sonlandirma
"""

import os
import time
import datetime
import pytz
import logging
import asyncio
import database
import telegram_utils
import market_data
import strategy_engine

logger = logging.getLogger("BistScalpBot")


class TradeExecutionError(Exception):
    """Islem gerceklestirme sirasinda olusan hatalar."""
    def __init__(self, message: str, details: dict = None):
        super().__init__(message)
        self.details = details or {}


async def get_total_portfolio_value() -> float:
    """Nakit ve hisselerin guncel piyasa degerlerinin toplamini hesaplar."""
    conn = await database.get_async_db_connection()
    try:
        async with conn.execute("SELECT ticker, quantity, average_cost FROM portfolio") as cursor:
            rows = await cursor.fetchall()

        total_value = 0.0
        for row in rows:
            ticker = row["ticker"]
            qty = row["quantity"]
            if ticker == "TRY":
                total_value += qty
            else:
                price = await market_data.get_stock_price(ticker)
                if price is None or price <= 0:
                    price = row["average_cost"]
                total_value += (qty * price)

        return max(1000.0, total_value)
    finally:
        await conn.close()


async def get_active_open_positions_count() -> int:
    """Acik pozisyon sayisini dondurur."""
    conn = await database.get_async_db_connection()
    try:
        async with conn.execute("SELECT COUNT(*) as cnt FROM open_positions WHERE status = 'OPEN'") as cursor:
            row = await cursor.fetchone()
            return row["cnt"] if row else 0
    finally:
        await conn.close()


async def get_all_open_positions() -> list:
    """Dashboard ve API icin tum acik pozisyonlari zenginlestirilmis verilerle dondurur."""
    conn = await database.get_async_db_connection()
    try:
        async with conn.execute("""
            SELECT id, ticker, strategy, entry_price, entry_time, initial_quantity, current_quantity,
                   tp1, tp2, tp3, sl, trailing_sl, highest_price, stage, expire_time, status, reasoning
            FROM open_positions
            WHERE status = 'OPEN'
            ORDER BY id DESC
        """) as cursor:
            rows = await cursor.fetchall()

        positions = []
        for r in rows:
            pos = dict(r)
            ticker = pos["ticker"]
            entry_price = pos["entry_price"]
            curr_qty = pos["current_quantity"]

            curr_price = await market_data.get_stock_price(ticker)
            if curr_price is None or curr_price <= 0:
                curr_price = entry_price

            pnl_val = (curr_price - entry_price) * curr_qty
            pnl_pct = ((curr_price - entry_price) / entry_price * 100) if entry_price > 0 else 0.0

            pos.update({
                "current_price": round(curr_price, 2),
                "pnl_value": round(pnl_val, 2),
                "pnl_percent": round(pnl_pct, 2),
                "total_current_value": round(curr_qty * curr_price, 2),
                "total_cost": round(entry_price * pos["initial_quantity"], 2)
            })
            positions.append(pos)

        return positions
    finally:
        await conn.close()


async def open_strategy_position(
    ticker: str,
    price: float,
    strategy_info: dict,
    reasoning: str = None
) -> dict:
    """
    Yeni bir kisa vadeli pozisyon acar. Risk kontrollerini (%12 portfoy, max 5 pozisyon) yapar.
    """
    clean_ticker = ticker.upper().replace(".IS", "")
    demo_mode = os.getenv("DEMO_MODE", "True").strip().lower() == "true"
    mode_text = " (Simule)" if demo_mode else " (GERCEK)"

    conn = await database.get_async_db_connection()
    try:
        # 1. Halihazirda bu hissede acik pozisyon var mi?
        async with conn.execute("SELECT id FROM open_positions WHERE ticker = ? AND status = 'OPEN'", (clean_ticker,)) as cursor:
            existing = await cursor.fetchone()
            if existing:
                raise TradeExecutionError(f"{clean_ticker} icin zaten acik bir pozisyon mevcut.")

        # 2. Eszamanli pozisyon limiti kontrolu (Max 5)
        open_count = await get_active_open_positions_count()
        if open_count >= strategy_engine.MAX_CONCURRENT_POSITIONS:
            raise TradeExecutionError(
                f"Maksimum 5 eszamanli pozisyon limitine ulasildi ({open_count}/5). Yeni pozisyon acilamaz."
            )

        # 3. Portfoy degeri ve bakiye kontrolu
        total_port_val = await get_total_portfolio_value()
        async with conn.execute("SELECT quantity FROM portfolio WHERE ticker = 'TRY'") as cursor:
            try_row = await cursor.fetchone()
            available_cash = try_row["quantity"] if try_row else 0.0

        quantity, total_cost, reject_reason = strategy_engine.calculate_position_size(
            available_cash=available_cash,
            total_portfolio_value=total_port_val,
            current_price=price,
            current_open_positions=open_count
        )

        if reject_reason:
            raise TradeExecutionError(reject_reason, {"cash": available_cash, "portfolio": total_port_val})

        # 4. Bakiyeden dus ve portfoye ekle
        new_cash = available_cash - total_cost
        await conn.execute("UPDATE portfolio SET quantity = ? WHERE ticker = 'TRY'", (new_cash,))

        async with conn.execute("SELECT quantity, average_cost FROM portfolio WHERE ticker = ?", (clean_ticker,)) as cursor:
            stock_row = await cursor.fetchone()

        if stock_row:
            old_qty = stock_row["quantity"]
            old_cost = stock_row["average_cost"]
            new_qty = old_qty + quantity
            new_avg = ((old_qty * old_cost) + total_cost) / new_qty
            await conn.execute("UPDATE portfolio SET quantity = ?, average_cost = ? WHERE ticker = ?", (new_qty, new_avg, clean_ticker))
        else:
            await conn.execute("INSERT INTO portfolio (ticker, quantity, average_cost) VALUES (?, ?, ?)", (clean_ticker, quantity, price))

        # 5. Trades tablosuna kaydet
        await conn.execute(
            "INSERT INTO trades (ticker, action, price, quantity, total_value, reasoning) VALUES (?, ?, ?, ?, ?, ?)",
            (clean_ticker, "AL", price, quantity, total_cost, f"[{strategy_info.get('strategy', 'auto').upper()}] {reasoning or ''}")
        )

        # 6. Open Positions tablosuna kaydet
        strat_name = strategy_info.get("strategy", "scaling")
        tp1 = strategy_info.get("tp1")
        tp2 = strategy_info.get("tp2")
        tp3 = strategy_info.get("tp3")
        sl = strategy_info.get("sl", price * 0.97)
        expire_time = strategy_info.get("expire_time")

        await conn.execute("""
            INSERT INTO open_positions (
                ticker, strategy, entry_price, initial_quantity, current_quantity,
                tp1, tp2, tp3, sl, trailing_sl, highest_price, stage, expire_time, status, reasoning
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'STAGE_INITIAL', ?, 'OPEN', ?)
        """, (clean_ticker, strat_name, price, quantity, quantity, tp1, tp2, tp3, sl, sl, price, expire_time, reasoning))

        await conn.commit()

        # 7. Telegram Bildirimi
        strat_title = strategy_engine.STRATEGY_DESCRIPTIONS.get(strat_name, strat_name)
        tp_text = f"🎯 <b>TP1:</b> {tp1:.2f} TL"
        if tp2:
            tp_text += f" | <b>TP2:</b> {tp2:.2f} TL"
        if tp3:
            tp_text += f" | <b>TP3:</b> {tp3:.2f} TL"

        msg = (
            f"🚀 <b>YENI POZISYON ACILDI{mode_text}</b>\n\n"
            f"📌 <b>Hisse:</b> #{clean_ticker}\n"
            f"🧠 <b>Strateji:</b> {strat_title}\n"
            f"💵 <b>Giris Fiyati:</b> {price:.2f} TL\n"
            f"📦 <b>Miktar:</b> {quantity:.0f} Lot\n"
            f"💰 <b>Toplam Tutar:</b> {total_cost:.2f} TL (Portfoy %{(total_cost/total_port_val*100):.1f})\n"
            f"{tp_text}\n"
            f"🛑 <b>Stop-Loss:</b> {sl:.2f} TL\n"
            f"⏳ <b>Vade/Hedef Sure:</b> {strategy_info.get('expected_hold', '1-3 Gun')}\n"
        )
        if reasoning:
            msg += f"\n✍️ <i>{reasoning}</i>"

        await asyncio.to_thread(telegram_utils.send_telegram_message, msg)

        return {
            "status": "success",
            "ticker": clean_ticker,
            "quantity": quantity,
            "entry_price": price,
            "total_cost": total_cost,
            "strategy": strat_name,
            "tp1": tp1,
            "sl": sl
        }

    except TradeExecutionError:
        await conn.rollback()
        raise
    except Exception as e:
        await conn.rollback()
        logger.error(f"Pozisyon acilirken hata: {str(e)}")
        raise TradeExecutionError(f"Pozisyon acilamadi: {str(e)}")
    finally:
        await conn.close()


async def close_position_partial_or_full(
    pos_id: int,
    ticker: str,
    sell_quantity: float,
    current_price: float,
    close_type: str,  # 'TP1', 'TP2', 'TP3_TRAILING', 'STOP_LOSS', 'EXPIRED_SESSION', 'MANUAL'
    new_stage: str = None
):
    """Acik bir pozisyondan kademeli veya tam cikis yapar."""
    demo_mode = os.getenv("DEMO_MODE", "True").strip().lower() == "true"
    mode_text = " (Simule)" if demo_mode else " (GERCEK)"

    conn = await database.get_async_db_connection()
    try:
        async with conn.execute("SELECT * FROM open_positions WHERE id = ?", (pos_id,)) as cursor:
            pos = await cursor.fetchone()
            if not pos:
                return

        entry_price = pos["entry_price"]
        curr_qty = pos["current_quantity"]
        initial_qty = pos["initial_quantity"]
        strategy = pos["strategy"]

        sell_qty = min(curr_qty, sell_quantity)
        if sell_qty <= 0:
            return

        total_gain = round(sell_qty * current_price, 2)
        cost_basis = round(sell_qty * entry_price, 2)
        realized_pnl = total_gain - cost_basis
        pnl_pct = ((current_price - entry_price) / entry_price * 100) if entry_price > 0 else 0.0

        remaining_qty = curr_qty - sell_qty
        is_fully_closed = (remaining_qty <= 1e-8) or (close_type in ['TP3_TRAILING', 'STOP_LOSS', 'EXPIRED_SESSION', 'MANUAL'])

        # 1. Portfoy TRY Bakiye Artisi
        async with conn.execute("SELECT quantity FROM portfolio WHERE ticker = 'TRY'") as cursor:
            try_row = await cursor.fetchone()
            cash = try_row["quantity"] if try_row else 0.0
        await conn.execute("UPDATE portfolio SET quantity = ? WHERE ticker = 'TRY'", (cash + total_gain,))

        # 2. Portfoy Hisse Guncellemesi
        if is_fully_closed:
            await conn.execute("DELETE FROM portfolio WHERE ticker = ?", (ticker,))
        else:
            await conn.execute("UPDATE portfolio SET quantity = ? WHERE ticker = ?", (remaining_qty, ticker))

        # 3. Trades Tablosuna Kaydet
        trade_reason = f"[{strategy.upper()} - {close_type}] Kar/Zarar: %{pnl_pct:.2f} ({realized_pnl:+.2f} TL)"
        await conn.execute(
            "INSERT INTO trades (ticker, action, price, quantity, total_value, reasoning) VALUES (?, 'SAT', ?, ?, ?, ?)",
            (ticker, current_price, sell_qty, total_gain, trade_reason)
        )

        # 4. Open Positions Guncellemesi
        if is_fully_closed:
            await conn.execute("""
                UPDATE open_positions
                SET current_quantity = 0, status = 'CLOSED', stage = 'CLOSED',
                    close_time = datetime('now'), close_price = ?,
                    realized_pnl = realized_pnl + ?
                WHERE id = ?
            """, (current_price, realized_pnl, pos_id))
        else:
            stage_to_set = new_stage or pos["stage"]
            # Kademeli cikista TP1 gelince SL basabas seviyesine cekilir
            new_sl = entry_price if stage_to_set == "TP1_HIT" else pos["sl"]
            await conn.execute("""
                UPDATE open_positions
                SET current_quantity = ?, stage = ?, sl = ?,
                    realized_pnl = realized_pnl + ?
                WHERE id = ?
            """, (remaining_qty, stage_to_set, new_sl, realized_pnl, pos_id))

        await conn.commit()

        # 5. Telegram Bildirimi
        emoji = "🎯" if realized_pnl >= 0 else "🛑"
        close_title = {
            "TP1": "TP1 HEDEFI GERCEKLESTI (%40 CIKIS)",
            "TP2": "TP2 HEDEFI GERCEKLESTI (%40 CIKIS)",
            "TP3_TRAILING": "TRAILING STOP ILE TAM CIKIS",
            "STOP_LOSS": "STOP-LOSS TETIKLENDI (ZARAR KES)",
            "EXPIRED_SESSION": "SEANS KAPANISI VADE DOLUMU",
            "MANUAL": "MANUEL POZISYON KAPATMA"
        }.get(close_type, close_type)

        msg = (
            f"{emoji} <b>{close_title}{mode_text}</b>\n\n"
            f"📌 <b>Hisse:</b> #{ticker}\n"
            f"💵 <b>Giris:</b> {entry_price:.2f} TL ➡️ <b>Cikis:</b> {current_price:.2f} TL\n"
            f"📊 <b>Getiri:</b> %{pnl_pct:+.2f} ({realized_pnl:+.2f} TL)\n"
            f"📦 <b>Satilan Lot:</b> {sell_qty:.0f} | <b>Kalan Lot:</b> {max(0, remaining_qty):.0f}\n"
            f"💰 <b>Hesaba Gecen:</b> {total_gain:.2f} TL"
        )
        if not is_fully_closed and new_stage == "TP1_HIT":
            msg += f"\n🛡️ <i>Stop-Loss basabas noktasi olan {entry_price:.2f} TL seviyesine cekildi!</i>"

        await asyncio.to_thread(telegram_utils.send_telegram_message, msg)

    finally:
        await conn.close()


async def evaluate_open_positions():
    """
    Periyodik olarak calisir. Acik pozisyonlarin TP/SL, Trailing Stop ve Seans Sonu durumlarini denetler.
    """
    conn = await database.get_async_db_connection()
    try:
        async with conn.execute("SELECT * FROM open_positions WHERE status = 'OPEN'") as cursor:
            positions = await cursor.fetchall()

        if not positions:
            return

        tz = pytz.timezone("Europe/Istanbul")
        now = datetime.datetime.now(tz)
        is_weekday = now.weekday() < 5
        is_session_end = is_weekday and (now.hour == 17 and now.minute >= 50 or now.hour >= 18)

        for p in positions:
            pos_id = p["id"]
            ticker = p["ticker"]
            entry_price = p["entry_price"]
            strategy = p["strategy"]
            stage = p["stage"]
            curr_qty = p["current_quantity"]
            initial_qty = p["initial_quantity"]
            tp1 = p["tp1"]
            tp2 = p["tp2"]
            sl = p["sl"]
            trailing_sl = p["trailing_sl"]
            highest_price = p["highest_price"] or entry_price
            expire_time_str = p["expire_time"]

            current_price = await market_data.get_stock_price(ticker)
            if current_price is None or current_price <= 0:
                continue

            # En yuksek fiyat guncelleme
            if current_price > highest_price:
                highest_price = current_price
                # Trailing stop guncellemesi (Zirveden %2 asagisi)
                trailing_sl = round(highest_price * 0.98, 2)
                await conn.execute(
                    "UPDATE open_positions SET highest_price = ?, trailing_sl = ? WHERE id = ?",
                    (highest_price, trailing_sl, pos_id)
                )
                await conn.commit()

            # Vade sonu kontrolu
            is_expired = False
            if expire_time_str:
                try:
                    exp_dt = datetime.datetime.strptime(expire_time_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=tz)
                    if now >= exp_dt:
                        is_expired = True
                except Exception:
                    pass

            # --- STRATEJI 1: KADEMELI (SCALING) ---
            if strategy == "scaling":
                # 1. Stop-Loss
                if current_price <= sl:
                    logger.info(f"[{ticker}] Scaling SL tetiklendi -> Fiyat: {current_price}, SL: {sl}")
                    await close_position_partial_or_full(pos_id, ticker, curr_qty, current_price, "STOP_LOSS")
                    continue

                # 2. TP1 Kontrolu (Ilk %40 satis)
                if stage == "STAGE_INITIAL" and tp1 and current_price >= tp1:
                    sell_lot = math.floor(initial_qty * 0.40)
                    if sell_lot >= 1:
                        logger.info(f"[{ticker}] TP1 ulasildi -> %40 satiliyor")
                        await close_position_partial_or_full(pos_id, ticker, sell_lot, current_price, "TP1", new_stage="TP1_HIT")
                    continue

                # 3. TP2 Kontrolu (Ikinci %40 satis)
                if stage == "TP1_HIT" and tp2 and current_price >= tp2:
                    sell_lot = math.floor(initial_qty * 0.40)
                    if sell_lot >= 1:
                        logger.info(f"[{ticker}] TP2 ulasildi -> %40 satiliyor, Trailing Stop baslatildi")
                        await close_position_partial_or_full(pos_id, ticker, sell_lot, current_price, "TP2", new_stage="TP2_HIT")
                    continue

                # 4. TP3 Trailing Stop Kontrolu (Kalan %20)
                if stage == "TP2_HIT" and trailing_sl and current_price <= trailing_sl:
                    logger.info(f"[{ticker}] Trailing Stop tetiklendi -> Kalan %20 satiliyor")
                    await close_position_partial_or_full(pos_id, ticker, curr_qty, current_price, "TP3_TRAILING")
                    continue

            # --- STRATEJI 2: SWING TRADE ---
            elif strategy == "swing":
                if current_price <= sl:
                    logger.info(f"[{ticker}] Swing SL tetiklendi -> Fiyat: {current_price}, SL: {sl}")
                    await close_position_partial_or_full(pos_id, ticker, curr_qty, current_price, "STOP_LOSS")
                    continue
                elif tp1 and current_price >= tp1:
                    logger.info(f"[{ticker}] Swing TP ulasildi -> Tamami satiliyor")
                    await close_position_partial_or_full(pos_id, ticker, curr_qty, current_price, "TP1")
                    continue

            # --- STRATEJI 3: MOMENTUM (GUN ICI) ---
            elif strategy == "momentum":
                if current_price <= sl:
                    logger.info(f"[{ticker}] Momentum SL tetiklendi -> Fiyat: {current_price}, SL: {sl}")
                    await close_position_partial_or_full(pos_id, ticker, curr_qty, current_price, "STOP_LOSS")
                    continue
                elif tp1 and current_price >= tp1:
                    logger.info(f"[{ticker}] Momentum TP ulasildi -> Tamami satiliyor")
                    await close_position_partial_or_full(pos_id, ticker, curr_qty, current_price, "TP1")
                    continue

            # --- SEANS KAPANISI VE VADE KONTROLU (17:50 BIST) ---
            if (strategy == "momentum" and is_session_end) or is_expired:
                logger.info(f"[{ticker}] Seans sonu/vade dolumu nedeniyle pozisyon kapatiliyor.")
                await close_position_partial_or_full(pos_id, ticker, curr_qty, current_price, "EXPIRED_SESSION")
                continue

    except Exception as e:
        logger.error(f"Acik pozisyonlar denetlenirken hata: {str(e)}")
    finally:
        await conn.close()


async def process_trade_signal(ticker: str, action: str, price: float, quantity: float, reasoning: str = None) -> dict:
    """Webhook veya genel API cagrilari icin uyumluluk katmani."""
    clean_ticker = ticker.upper().replace(".IS", "")
    if action == "AL":
        # Varsayilan strateji ile ac
        strat_info = {
            "strategy": "scaling",
            "tp1": round(price * 1.03, 2),
            "tp2": round(price * 1.06, 2),
            "tp3": round(price * 1.10, 2),
            "sl": round(price * 0.97, 2),
            "expected_hold": "1-3 Gun"
        }
        return await open_strategy_position(clean_ticker, price, strat_info, reasoning)
    else:
        # SAT sinyali geldiyse acik pozisyonu tamamen kapat
        conn = await database.get_async_db_connection()
        try:
            async with conn.execute("SELECT id, current_quantity FROM open_positions WHERE ticker = ? AND status = 'OPEN'", (clean_ticker,)) as cursor:
                pos = await cursor.fetchone()
                if pos:
                    await close_position_partial_or_full(pos["id"], clean_ticker, pos["current_quantity"], price, "MANUAL")
                    return {"status": "success", "message": f"{clean_ticker} pozisyonu kapatildi."}
                else:
                    return {"status": "rejected", "message": f"{clean_ticker} icin acik pozisyon bulunamadi."}
        finally:
            await conn.close()