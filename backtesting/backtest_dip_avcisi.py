import yfinance as yf
import pandas as pd
import numpy as np

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).fillna(0)
    loss = (-delta.where(delta < 0, 0)).fillna(0)
    avg_gain = gain.rolling(window=period, min_periods=period).mean()
    avg_loss = loss.rolling(window=period, min_periods=period).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def run_dip_avcisi_backtest(ticker="XU100.IS", period="6mo", interval="1h", initial_capital=500000.0, max_allocation=50000.0):
    print(f"[{ticker}] Veri indiriliyor ({period}, {interval})...")
    df = yf.download(ticker, period=period, interval=interval, progress=False)
    
    if df.empty:
        print("Veri indirilemedi.")
        return

    # Pandas yf returns MultiIndex columns sometimes, depending on version.
    if isinstance(df.columns, pd.MultiIndex):
        df = df.droplevel(1, axis=1)

    df['RSI'] = calculate_rsi(df['Close'], 14)
    
    capital = initial_capital
    held_qty = 0.0
    entry_price = 0.0
    tp1_hit = False
    
    trades = []
    
    print("Backtest basliyor (Dip Avcisi)...")
    
    for i in range(15, len(df)-1): # -1 cünkü next open aliyoruz
        curr_bar = df.iloc[i]
        next_bar = df.iloc[i+1]
        
        close = float(curr_bar['Close'])
        rsi = float(curr_bar['RSI'])
        
        next_open = float(next_bar['Open'])
        current_time = df.index[i]
        next_time = df.index[i+1]
        
        if held_qty == 0:
            if rsi < 30.0:
                # Alim sinyali (next open)
                target_amount = min(capital * 0.15, max_allocation)
                qty_to_buy = int(target_amount / next_open)
                if qty_to_buy >= 1:
                    capital -= qty_to_buy * next_open
                    held_qty = float(qty_to_buy)
                    entry_price = next_open
                    tp1_hit = False
                    
                    trades.append({
                        "entry_time": next_time,
                        "entry_price": entry_price,
                        "qty": held_qty,
                        "type": "AL",
                        "status": "OPEN",
                        "pnl": 0.0
                    })
                    # print(f"[{next_time}] ALIM: {qty_to_buy} Lot @ {entry_price:.2f} TL (RSI: {rsi:.1f})")
        else:
            # Acik pozisyon var, satis kosullari kontrolu
            # Satis islemleri yine bir sonraki acilistan yapilabilir ya da ayni barin kapanisindan 
            # (gercekte limit emir veya stop emir girilirse o fiyattan da eslesebilir)
            # Biz muhafazakar test icin mevcut barin Low/High fiyatini test edip 
            # hedefler gerceklesti mi bakariz. Eger gerceklestiyse hedef fiyattan satilmis sayariz (limit emir).
            
            high = float(curr_bar['High'])
            low = float(curr_bar['Low'])
            
            sl_price = entry_price if tp1_hit else entry_price * 0.97
            tp1_price = entry_price * 1.02
            tp2_price = entry_price * 1.04
            
            action = None
            sell_qty = 0.0
            exit_price = 0.0
            exit_reason = ""
            
            # SL Kontrolu (Low)
            if low <= sl_price:
                action = "SAT_ALL"
                sell_qty = held_qty
                exit_price = sl_price
                exit_reason = "Stop-Loss (veya Basabas)"
                
            # TP2 Kontrolu (High)
            elif tp1_hit and high >= tp2_price:
                action = "SAT_ALL"
                sell_qty = held_qty
                exit_price = tp2_price
                exit_reason = "Kar Al - TP2"
                
            # TP1 Kontrolu (High)
            elif not tp1_hit and high >= tp1_price:
                action = "SAT_PARTIAL"
                sell_qty = held_qty * 0.50
                exit_price = tp1_price
                exit_reason = "Kar Al - TP1"
                tp1_hit = True
                
            if action:
                sell_revenue = sell_qty * exit_price
                capital += sell_revenue
                
                # Update Trade PnL
                trades[-1]["pnl"] += (exit_price - entry_price) * sell_qty
                trades[-1]["exit_time"] = current_time
                trades[-1]["exit_price"] = exit_price
                
                # print(f"[{current_time}] {exit_reason}: {sell_qty} Lot @ {exit_price:.2f} TL")
                
                held_qty -= sell_qty
                if action == "SAT_ALL" or held_qty < 1:
                    held_qty = 0.0
                    trades[-1]["status"] = "CLOSED"

    # Degerleme
    final_close = float(df.iloc[-1]['Close'])
    final_value = capital + (held_qty * final_close)
    
    completed = [t for t in trades if t["status"] == "CLOSED"]
    wins = [t for t in completed if t["pnl"] > 0]
    losses = [t for t in completed if t["pnl"] <= 0]
    
    print("\n" + "="*50)
    print(f"=== {ticker} DIP AVCISI BACKTEST SONUCLARI ===")
    print("="*50)
    print(f"Baslangic Sermayesi : {initial_capital:,.2f} TL")
    print(f"Bitis Sermayesi     : {final_value:,.2f} TL")
    print(f"Toplam Getiri (%)   : {((final_value - initial_capital)/initial_capital)*100:+.2f}%")
    print("-"*50)
    print(f"Toplam Acilan Pozisyon : {len(trades)}")
    print(f"Kapanan Pozisyon       : {len(completed)}")
    print(f"Kazanan Pozisyon (Win) : {len(wins)}")
    print(f"Kaybeden Pozisyon (Loss): {len(losses)}")
    win_rate = len(wins)/len(completed)*100 if completed else 0.0
    print(f"Kazanma Orani (Win%)   : {win_rate:.2f}%")
    print("="*50)

if __name__ == "__main__":
    run_dip_avcisi_backtest("XU100.IS", period="6mo", interval="1h")
