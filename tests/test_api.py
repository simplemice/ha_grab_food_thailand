"""API client token handling."""

from __future__ import annotations

import time

import pytest

from custom_components.grab_food.api import (
    GrabApiError,
    GrabAuthError,
    GrabFoodApiClient,
)

from .conftest import ClientError, FakeResp, FakeSession, Timeout, make_jwt

ACTIVE = "orders/active"
REFRESH = "oauth2/token"


def client(session, access=None, refresh="", expiry=0.0):
    return GrabFoodApiClient(
        session, access or make_jwt(), refresh_token=refresh, token_expiry=expiry
    )


async def test_valid_jwt_without_refresh_not_expired_by_guess():
    """Stored 1h guess in the past must not break a still-valid JWT."""
    s = FakeSession()
    s.add(ACTIVE, FakeResp(data={"orders": []}))
    c = client(s, make_jwt(exp_in=86400), expiry=time.time() - 10)
    assert await c.get_active_orders() == []


async def test_unknown_expiry_without_refresh_still_requests():
    s = FakeSession()
    s.add(ACTIVE, FakeResp(data={"orders": []}))
    c = client(s, "opaque-token", expiry=0.0)
    assert await c.get_active_orders() == []


async def test_rejected_token_without_refresh_is_auth_error():
    s = FakeSession()
    s.add(ACTIVE, FakeResp(status=401))
    c = client(s)
    with pytest.raises(GrabAuthError):
        await c.get_active_orders()


async def test_refresh_network_error_is_not_auth_error():
    """Transient network failure must not trigger a reauth prompt."""
    s = FakeSession()
    s.add(ACTIVE, FakeResp(status=401))
    s.add(REFRESH, ClientError("boom"))
    c = client(s, refresh="r1")
    with pytest.raises(GrabApiError):
        await c.get_active_orders()


async def test_refresh_timeout_is_api_error():
    s = FakeSession()
    s.add(ACTIVE, FakeResp(status=401))
    s.add(REFRESH, Timeout())
    c = client(s, refresh="r1")
    with pytest.raises(GrabApiError):
        await c.get_active_orders()


async def test_refresh_server_error_is_api_error():
    s = FakeSession()
    s.add(ACTIVE, FakeResp(status=401))
    s.add(REFRESH, FakeResp(status=503))
    c = client(s, refresh="r1")
    with pytest.raises(GrabApiError):
        await c.get_active_orders()


async def test_refresh_rejected_is_auth_error():
    s = FakeSession()
    s.add(ACTIVE, FakeResp(status=401))
    s.add(REFRESH, FakeResp(status=400, data={"error": "invalid_grant"}))
    c = client(s, refresh="r1")
    with pytest.raises(GrabAuthError):
        await c.get_active_orders()


async def test_get_timeout_is_api_error():
    s = FakeSession()
    s.add(ACTIVE, Timeout())
    with pytest.raises(GrabApiError):
        await client(s).get_active_orders()


async def test_401_refresh_retry_success_and_callback():
    new = make_jwt(exp_in=3600, sub="user-1")
    s = FakeSession()
    s.add(ACTIVE, FakeResp(status=401), FakeResp(data={"orders": [{"id": 1}]}))
    s.add(REFRESH, FakeResp(data={"access_token": new, "refresh_token": "r2", "expires_in": 3600}))
    c = client(s, refresh="r1")
    seen = []
    c.on_tokens_updated = lambda: seen.append(c.refresh_token)
    assert await c.get_active_orders() == [{"id": 1}]
    assert c.access_token == new and c.refresh_token == "r2"
    assert seen == ["r2"]


async def test_callback_fires_even_if_retry_fails():
    """Rotated refresh token must be saved even when the follow-up call fails."""
    s = FakeSession()
    s.add(ACTIVE, FakeResp(status=401), FakeResp(status=500))
    s.add(REFRESH, FakeResp(data={"access_token": make_jwt(), "refresh_token": "r2", "expires_in": 3600}))
    c = client(s, refresh="r1")
    seen = []
    c.on_tokens_updated = lambda: seen.append(c.refresh_token)
    with pytest.raises(GrabApiError):
        await c.get_active_orders()
    assert seen == ["r2"]


async def test_second_401_after_refresh_is_auth_error():
    s = FakeSession()
    s.add(ACTIVE, FakeResp(status=401), FakeResp(status=401))
    s.add(REFRESH, FakeResp(data={"access_token": make_jwt(), "expires_in": 3600}))
    c = client(s, refresh="r1")
    with pytest.raises(GrabAuthError):
        await c.get_active_orders()


async def test_proactive_refresh_when_expiry_known_and_past():
    s = FakeSession()
    s.add(REFRESH, FakeResp(data={"access_token": make_jwt(), "refresh_token": "r2", "expires_in": 3600}))
    s.add(ACTIVE, FakeResp(data={"orders": []}))
    c = client(s, "opaque", refresh="r1", expiry=time.time() - 5)
    await c.get_active_orders()
    assert [m for m, *_ in s.calls] == ["POST", "GET"]
