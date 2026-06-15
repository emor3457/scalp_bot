# Architecture Patterns

**Domain:** BIST Scalp Bot
**Researched:** 2026-06-15

## Recommended Architecture

The system follows an **Asynchronous Event-Driven** pattern to handle the strict 3-second response time required by TradingView.

### Component Boundaries

| Component | Responsibility | Communicates With |
|-----------|---------------|-------------------|
| **FastAPI Listener** | Receives POST webhooks, validates tokens. | TradingView, Background Task Queue |
| **Task Queue** | Manages execution threads to avoid blocking. | Execution Engine |
| **Execution Engine** | Interacts with AlgoLab API or Playwright. | Broker / Exchange |
| **Risk Manager** | Checks OTR and PTRM limits before sending orders. | Execution Engine |
| **Telegram Bot** | Sends status updates to the user. | User |

### Data Flow

1. **TradingView** sends a JSON POST to `/webhook`.
2. **FastAPI** validates the `passphrase`.
3. If valid, FastAPI spawns a `BackgroundTasks` job and returns `200 OK` to TradingView immediately.
4. **Risk Manager** checks if the current OTR (Order-to-Trade) ratio is safe.
5. **Execution Engine** performs the trade via API or Automation.
6. **Telegram Bot** notifies the user of success or failure.

## Patterns to Follow

### Pattern 1: Immediate Acknowledgement
**What:** Return HTTP 200 before processing logic.
**When:** Always for TradingView webhooks.
**Example:**
```python
@app.post("/webhook")
async def webhook(data: Signal, background_tasks: BackgroundTasks):
    if data.passphrase != SECRET:
        raise HTTPException(status_code=401)
    background_tasks.add_task(process_trade, data)
    return {"status": "accepted"}
```

## Anti-Patterns to Avoid

### Anti-Pattern 1: Synchronous UI Automation
**What:** Running browser automation inside the request/response cycle.
**Why bad:** Browser startup takes >3s, causing TradingView to mark the alert as "Failed" and stop sending further alerts.
**Instead:** Use async task queues or background threads.

## Scalability Considerations

| Concern | At 1 trade/day | At 100 trades/hour |
|---------|--------------|-------------------|
| **Database** | SQLite is perfect. | SQLite still fine (low volume). |
| **Execution** | Browser automation okay. | API (AlgoLab) mandatory (automation too slow). |
| **Latency** | Not an issue. | VPS near Istanbul (colocation) might be needed. |

## Sources
- [FastAPI BackgroundTasks](https://fastapi.tiangolo.com/tutorial/background-tasks/)
- [TradingView Webhook Security](https://www.tradingview.com/support/solutions/43000529348-about-webhooks/)
