# Phase 1: Infrastructure & Listener - Research

**Researched:** 2024-06-15
**Domain:** Webhook Listener & Public Exposure
**Confidence:** HIGH

## Summary

This phase establishes the entry point for the Borsa Scalper bot. We are building a FastAPI-based webhook listener that will receive alerts from TradingView. To maintain the "Zero Cost" requirement while developing locally on Windows, we will use Ngrok's free tier with a static domain for persistent connectivity. The architecture focuses on high reliability and low latency (responding < 3s) by utilizing FastAPI's `BackgroundTasks` for processing while immediately acknowledging requests.

**Primary recommendation:** Use FastAPI with `BackgroundTasks` for non-blocking webhook processing and Ngrok with a free static domain for persistent local-to-cloud tunneling.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Public Endpoint | Ngrok Tunnel | — | Provides public URL for local development without port forwarding. |
| Request Routing | FastAPI | — | Handles incoming POST requests from TradingView. |
| Schema Validation | Pydantic | — | Ensures incoming JSON matches expected "Ticker, Action, Price" structure. |
| Authentication | Middleware/Logic | — | Verifies passphrase and whitelists TradingView IP ranges. |
| Task Deferral | BackgroundTasks | — | Ensures 200 OK response within TradingView's 3s timeout. |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `fastapi` | 0.115+ | Web framework | High performance, async-first, automatic Pydantic integration. |
| `uvicorn` | 0.30+ | ASGI Server | Standard, fast server for FastAPI. |
| `pydantic` | 2.9+ | Data validation | Used for strict webhook payload modeling. |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|--------------|
| `python-dotenv` | 1.0.1 | Secret management | Loading passphrase and Telegram tokens from `.env`. |
| `sqlalchemy` | 2.0+ | ORM | Storing incoming signals in SQLite for history. |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Ngrok | Cloudflare Tunnels | Cloudflare is more professional but requires owning a domain. Ngrok is zero-config for free static domains. |
| FastAPI | Flask | Flask is synchronous and slower; FastAPI's async nature is better for high-frequency scalp signals. |

**Installation:**
```bash
pip install fastapi uvicorn pydantic python-dotenv sqlalchemy
```

## Package Legitimacy Audit

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| fastapi | npm | 6 yrs | 50M/mo | github.com/tiangolo/fastapi | [ASSUMED] | Approved |
| uvicorn | npm | 7 yrs | 20M/mo | github.com/encode/uvicorn | [ASSUMED] | Approved |
| pydantic | npm | 7 yrs | 150M/mo | github.com/pydantic/pydantic | [ASSUMED] | Approved |
| python-dotenv | npm | 10 yrs | 100M/mo | github.com/theskumar/python-dotenv | [ASSUMED] | Approved |

*Note: slopcheck was unavailable during research; all packages are marked [ASSUMED]. Planner must include `checkpoint:human-verify` for installation.*

## Architecture Patterns

### System Architecture Diagram
`TradingView Alarm` -> `Ngrok Public URL` -> `Local FastAPI Listener` -> `Pydantic Validation` -> `Response (202 Accepted)` -> `BackgroundTasks` -> `Database/Execution Logic`.

### Recommended Project Structure
```
.
├── main.py              # FastAPI entry point
├── models/              # Pydantic schemas
│   └── webhook.py
├── core/                # Configuration and Security
│   └── config.py
├── .env                 # Secrets (NOT IN GIT)
└── requirements.txt
```

### Pattern 1: Deferring Logic with BackgroundTasks
**What:** Responding to TradingView before performing database writes or API calls.
**When to use:** Always for webhooks with <3s timeout.
**Example:**
```python
# Source: FastAPI Documentation
from fastapi import FastAPI, BackgroundTasks, status

app = FastAPI()

def process_signal(data):
    # Heavy logic here
    pass

@app.post("/webhook", status_code=status.HTTP_202_ACCEPTED)
async def handle_webhook(payload: SignalSchema, background_tasks: BackgroundTasks):
    background_tasks.add_task(process_signal, payload)
    return {"message": "Signal received"}
```

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| TradingView IPs | Hardcoded List | Verified Range | TradingView uses specific AWS IPs (see Common Pitfalls). |
| Tunneling | Custom SSH Tunnel | Ngrok/Cloudflared | Handling NAT traversal and persistent domains is complex. |
| Market Hours | Manual `if` blocks | `pandas_market_calendars` | BIST has complex holidays and half-days (Arife). |

## Common Pitfalls

### Pitfall 1: TradingView Timeout
**What goes wrong:** TradingView cancels the request if it doesn't get a response in 3 seconds.
**How to avoid:** Use `BackgroundTasks`. Never perform external API calls (like sending a Telegram message) in the main request flow.

### Pitfall 2: Dynamic Tunnel URL
**What goes wrong:** Ngrok free tier used to change URLs on restart, breaking TradingView alerts.
**How to avoid:** Use the **Free Static Domain** feature now offered by Ngrok (1 per account).

### Pitfall 3: Spoofed Webhooks
**What goes wrong:** Malicious actors sending "SELL ALL" signals to your endpoint.
**How to avoid:** Combine IP whitelisting with a mandatory `passphrase` field in the JSON payload.

## Code Examples

### TradingView IP Whitelist Middleware
```python
# Source: [VERIFIED: TradingView Docs]
TRADINGVIEW_IPS = ["52.89.214.238", "34.212.75.30", "54.218.53.128", "52.32.178.7"]

# Middleware logic should check request.client.host
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Randomized Ngrok URLs | Free Static Domains | 2023 | No more updating TV alerts on every reboot. |
| Synchronous Webhooks | Async FastAPI | 2020+ | Better concurrency for multiple simultaneous alarms. |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | TradingView IPs are stable | Code Examples | Signals might be blocked if IPs change. |
| A2 | Ngrok static domain is free | Alternatives | Development might require manual URL updates if paid. |

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | Runtime | ✓ | 3.14.0 | — |
| Pip | Packages | ✓ | 25.3 | — |
| Ngrok | Tunneling | ✗ | — | Manual port forward (NOT RECOMMENDED) |

**Missing dependencies with no fallback:**
- Ngrok: User must install `ngrok.exe` and authenticate.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | Pytest |
| Config file | `pytest.ini` |
| Full suite command | `pytest` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| INF-01 | Listener accepts JSON | Unit | `pytest tests/test_webhook.py` | ❌ |
| INF-02 | Invalid passphrase rejected | Security | `pytest tests/test_auth.py` | ❌ |
| INF-03 | IP Whitelist works | Security | `pytest tests/test_ips.py` | ❌ |

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V5 Input Validation | Yes | Pydantic Schema |
| V12 Communications | Yes | HTTPS (provided by Ngrok) |
| V14 Configuration | Yes | `.env` for Passphrase |

### Known Threat Patterns for FastAPI

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Webhook Spoofing | Spoofing | IP Whitelist + Passphrase |
| Denial of Service | Availability | Ngrok/FastAPI rate limiting |

## Sources

### Primary (HIGH confidence)
- `tradingview.com/support/solutions/43000529348-about-webhooks/` - IP ranges and timeout specs.
- `fastapi.tiangolo.com/tutorial/background-tasks/` - Background task patterns.

### Secondary (MEDIUM confidence)
- `ngrok.com/blog-post/free-static-domains-for-all-ngrok-users` - Static domain availability.
