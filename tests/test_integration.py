"""Config flow, setup, sensors, token persistence (real HA core)."""

from __future__ import annotations

import time
from unittest.mock import patch

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.grab_food.const import DOMAIN

from .conftest import ClientError, FakeResp, FakeSession, make_jwt

PATCH_ACTIVE = "custom_components.grab_food.api.GrabFoodApiClient.get_active_orders"
PATCH_DETAIL = "custom_components.grab_food.api.GrabFoodApiClient.get_order_detail"
PATCH_SESSION = "custom_components.grab_food.async_get_clientsession"
PATCH_SETUP = "custom_components.grab_food.async_setup_entry"


async def _add(hass: HomeAssistant, token: str, refresh: str = ""):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    return await hass.config_entries.flow.async_configure(
        result["flow_id"], {"access_token": token, "refresh_token": refresh}
    )


def _entry(refresh: str = "") -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        data={"access_token": make_jwt(), "refresh_token": refresh, "token_expiry": 0.0},
    )


async def test_two_accounts_can_be_added(hass: HomeAssistant):
    with patch(PATCH_ACTIVE, return_value=[]), patch(PATCH_SETUP, return_value=True):
        r1 = await _add(hass, make_jwt(sub="alice"))
        r2 = await _add(hass, make_jwt(sub="bob"))
    assert r1["type"] == "create_entry"
    assert r2["type"] == "create_entry"


async def test_same_account_new_token_is_duplicate(hass: HomeAssistant):
    with patch(PATCH_ACTIVE, return_value=[]), patch(PATCH_SETUP, return_value=True):
        await _add(hass, make_jwt(sub="alice"))
        r = await _add(hass, make_jwt(sub="alice", exp_in=999))
    assert r["type"] == "abort" and r["reason"] == "already_configured"


async def test_entry_stores_real_expiry_not_one_hour_guess(hass: HomeAssistant):
    with patch(PATCH_ACTIVE, return_value=[]), patch(PATCH_SETUP, return_value=True):
        r = await _add(hass, make_jwt(exp_in=5 * 86400))
    assert r["data"]["token_expiry"] > time.time() + 4 * 86400


async def test_expired_token_without_refresh_rejected(hass: HomeAssistant):
    with patch(PATCH_ACTIVE, return_value=[]):
        r = await _add(hass, make_jwt(exp_in=-100))
    assert r["type"] == "form" and r["errors"]["base"] == "invalid_token"


async def test_known_status_sensor_ok(hass: HomeAssistant):
    entry = _entry()
    entry.add_to_hass(hass)
    order = {"id": "9", "state": "ON_THE_WAY", "restaurant": {"name": "Som Tam"}}
    with patch(PATCH_ACTIVE, return_value=[order]), patch(PATCH_DETAIL, return_value={}):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    states = {s.entity_id: s.state for s in hass.states.async_all("sensor")}
    status = next(v for k, v in states.items() if k.endswith("order_status"))
    assert status == "delivering"
    assert "unavailable" not in states.values(), states


async def test_brand_new_status_shows_unknown(hass: HomeAssistant):
    entry = _entry()
    entry.add_to_hass(hass)
    with patch(PATCH_ACTIVE, return_value=[{"id": "9", "state": "BRAND_NEW"}]), patch(
        PATCH_DETAIL, return_value={}
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    status = next(
        s for s in hass.states.async_all("sensor") if s.entity_id.endswith("order_status")
    )
    assert status.state == "unknown"
    assert status.attributes["raw_status"] == "BRAND_NEW"


async def test_rotated_refresh_token_saved_even_if_poll_fails(hass: HomeAssistant):
    new_access = make_jwt(exp_in=3600)
    fake = FakeSession()
    fake.add("orders/active", FakeResp(status=401), FakeResp(status=500))
    fake.add(
        "oauth2/token",
        FakeResp(data={"access_token": new_access, "refresh_token": "r2", "expires_in": 3600}),
    )
    entry = _entry("r1")
    entry.add_to_hass(hass)
    with patch(PATCH_SESSION, return_value=fake):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    assert entry.data["refresh_token"] == "r2"
    assert entry.data["access_token"] == new_access


async def test_transient_refresh_failure_does_not_start_reauth(hass: HomeAssistant):
    fake = FakeSession()
    fake.add("orders/active", FakeResp(status=401))
    fake.add("oauth2/token", ClientError("net down"))
    entry = _entry("r1")
    entry.add_to_hass(hass)
    with patch(PATCH_SESSION, return_value=fake):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    assert not list(entry.async_get_active_flows(hass, {config_entries.SOURCE_REAUTH}))


async def test_dead_token_starts_reauth(hass: HomeAssistant):
    fake = FakeSession()
    fake.add("orders/active", FakeResp(status=401))
    entry = _entry()
    entry.add_to_hass(hass)
    with patch(PATCH_SESSION, return_value=fake):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_ERROR
    assert list(entry.async_get_active_flows(hass, {config_entries.SOURCE_REAUTH}))
