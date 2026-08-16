import os
import sys
import argparse
import asyncio
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime

# Proje kok dizinini path'e ekleyelim ki auto_analyst modülünü de içe aktarabilelim
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from auto_analyst import calculate_technical_score, calculate_fundamental_score

async def run_backtest(ticker: str, period: str, initial_capital: float, max_trade_allocation: float, news_score: float = None, fill_mode: str = "next_open"):
    # Icra modu:
    #   next_open    (varsayilan, gercekci) — sinyal bar kapanisinda uretilir, icra bir sonraki barin
    #                 acilis fiyatindan yapilir. Lookahead bias yoktur.
    #   signal_close (eski/iyimser)         — sinyal uretildigi barin kapanis fiyatindan aninda icra
    #                 edilir. Sonuclari iyimser sisebilecegi icin karsilastirma amaclidir.
    if fill_mode not in ("next_open", "signal_close"):
        raise ValueError(f"Gecersiz fill_mode: {fill_mode}. Beklenen: 'next_open' veya 'signal_close'")

    yahoo_ticker = f"{ticker}.IS"
    print(f"\n[+] {yahoo_ticker} için veriler indiriliyor...")
    print(f"[+] Icra modu: {fill_mode} (" + ("sinyal kapanisinda aninda" if fill_mode == "signal_close" else "sonraki bar acilisinda") + ")")
    
    # 1. Haber skoru: Tarihsel haber verisi olmadığı için backtest boyunca tek bir değer kullanılır.
    #    Varsayılan NÖTR (50.0) — bugünkü canlı haber duyarlılığı geçmişe uygulanmaz (bias).
    #    Bugünkü haber ortamını senaryo olarak test etmek için news_score parametresi verilebilir.
    if news_score is None:
        news_score = 50.0
        news_mode = "neutral"
        print("[+] Haber skoru: NÖTR (50.0). Canlı haber skoru tarihsel backtest'e uygulanmaz.")
        print("    Bugünkü haber ortamını senaryo olarak test etmek için --news <0-100> kullanın.")
    else:
        news_mode = "scenario"
        news_score = max(0.0, min(100.0, float(news_score)))
        print(f"[+] Haber skoru senaryosu: {news_score:.1f}/100 (kullanıcı tanımlı, backtest boyunca sabit)")

    # 2. Periyotlara göre veri aralıklarını belirle (EMA göstergelerinin ısınması için günlük veri daha uzun tutulur)
    if period == "5d":
        hourly_period = "5d"
        daily_period = "6mo"
    elif period == "1mo":
        hourly_period = "1mo"
        daily_period = "6mo"
    elif period == "60d" or period == "3mo":
        hourly_period = "3mo"
        daily_period = "1y"
    else:
        hourly_period = "1mo"
        daily_period = "6mo"

    stock = yf.Ticker(yahoo_ticker)
    
    # Verileri ve info'yu eşzamanlı indir
    df_hourly, df_daily, info = await asyncio.gather(
        asyncio.to_thread(stock.history, period=hourly_period, interval="1h"),
        asyncio.to_thread(stock.history, period=daily_period, interval="1d"),
        asyncio.to_thread(lambda: stock.info)
    )

    if df_hourly.empty or len(df_hourly) < 20:
        print(f"[-] Hata: {ticker} için yetersiz saatlik veri indirildi. Satır sayısı: {len(df_hourly)}")
        return None

    if df_daily.empty or len(df_daily) < 50:
        print(f"[-] Hata: {ticker} için yetersiz günlük veri indirildi. Satır sayısı: {len(df_daily)}")
        return None

    print(f"[+] Veriler indirildi. Günlük bar: {len(df_daily)}, Saatlik bar: {len(df_hourly)}")

    # Simülasyon değişkenleri
    capital = initial_capital
    held_qty = 0.0
    entry_price = 0.0
    tp1_hit = False
    tp2_hit = False
    
    trades = []       # Tamamlanmış/Bölünmüş tüm işlemler
    held_trades = []  # Açık olan pozisyon

    # next_open modunda: önceki barın kapanışında üretilen sinyal bu barın açılışında icra edilir
    pending_signal = None  # (action, sell_qty, reason)

    # Performans takibi
    peak_portfolio_value = initial_capital
    max_drawdown = 0.0

    # Adım adım saatlik veride ilerle
    for i in range(10, len(df_hourly)):
        current_time = df_hourly.index[i]
        curr_bar = df_hourly.iloc[i]
        bar_open = float(curr_bar['Open'])
        close = float(curr_bar['Close'])

        # ------------------------------------------------------------------
        # A) BEKLEYEN SINYALIN ICRA EDILMESI (yalnizca next_open modu)
        #    Sinyal bir onceki barin kapanisinda uretilir, bu barin AÇILIŞ
        #    fiyatindan dolur. Boylece 'sinyal goruldugu anda ayni kapanistan
        #    icra' seklindeki lookahead bias ortadan kalkar.
        # ------------------------------------------------------------------
        if pending_signal is not None:
            sig_action, sig_qty, sig_reason = pending_signal
            pending_signal = None

            if sig_action == "AL" and held_qty == 0 and bar_open > 0:
                # Tahsis buyuklugu icra anindaki acilis fiyatina gore yeniden hesaplanir
                target_amount = min(capital * 0.15, max_trade_allocation)
                if target_amount < 500.0:
                    target_amount = min(capital, 500.0)
                qty_to_buy = int(target_amount / bar_open)
                if qty_to_buy >= 1:
                    buy_cost = qty_to_buy * bar_open
                    capital -= buy_cost
                    held_qty = float(qty_to_buy)
                    entry_price = bar_open
                    tp1_hit = False
                    tp2_hit = False
                    held_trades.append({
                        "entry_time": current_time,
                        "entry_price": entry_price,
                        "qty": held_qty,
                        "type": "AL",
                        "reason": sig_reason
                    })
                    print(f"[{current_time}] ALIM: {qty_to_buy} Lot @ {bar_open:.2f} TL (acilis) | Kalan Nakit: {capital:.2f} TL")

            elif sig_action in ("SAT_ALL", "SAT_PARTIAL") and held_qty > 0:
                sell_qty = min(sig_qty, held_qty)
                if sell_qty >= 1:
                    sell_revenue = sell_qty * bar_open
                    capital += sell_revenue

                    p_trade = held_trades[0]
                    pnl = (bar_open - p_trade["entry_price"]) * sell_qty
                    pnl_pct = ((bar_open - p_trade["entry_price"]) / p_trade["entry_price"]) * 100

                    trades.append({
                        "entry_time": p_trade["entry_time"],
                        "exit_time": current_time,
                        "entry_price": p_trade["entry_price"],
                        "exit_price": bar_open,
                        "qty": sell_qty,
                        "type": "AL",
                        "pnl": pnl,
                        "pnl_pct": pnl_pct,
                        "reason": p_trade["reason"],
                        "exit_reason": sig_reason
                    })
                    p_trade["qty"] -= sell_qty
                    held_qty -= sell_qty
                    if sig_action == "SAT_ALL" or held_qty < 1:
                        held_qty = 0.0
                        entry_price = 0.0
                        held_trades = []
                    print(f"[{current_time}] SATIM: {sell_qty} Lot @ {bar_open:.2f} TL (acilis) | Kâr/Zarar: {pnl:+.2f} TL ({pnl_pct:+.2f}%) | Neden: {sig_reason} | Kalan: {held_qty} Lot")

        # 3. Lookahead bias (geleceği görme) olmaksızın günlük slice oluştur
        # Bugünün o saate kadar olan saatlik barlarını birleştirip bugünlük bar oluştur
        today_hourly = df_hourly[(df_hourly.index.date == current_time.date()) & (df_hourly.index <= current_time)]
        if not today_hourly.empty:
            today_bar = pd.DataFrame([{
                'Open': today_hourly['Open'].iloc[0],
                'High': today_hourly['High'].max(),
                'Low': today_hourly['Low'].min(),
                'Close': today_hourly['Close'].iloc[-1],
                'Volume': today_hourly['Volume'].sum(),
            }], index=[pd.Timestamp(current_time.date())])
            df_daily_slice = pd.concat([df_daily[df_daily.index.date < current_time.date()], today_bar])
        else:
            df_daily_slice = df_daily[df_daily.index.date < current_time.date()]

        # 4. Saatlik slice oluştur
        df_hourly_slice = df_hourly[df_hourly.index <= current_time]

        # Göstergeleri ve skorları hesapla
        try:
            tech_score, tech_details = calculate_technical_score(df_daily_slice, df_hourly_slice)
            dist_from_52w_low = tech_details.get("dist_from_52w_low", 50.0)
            fund_score = calculate_fundamental_score(info, dist_from_52w_low)
        except Exception as e:
            continue

        # Kompozit Skor (Teknik %50, Temel %25, Haber %25)
        composite = (tech_score * 0.50) + (fund_score * 0.25) + (news_score * 0.25)

        # Portföy Değerleme
        current_portfolio_value = capital + (held_qty * close)
        if current_portfolio_value > peak_portfolio_value:
            peak_portfolio_value = current_portfolio_value
        
        drawdown = (peak_portfolio_value - current_portfolio_value) / peak_portfolio_value * 100
        if drawdown > max_drawdown:
            max_drawdown = drawdown

        # ------------------------------------------------------------------
        # B) SINYAL URETIMI (bar kapanisi baz alinir)
        #    next_open: sinyal uretilir, icra sonraki turda (barin acilisinda) yapilir
        #    signal_close: sinyal aninda kapanis fiyatindan icra edilir (eski davranis)
        # ------------------------------------------------------------------
        if held_qty == 0:
            # ALIM KOŞULU (Skor >= 65 ve Haber >= 30)
            if composite >= 65 and news_score >= 30:
                reason = f"Kompozit Skor: {composite:.1f}/100 (Teknik: {tech_score:.1f}, Temel: {fund_score:.1f})"
                if fill_mode == "next_open":
                    pending_signal = ("AL", 0.0, reason)
                else:
                    target_amount = min(capital * 0.15, max_trade_allocation)
                    if target_amount < 500.0:
                        target_amount = min(capital, 500.0)

                    qty_to_buy = int(target_amount / close)
                    if qty_to_buy >= 1:
                        buy_cost = qty_to_buy * close
                        capital -= buy_cost
                        held_qty = float(qty_to_buy)
                        entry_price = close
                        tp1_hit = False
                        tp2_hit = False

                        held_trades.append({
                            "entry_time": current_time,
                            "entry_price": entry_price,
                            "qty": held_qty,
                            "type": "AL",
                            "reason": reason
                        })
                        print(f"[{current_time}] ALIM: {qty_to_buy} Lot @ {close:.2f} TL | Kompozit: {composite:.1f} | Kalan Nakit: {capital:.2f} TL")
        else:
            # SATIM KOŞULLARI (Kısa Vadeli TP/SL Seviyeleri) — kapanış fiyatıyla değerlendirilir
            current_return_pct = (close - entry_price) / entry_price
            
            action = None
            sell_qty = 0.0
            exit_reason = ""

            # 1. Stop-Loss (-%5)
            if current_return_pct <= -0.05:
                action = "SAT_ALL"
                sell_qty = held_qty
                exit_reason = f"Stop-Loss (-%{abs(current_return_pct*100):.1f})"
            
            # 2. Kar Al - TP3 (+%15)
            elif current_return_pct >= 0.15:
                action = "SAT_ALL"
                sell_qty = held_qty
                exit_reason = f"Kar Al - TP3 (+%{current_return_pct*100:.1f})"
            
            # 3. Kar Al - TP2 (+%10)
            elif current_return_pct >= 0.10 and not tp2_hit:
                action = "SAT_PARTIAL"
                sell_qty = float(int(held_qty * 0.4))
                if sell_qty >= 1.0:
                    exit_reason = f"Kar Al - TP2 (+%{current_return_pct*100:.1f})"
                    tp2_hit = True
                    tp1_hit = True
                else:
                    action = None

            # 4. Kar Al - TP1 (+%5)
            elif current_return_pct >= 0.05 and not tp1_hit:
                action = "SAT_PARTIAL"
                sell_qty = float(int(held_qty * 0.4))
                if sell_qty >= 1.0:
                    exit_reason = f"Kar Al - TP1 (+%{current_return_pct*100:.1f})"
                    tp1_hit = True
                else:
                    action = None

            # 5. Skor Düşüşü (Skor <= 30)
            elif composite <= 30 and current_return_pct > -0.02:
                action = "SAT_ALL"
                sell_qty = held_qty
                exit_reason = f"Zayıf Skor (Kompozit: {composite:.1f})"

            if action is not None and fill_mode == "next_open":
                # Sinyal uretildi; icra bir sonraki barin acilisinda yapilacak
                pending_signal = (action, sell_qty, exit_reason)

            elif action == "SAT_ALL":
                sell_revenue = sell_qty * close
                capital += sell_revenue
                
                p_trade = held_trades[0]
                pnl = (close - p_trade["entry_price"]) * sell_qty
                pnl_pct = ((close - p_trade["entry_price"]) / p_trade["entry_price"]) * 100
                
                trades.append({
                    "entry_time": p_trade["entry_time"],
                    "exit_time": current_time,
                    "entry_price": p_trade["entry_price"],
                    "exit_price": close,
                    "qty": p_trade["qty"],
                    "type": "AL",
                    "pnl": pnl,
                    "pnl_pct": pnl_pct,
                    "reason": p_trade["reason"],
                    "exit_reason": exit_reason
                })
                print(f"[{current_time}] SATIM (HEPSİ): {held_qty} Lot @ {close:.2f} TL | Kâr/Zarar: {pnl:+.2f} TL ({pnl_pct:+.2f}%) | Neden: {exit_reason}")
                
                held_qty = 0.0
                entry_price = 0.0
                held_trades = []

            elif action == "SAT_PARTIAL":
                sell_revenue = sell_qty * close
                capital += sell_revenue
                
                p_trade = held_trades[0]
                pnl = (close - p_trade["entry_price"]) * sell_qty
                pnl_pct = ((close - p_trade["entry_price"]) / p_trade["entry_price"]) * 100
                
                trades.append({
                    "entry_time": p_trade["entry_time"],
                    "exit_time": current_time,
                    "entry_price": p_trade["entry_price"],
                    "exit_price": close,
                    "qty": sell_qty,
                    "type": "AL",
                    "pnl": pnl,
                    "pnl_pct": pnl_pct,
                    "reason": p_trade["reason"],
                    "exit_reason": exit_reason
                })
                
                p_trade["qty"] -= sell_qty
                held_qty -= sell_qty
                print(f"[{current_time}] SATIM (KISMİ): {sell_qty} Lot @ {close:.2f} TL | Kâr/Zarar: {pnl:+.2f} TL ({pnl_pct:+.2f}%) | Neden: {exit_reason} | Kalan: {held_qty} Lot")

    # Son durum değerlemesi ve açık pozisyonu listeye ekleme
    final_close = float(df_hourly.iloc[-1]['Close'])
    final_portfolio_value = capital + (held_qty * final_close)
    total_return = ((final_portfolio_value - initial_capital) / initial_capital) * 100

    if held_qty > 0:
        p_trade = held_trades[0]
        trades.append({
            "entry_time": p_trade["entry_time"],
            "exit_time": None,
            "entry_price": p_trade["entry_price"],
            "exit_price": None,
            "qty": p_trade["qty"],
            "type": "AL",
            "reason": p_trade["reason"],
            "exit_reason": "Açık Pozisyon"
        })

    # İstatistikleri hesapla
    total_trades = len(trades)
    completed_trades = [t for t in trades if "pnl" in t]
    winning_trades = [t for t in completed_trades if t["pnl"] > 0]
    losing_trades = [t for t in completed_trades if t["pnl"] <= 0]
    
    win_rate = (len(winning_trades) / len(completed_trades) * 100) if completed_trades else 0.0
    total_gains = sum([t["pnl"] for t in winning_trades])
    total_losses = sum([abs(t["pnl"]) for t in losing_trades])
    profit_factor = (total_gains / total_losses) if total_losses > 0 else (total_gains if total_gains > 0 else 1.0)

    print("\n" + "="*50)
    print(f"=== {ticker} YENİ YATIRIM STRATEJİSİ BACKTEST SONUÇLARI ===")
    print("="*50)
    print(f"Başlangıç Sermayesi : {initial_capital:,.2f} TL")
    print(f"Bitiş Sermayesi     : {final_portfolio_value:,.2f} TL")
    print(f"Toplam Getiri (%)   : {total_return:+.2f}%")
    print(f"Toplam Net Kâr/Zarar: {final_portfolio_value - initial_capital:+.2f} TL")
    print(f"Maksimum Drawdown   : -{max_drawdown:.2f}%")
    print("-"*50)
    print(f"Toplam İşlem Sayısı : {total_trades}")
    print(f"Tamamlanan İşlemler : {len(completed_trades)}")
    print(f"Kazanan İşlem Sayısı: {len(winning_trades)}")
    print(f"Kaybeden İşlem Sayısı: {len(losing_trades)}")
    print(f"Kazanma Oranı (Win%): {win_rate:.2f}%")
    print(f"Kar Faktörü (P.F.)  : {profit_factor:.2f}")
    print("="*50)

    # JSON Serileştirme için tarihleri string'e çevir
    serialized_trades = []
    for t in trades:
        st = t.copy()
        if "entry_time" in st and hasattr(st["entry_time"], "strftime"):
            st["entry_time"] = st["entry_time"].strftime("%Y-%m-%d %H:%M")
        if "exit_time" in st and st["exit_time"] is not None and hasattr(st["exit_time"], "strftime"):
            st["exit_time"] = st["exit_time"].strftime("%Y-%m-%d %H:%M")
        serialized_trades.append(st)

    return {
        "status": "success",
        "ticker": ticker,
        "period": period,
        "fill_mode": fill_mode,
        "news_score": news_score,
        "news_mode": news_mode,
        "initial_capital": initial_capital,
        "final_portfolio_value": final_portfolio_value,
        "total_return": total_return,
        "net_profit": final_portfolio_value - initial_capital,
        "max_drawdown": max_drawdown,
        "total_trades": total_trades,
        "completed_trades_count": len(completed_trades),
        "winning_trades_count": len(winning_trades),
        "losing_trades_count": len(losing_trades),
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "trades": serialized_trades
    }

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="BIST Yatırım Botu Geriye Dönük Test Aracı")
    parser.add_argument("--ticker", type=str, default="THYAO", help="BIST Hisse kodu (örn: THYAO, EREGL)")
    parser.add_argument("--period", type=str, default="1mo", choices=["5d", "1mo", "3mo", "60d"], help="Analiz süresi")
    parser.add_argument("--capital", type=float, default=500000.0, help="Başlangıç sermayesi (TL)")
    parser.add_argument("--max-alloc", type=float, default=10000.0, help="İşlem başına maksimum tahsis (TL)")
    parser.add_argument("--news", type=float, default=None, help="Haber skoru senaryosu (0-100). Verilmezse nötr 50.0 kullanılır.")
    parser.add_argument("--fill-mode", type=str, default="next_open", choices=["next_open", "signal_close"],
                        help="Icra modu: next_open (sonraki bar acilisi, gercekci) veya signal_close (sinyal kapanisi, iyimser)")
    
    args = parser.parse_args()
    
    asyncio.run(run_backtest(
        ticker=args.ticker.upper(),
        period=args.period,
        initial_capital=args.capital,
        max_trade_allocation=args.max_alloc,
        news_score=args.news,
        fill_mode=args.fill_mode
    ))
