# ROADMAP: Borsa Scalper

## Phase 1: Infrastructure & Listener
**Goal:** Set up a secure, async FastAPI listener accessible via a static Ngrok tunnel.
**Plans:** 1 plan
- [ ] 01-01-PLAN.md — Refactor FastAPI listener with CIDR-based IP whitelisting, XIST market hours, and regression testing.

**Requirements:** [INF-01, INF-02, INF-03]

### Tasks:
- [x] Initialize project structure and `.env`.
- [ ] Create FastAPI listener with IP whitelisting and Passphrase validation.
- [ ] Implement `BackgroundTasks` for async signal processing.
- [ ] Set up Ngrok/Cloudflare tunnel for external access.

## Phase 2: Execution Engine
- [ ] Integrate AlgoLab API (Authentication & Order Placement).
- [ ] Implement fallback Playwright automation for web terminals.
- [ ] Create mock execution for testing.

## Phase 3: Risk & Database
- [ ] Set up SQLite database with SQLAlchemy.
- [ ] Implement OTR (Order-to-Trade Ratio) tracking logic.
- [ ] Add Stop-Loss and Trailing Stop logic.

## Phase 4: Notifications & UI
- [ ] Integrate Telegram Bot API for trade alerts.
- [ ] Create a simple HTML dashboard for live monitoring.
- [ ] Add manual kill-switch (via Telegram or Dashboard).

## Phase 5: Testing & Deployment
- [ ] E2E testing with TradingView alerts (Simulated/Paper).
- [ ] Production deployment on local machine.
