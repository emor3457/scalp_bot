# REQUIREMENTS: Borsa Scalper

## 1. Functional Requirements
### 1.1 Webhook Listener
- Receive POST requests from TradingView.
- Validate `passphrase` in the JSON payload.
- Whitelist TradingView's official IP ranges.
- Return `200 OK` immediately (FastAPI BackgroundTasks).

### 1.2 Order Execution
- Integrate with **AlgoLab API** (Primary) or **Playwright** (Fallback).
- Support Market and Limit orders.
- Handle order status updates (Filled, Partial, Rejected).

### 1.3 Risk & Trade Management
- **OTR Counter:** Monitor and prevent exceeding BIST's 5:1 order-to-trade ratio.
- **Stop-Loss/Take-Profit:** Percentage-based SL/TP (can be managed by TV or local logic).
- **Position Sizing:** Calculate shares based on fixed cash amount or equity percentage.

### 1.4 Monitoring & Notifications
- Send trade logs to a local SQLite database.
- Push real-time notifications to **Telegram**.
- Local dashboard (HTML/FastAPI) to view current state and logs.

## 2. Non-Functional Requirements
- **Latency:** Webhook-to-Order latency < 500ms.
- **Uptime:** Run locally on Windows with auto-restart on failure.
- **Security:** Secure storage of API keys in `.env`.

## 3. Constraints
- **BIST Hours:** Bot only operates during BIST trading hours.
- **Free Tier Limits:** Ngrok bandwidth and AlgoLab rate limits.
