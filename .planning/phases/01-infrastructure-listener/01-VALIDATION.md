# VALIDATION: Phase 1 - Infrastructure & Listener

## 🎯 Verification Goals
Ensure the FastAPI listener is secure, async, and accessible via a persistent Ngrok tunnel while preserving existing functionality.

## 🧪 Automated Tests
- [ ] `pytest tests/test_webhook_security.py`: Verify IP whitelisting and passphrase validation.
- [ ] `pytest tests/test_market_hours.py`: Verify BIST market hours logic using `pandas_market_calendars`.
- [ ] `pytest tests/test_existing_endpoints.py`: Verify `/dashboard`, `/portfolio`, etc., are still functional.

## 🕹️ Manual Verification
- [ ] **Ngrok Tunnel:** Confirm the static domain is active and points to `localhost:8000`.
- [ ] **TradingView Simulation:** Send a test webhook from TradingView (or Postman with TV IP headers) and confirm `202 Accepted` response within < 100ms.
- [ ] **Log Inspection:** Check `bot.log` for correct IP detection and security rejection messages.

## 🏁 Success Criteria
- [ ] Webhook listener accepts valid signals only from TV IPs + correct Passphrase.
- [ ] Responses are returned immediately (Async).
- [ ] Existing dashboard and API endpoints work as before.
- [ ] BIST market hour guard correctly rejects signals outside 09:40-18:10.
