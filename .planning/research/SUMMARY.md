# Research Summary: BIST Scalp Bot

**Domain:** Algorithmic Trading (Borsa Istanbul)
**Researched:** 2026-06-15
**Overall confidence:** HIGH

## Executive Summary
This research focuses on building a zero-cost scalp bot for Borsa Istanbul (BIST) using TradingView webhooks and Python. The primary challenge in the BIST ecosystem is the high cost of data and API access from traditional vendors (Matriks, Ideal). 

The most viable zero-cost solution for execution is **AlgoLab (Deniz Yatırım)**, which provides a REST/WebSocket API to its customers for free. For users at other brokers, **browser automation (Playwright/Selenium)** remains the only zero-cost "hack," though it is prone to breakage.

Risk management is dominated by BIST's unique **Order-to-Trade Ratio (OTR)** penalties and **Pre-Trade Risk Management (PTRM)** limits. Success in scalping requires high liquidity (BIST 30) and strict adherence to a 5:1 order-to-execution ratio to avoid heavy penalties.

## Key Findings

**Stack:** Python 3.12, FastAPI (Webhook listener), AlgoLab API (Execution), Telegram (Alerts).
**Architecture:** Event-driven architecture where TradingView alerts trigger asynchronous execution tasks to meet the 3-second webhook timeout requirement.
**Critical pitfall:** **OTR (Order-to-Trade Ratio)**. Exceeding 5 orders per 1 execution results in a 0.50 TL penalty per excess order, which can wipe out scalp profits instantly.

## Implications for Roadmap

Based on research, suggested phase structure:

1. **Infrastructure & Security** - Establishing the FastAPI listener with HTTPS (Ngrok/Cloudflare) and secret token validation.
   - Addresses: Webhook reliability and security.
2. **Execution Engine (AlgoLab/Automation)** - Integrating with AlgoLab API or finalizing the Playwright automation fallback.
   - Addresses: The core "Zero-Cost" requirement.
3. **Risk & OTR Management** - Implementing logic to track OTR and prevent "flickering" orders.
   - Addresses: The most dangerous pitfall identified.
4. **Notifications & Monitoring** - Telegram integration for real-time trade updates.
   - Addresses: Operational visibility.

**Phase ordering rationale:**
- Security and connectivity must come first to receive signals. 
- Execution is the core functionality.
- Risk management is added before "live" trading to protect the capital.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | AlgoLab is well-documented; FastAPI is standard for webhooks. |
| Features | MEDIUM | Scalp features depend on TradingView script quality. |
| Architecture | HIGH | Async patterns are mandatory for TradingView's 3s timeout. |
| Pitfalls | HIGH | OTR and PTRM are official BIST regulations. |

## Gaps to Address

- **Broker Specifics:** Each broker has different UI/API quirks for the automation fallback.
- **Backtesting:** Zero-cost historical data for BIST is limited to 15m delay; backtesting should happen on TradingView.
