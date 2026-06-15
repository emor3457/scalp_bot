# Feature Landscape

**Domain:** BIST Scalp Bot
**Researched:** 2026-06-15

## Table Stakes

Features users expect for any trading bot.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Webhook Listener | Must receive signals from TradingView. | Low | FastAPI handles this easily. |
| Order Execution | Buy/Sell orders on the exchange. | Medium | Depends on API/Automation reliability. |
| Secure Auth | Prevent random internet requests from trading. | Low | Passphrase validation. |
| Logging | Track what happened and why. | Low | Standard Python logging. |

## Differentiators

Features that set this bot apart for BIST.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| OTR Monitor | Prevent BIST penalties for excessive orders. | Medium | Tracks order/trade ratio in real-time. |
| Zero-Cost Setup | No monthly vendor fees (Matriks/Ideal). | High | Requires AlgoLab or Playwright mastery. |
| Telegram Control | Check status/stop bot via Telegram. | Medium | Bi-directional communication. |
| Multi-Broker Support | Abstracted execution layer for automation. | High | Custom logic per broker UI. |
| Position Sizing | Auto-calculate lot size based on balance. | Medium | (Balance * %Risk) / (Entry - StopLoss). |

## Risk Management Features

Scalp-specific risk controls for the Python side:

- **Hard Stop:** If price hits X, sell immediately (backup for TV signals).
- **Trailing Stop:** Python-side logic to move SL up as price moves.
- **Max Daily Loss:** Shut down bot if loss exceeds 2% of capital.
- **Tick Value Filter:** Only trade if (1 Tick Profit > Fees + Commission).

## Anti-Features

Features to explicitly NOT build.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| Charting | TV already does this better. | Focus on execution speed. |
| Indicator Logic | Complex to code in Python accurately. | Use TV PineScript for all logic. |
| High-Frequency (HFT) | Local home internet + Python is too slow. | Scalping (seconds/minutes), not HFT (ms). |

## Feature Dependencies

```
Webhook Listener → Auth Validation → Risk Manager (OTR/Size) → Execution Engine → Telegram Notification
```

## MVP Recommendation

Prioritize:
1. **Async Webhook Listener:** Must return `200 OK` in <3s.
2. **Simple Execution:** Buy/Sell market orders via Playwright or AlgoLab.
3. **Secret Token:** Basic security.
4. **OTR Basic Guard:** Simple counter to stop trading if OTR hits 4:1.

Defer:
- Trailing stops in Python (better to do in PineScript).
- Advanced portfolio management.

## Sources
- [Borsa Istanbul Scalping Best Practices](https://www.tradingview.com/scripts/scalping/)
- [Deniz Yatırım AlgoLab documentation](https://www.algolab.com.tr/)
