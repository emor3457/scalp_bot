# PROJECT: Borsa Scalper (BIST Scalp Bot)

## Overview
A zero-cost, locally hosted Borsa Istanbul (BIST) scalping bot that listens to TradingView webhooks via FastAPI and executes orders through Deniz Yatırım's AlgoLab API or browser automation.

## Core Mandates
- **Zero Cost:** No paid API subscriptions or server costs (local Windows hosting).
- **Speed:** Async handling of webhooks to stay within TradingView's 3-second timeout.
- **Reliability:** Robust error handling, logging, and OTR (Order-to-Trade Ratio) management.
- **Security:** IP whitelisting and passphrase validation for webhooks.

## Tech Stack
- **Backend:** Python, FastAPI, Uvicorn
- **Integration:** TradingView Webhooks, AlgoLab API
- **Tunneling:** Ngrok (free tier)
- **Database:** SQLite
- **Notifications:** Telegram Bot API

## Success Criteria
1. Successful reception and validation of TradingView webhooks.
2. Order execution with < 500ms latency from reception.
3. Accurate tracking of OTR to avoid exchange penalties.
4. Functional Telegram notifications for all trade events.
