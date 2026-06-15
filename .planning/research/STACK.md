# Technology Stack

**Project:** BIST Scalp Bot
**Researched:** 2026-06-15

## Recommended Stack

### Core Framework
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| Python | 3.12+ | Language | Standard for trading and rich library ecosystem. |
| FastAPI | Latest | Webhook Listener | Ultra-fast, async by default, perfect for TV 3s timeout. |
| Uvicorn | Latest | ASGI Server | High-performance server to run FastAPI. |

### Execution
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| AlgoLab API | N/A | Order Execution | Zero-cost official API for Deniz Yatırım. |
| Playwright | Latest | Automation Fallback | Reliable browser automation for brokers without APIs. |

### Data & Infrastructure
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| SQLite | 3.x | Database | Lightweight, zero-config, handles local trade history. |
| Ngrok / Cloudflare | N/A | Tunnelling | Exposes local FastAPI to TradingView's webhooks securely. |

### Supporting Libraries
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `python-telegram-bot` | 21.x | Notifications | Trade logs and error alerts. |
| `pydantic` | 2.x | Data Validation | Strict schema for incoming webhooks. |
| `httpx` | Latest | Async Requests | Calling external APIs (AlgoLab, Telegram) without blocking. |

## Alternatives Considered

| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| API | AlgoLab | Matriks/Ideal | High monthly costs (thousands of TL). |
| Automation | Playwright | Selenium | Playwright is faster and has better "auto-wait" features. |
| DB | SQLite | PostgreSQL | Overkill for a local single-user scalp bot. |

## Installation

```bash
# Core
pip install fastapi uvicorn pydantic httpx playwright python-telegram-bot aiosqlite

# Playwright setup
playwright install chromium
```

## Sources
- [TradingView Webhook Docs](https://www.tradingview.com/support/solutions/43000529348-about-webhooks/)
- [AlgoLab API Community Wrapper](https://github.com/atillayurtseven/AlgoLab)
- [Borsa Istanbul PTRM & Fees](https://www.borsaistanbul.com/en/sayfa/2312/ptrm-pre-trade-risk-management)
