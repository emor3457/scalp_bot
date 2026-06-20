import os
import sys
import argparse
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime

# Proje kok dizinini path'e ekleyelim ki auto_analyst modülünü de içe aktarabilelim
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    if len(df) < 50:
        return df

    # 1. EMA
    df['EMA9'] = df['Close'].ewm(span=9, adjust=False).mean()
    df['EMA21'] = df['Close'].ewm(span=21, adjust=False).mean()
    df['EMA50'] = df['Close'].ewm(span=50, adjust=False).mean()

    # 2. RSI
    delta = df['Close'].diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    
    avg_gain = gain.ewm(alpha=1/14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/14, adjust=False).mean()
    
    rs = avg_gain / np.where(avg_loss == 0, 1e-10, avg_loss)
    df['RSI'] = 100 - (100 / (1 + rs))

    # 3. MACD
    ema12 = df['Close'].ewm(span=12, adjust=False).mean()
    ema26 = df['Close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = ema12 - ema26
    df['MACD_Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
    df['MACD_Hist'] = df['MACD'] - df['MACD_Signal']

    # 4. Bollinger Bands
    df['BB_Mid'] = df['Close'].rolling(window=20).mean()
    df['BB_Std'] = df['Close'].rolling(window=20).std()
    df['BB_Upper'] = df['BB_Mid'] + (2 * df['BB_Std'])
    df['BB_Lower'] = df['BB_Mid'] - (2 * df['BB_Std'])

    # 5. Volume SMA
    df['Vol_SMA20'] = df['Volume'].rolling(window=20).mean()

    return df

def run_backtest(ticker: str, period: str, initial_capital: float, max_trade_allocation: float):
    yahoo_ticker = f"{ticker}.IS"
    print(f"\n[+] {yahoo_ticker} için veriler indiriliyor (Süre: {period}, Aralık: 5m)...")
    
    stock = yf.Ticker(yahoo_ticker)
    df = stock.history(period=period, interval="5m")
    
    if df.empty or len(df) < 50:
        print(f"[-] Hata: {ticker} için yetersiz veri indirildi. Satır sayısı: {len(df)}")
        return
        
    print(f"[+] Veriler indirildi. Satır sayısı: {len(df)}")
    df = calculate_indicators(df)
    
    # Simülasyon değişkenleri
    capital = initial_capital
    portfolio_value = initial_capital
    held_qty = 0.0
    entry_price = 0.0
    trades = []
    
    # Performans takibi
    peak_portfolio_value = initial_capital
    max_drawdown = 0.0
    
    # 50. mumdan itibaren simülasyona başla (indikatörlerin oturması için)
    for i in range(50, len(df)):
        curr = df.iloc[i]
        prev = df.iloc[i-1]
        timestamp = df.index[i]
        
        close = float(curr['Close'])
        volume = float(curr['Volume'])
        
        # Göstergeler
        ema9, ema21, ema50 = float(curr['EMA9']), float(curr['EMA21']), float(curr['EMA50'])
        rsi = float(curr['RSI'])
        macd, macd_sig = float(curr['MACD']), float(curr['MACD_Signal'])
        bb_upper, bb_lower = float(curr['BB_Upper']), float(curr['BB_Lower'])
        vol_sma20 = float(curr['Vol_SMA20']) if curr['Vol_SMA20'] > 0 else 1.0
        
        prev_macd, prev_macd_sig = float(prev['MACD']), float(prev['MACD_Signal'])
        prev_rsi = float(prev['RSI'])
        
        # Durum Analizleri
        is_bullish_trend = close > ema50 and ema9 > ema21
        is_bearish_trend = close < ema50 or ema9 < ema21
        vol_ratio = volume / vol_sma20
        
        # Kesişimler
        macd_crossed_above = prev_macd <= prev_macd_sig and macd > macd_sig
        macd_crossed_below = prev_macd >= prev_macd_sig and macd < macd_sig
        rsi_crossed_above_30 = prev_rsi <= 30 and rsi > 30
        rsi_crossed_below_70 = prev_rsi >= 70 and rsi < 70
        touches_lower = close <= bb_lower * 1.003
        touches_upper = close >= bb_upper * 0.997
        
        # ALIM KARARI
        is_technical_buy = is_bullish_trend and (macd_crossed_above or rsi_crossed_above_30 or (touches_lower and rsi < 40))
        is_flow_buy = vol_ratio >= 1.5 and rsi > 50
        
        # PORTFÖY DEĞERİNİ GÜNCELLE
        current_portfolio_value = capital + (held_qty * close)
        if current_portfolio_value > peak_portfolio_value:
            peak_portfolio_value = current_portfolio_value
        
        drawdown = (peak_portfolio_value - current_portfolio_value) / peak_portfolio_value * 100
        if drawdown > max_drawdown:
            max_drawdown = drawdown

        # İşlem simülasyonu
        if held_qty == 0:
            # Alım koşulu kontrol et
            if is_technical_buy and is_flow_buy:
                target_amount = min(capital * 0.1, max_trade_allocation)
                if target_amount < 500.0:
                    target_amount = min(capital, 500.0)
                
                qty_to_buy = int(target_amount / close)
                if qty_to_buy >= 1:
                    buy_cost = qty_to_buy * close
                    capital -= buy_cost
                    held_qty = qty_to_buy
                    entry_price = close
                    
                    trades.append({
                        "entry_time": timestamp,
                        "entry_price": entry_price,
                        "qty": held_qty,
                        "type": "AL",
                        "reason": f"Hacim Patlaması ({vol_ratio:.1f}x) + Trend"
                    })
                    print(f"[{timestamp}] ALIM: {qty_to_buy} Lot @ {close:.2f} TL | Maliyet: {buy_cost:.2f} TL | Kalan Nakit: {capital:.2f} TL")
        else:
            # Satım koşulu kontrol et
            if is_bearish_trend or macd_crossed_below or rsi_crossed_below_70 or touches_upper:
                sell_revenue = held_qty * close
                capital += sell_revenue
                
                pnl = (close - entry_price) * held_qty
                pnl_pct = ((close - entry_price) / entry_price) * 100
                
                trades[-1].update({
                    "exit_time": timestamp,
                    "exit_price": close,
                    "pnl": pnl,
                    "pnl_pct": pnl_pct,
                    "exit_reason": "Trend Dönüşü" if is_bearish_trend else ("MACD Negatif" if macd_crossed_below else "RSI Aşırı Satım" if rsi_crossed_below_70 else "Bollinger Üst")
                })
                print(f"[{timestamp}] SATIM: {held_qty} Lot @ {close:.2f} TL | Gelir: {sell_revenue:.2f} TL | Kâr/Zarar: {pnl:+.2f} TL ({pnl_pct:+.2f}%)")
                
                held_qty = 0.0
                entry_price = 0.0

    # Final Değerleme
    final_close = float(df.iloc[-1]['Close'])
    final_portfolio_value = capital + (held_qty * final_close)
    total_return = ((final_portfolio_value - initial_capital) / initial_capital) * 100
    
    # İstatistikler
    total_trades = len(trades)
    completed_trades = [t for t in trades if "pnl" in t]
    winning_trades = [t for t in completed_trades if t["pnl"] > 0]
    losing_trades = [t for t in completed_trades if t["pnl"] <= 0]
    
    win_rate = (len(winning_trades) / len(completed_trades) * 100) if completed_trades else 0.0
    
    total_gains = sum([t["pnl"] for t in winning_trades])
    total_losses = sum([abs(t["pnl"]) for t in losing_trades])
    profit_factor = (total_gains / total_losses) if total_losses > 0 else (total_gains if total_gains > 0 else 1.0)
    
    print("\n" + "="*50)
    print(f"=== {ticker} GERIYE DONUK TEST (BACKTEST) SONUCLARI ===")
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

    # JSON Serileştirme için Timestamps string'e dönüştürülüyor
    serialized_trades = []
    for t in trades:
        st = t.copy()
        if "entry_time" in st and hasattr(st["entry_time"], "strftime"):
            st["entry_time"] = st["entry_time"].strftime("%Y-%m-%d %H:%M")
        if "exit_time" in st and hasattr(st["exit_time"], "strftime"):
            st["exit_time"] = st["exit_time"].strftime("%Y-%m-%d %H:%M")
        serialized_trades.append(st)

    return {
        "status": "success",
        "ticker": ticker,
        "period": period,
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
    parser = argparse.ArgumentParser(description="BIST Scalper Bot Strateji Backtest Aracı")
    parser.add_argument("--ticker", type=str, default="THYAO", help="BIST Hisse senedi kodu (örn: THYAO, EREGL)")
    parser.add_argument("--period", type=str, default="1mo", choices=["5d", "1mo", "3mo", "60d"], help="Analiz edilecek geçmiş veri süresi")
    parser.add_argument("--capital", type=float, default=500000.0, help="Sanal başlangıç sermayesi (TL)")
    parser.add_argument("--max-alloc", type=float, default=10000.0, help="İşlem başına maksimum ayrılacak bütçe (TL)")
    
    args = parser.parse_args()
    
    run_backtest(
        ticker=args.ticker.upper(),
        period=args.period,
        initial_capital=args.capital,
        max_trade_allocation=args.max_alloc
    )
