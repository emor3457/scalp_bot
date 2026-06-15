# Domain Pitfalls

**Domain:** BIST Scalp Bot
**Researched:** 2026-06-15

## Critical Pitfalls

### Pitfall 1: OTR (Order-to-Trade Ratio) Penalties
**What goes wrong:** Sending too many orders (buy, sell, cancel, modify) compared to executed trades.
**Why it happens:** Scalping scripts that "chase" price by constantly modifying orders.
**Consequences:** BIST charges 0.50 TL for every excess order (beyond 5:1 ratio). This can result in massive losses even on "winning" trades.
**Prevention:** Use "Fill-or-Kill" orders or limit modifications to once every few minutes.
**Detection:** Track `(total_orders / total_trades)` in the bot's internal state.

### Pitfall 2: Webhook Timeout (3 Seconds)
**What goes wrong:** TradingView stops sending alerts because the server takes too long to respond.
**Why it happens:** Performing browser automation or slow API calls inside the endpoint function.
**Consequences:** Bot misses trade signals; TradingView disables the alert.
**Prevention:** Always use `BackgroundTasks` in FastAPI to return `200 OK` instantly.

## Moderate Pitfalls

### Pitfall 3: Browser Automation Fragility
**What goes wrong:** Broker changes their website UI, and the bot fails to find the "Buy" button.
**Why it happens:** Dependence on HTML selectors (CSS/ID).
**Consequences:** Failed trades during high volatility.
**Prevention:** Use the AlgoLab API if possible. If using automation, use Playwright's "Robust Selectors" and implement Telegram alerts for immediate notification of failure.

### Pitfall 4: T+2 Settlement & Liquidity
**What goes wrong:** Trying to sell shares but funds are locked, or getting stuck in a "thin" stock with no buyers.
**Why it happens:** BIST uses T+2 settlement for cash; scalping illiquid stocks.
**Prevention:** Focus on BIST 30 stocks. Check "Usable Margin" via API before sending buy orders.

## Minor Pitfalls

### Pitfall 5: Timezone Mismatch
**What goes wrong:** Logs show wrong times; signals ignored outside market hours.
**Why it happens:** Server in UTC, BIST in GMT+3 (Turkey).
**Prevention:** Explicitly use `Europe/Istanbul` timezone in all Python datetime objects.

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|---------------|------------|
| Infrastructure | Ngrok tunnel reset | Use a static domain/URL (Cloudflare Tunnels). |
| Execution | SMS/2FA Block | Use "Persistent Context" in Playwright to keep session alive. |
| Risk Mgmt | Commission underestimation | Calculate "Net Profit" after deducting BSMV (Tax) and Broker Fees. |

## Sources
- [Borsa Istanbul Equity Market Fee Schedule](https://www.borsaistanbul.com/en/sayfa/2332/equity-market-fee-schedule)
- [PTRM User Guide](https://www.borsaistanbul.com/en/sayfa/2312/ptrm-pre-trade-risk-management)
