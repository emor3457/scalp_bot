import pytest
import asyncio
import datetime
import pytz
from fastapi.testclient import TestClient

import market_hours
import database
import llm_manager
from main import app

client = TestClient(app)

def test_market_hours_logic():
    tz = pytz.timezone("Europe/Istanbul")
    # Wednesday 14:30 TR
    open_time = tz.localize(datetime.datetime(2026, 6, 17, 14, 30))
    assert market_hours.is_bist_open(open_time) is True

    # Wednesday 08:30 TR
    closed_morning = tz.localize(datetime.datetime(2026, 6, 17, 8, 30))
    assert market_hours.is_bist_open(closed_morning) is False

    # Saturday 12:00 TR
    weekend = tz.localize(datetime.datetime(2026, 6, 20, 12, 0))
    assert market_hours.is_bist_open(weekend) is False

    # 17:55 TR -> Closing session
    closing_time = tz.localize(datetime.datetime(2026, 6, 17, 17, 55))
    assert market_hours.is_session_closing(closing_time) is True

@pytest.mark.asyncio
async def test_llm_settings_and_full_reset_persistence():
    database.init_db()

    # 1. Save custom LLM settings
    test_key = "AIzaSy_TEST_KEY_PERSISTENCE_12345"
    test_model = "gemini-2.5-pro"
    await llm_manager.save_llm_settings("gemini", test_key, test_model)

    settings = await llm_manager.get_llm_settings()
    assert settings["api_key"] == test_key
    assert settings["active_model"] == test_model

    # 2. Add sample trade and position
    now_tr = market_hours.get_tr_now_str()
    conn = await database.get_async_db_connection()
    try:
        await conn.execute(
            "INSERT INTO trades (ticker, action, price, quantity, total_value, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
            ("THYAO", "AL", 300.0, 10, 3000.0, now_tr)
        )
        await conn.commit()
    finally:
        await conn.close()

    conn = await database.get_async_db_connection()
    try:
        async with conn.execute("SELECT COUNT(*) as cnt FROM trades") as cursor:
            row = await cursor.fetchone()
            assert row["cnt"] > 0
    finally:
        await conn.close()

    # 3. Perform Full Reset via API endpoint
    response = client.post("/api/full-reset", json={"amount": 150000.0})
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["status"] == "success"

    # 4. Verify trades were reset
    conn = await database.get_async_db_connection()
    try:
        async with conn.execute("SELECT COUNT(*) as cnt FROM trades") as cursor:
            row = await cursor.fetchone()
            assert row["cnt"] == 0
    finally:
        await conn.close()

    # 5. Verify LLM settings were PRESERVED!
    settings_after_reset = await llm_manager.get_llm_settings()
    assert settings_after_reset["api_key"] == test_key
    assert settings_after_reset["active_model"] == test_model
    assert settings_after_reset["provider"] == "gemini"

def test_api_llm_endpoints():
    # Test GET /api/llm/settings
    res = client.get("/api/llm/settings")
    assert res.status_code == 200
    data = res.json()
    assert "provider" in data
    assert "active_model" in data

    # Test POST /api/llm/save-settings
    save_res = client.post("/api/llm/save-settings", json={
        "provider": "gemini",
        "api_key": "AIzaSy_UPDATED_KEY_999",
        "model": "gemini-2.5-flash"
    })
    assert save_res.status_code == 200
    assert save_res.json()["status"] == "success"

    # Verify updated settings
    verify_res = client.get("/api/llm/settings")
    verify_data = verify_res.json()
    assert verify_data["api_key"] == "AIzaSy_UPDATED_KEY_999"
    assert verify_data["active_model"] == "gemini-2.5-flash"

def test_dashboard_contains_llm_modal():
    res = client.get("/dashboard")
    assert res.status_code == 200
    html = res.text
    assert "llmSettingsModal" in html
    assert "btnOpenLlmModal" in html
    assert "headerLlmBadge" in html
    assert "btnFetchModels" in html
    assert "btnSaveLlmSettings" in html
