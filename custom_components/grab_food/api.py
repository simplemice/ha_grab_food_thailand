"""Grab Food API client."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import time
from collections.abc import Callable
from typing import Any

import aiohttp

from .const import (
    GRAB_ORDER_DETAIL,
    GRAB_ORDERS_ACTIVE,
    GRAB_ORDERS_HISTORY,
    GRAB_TOKEN_REFRESH,
)

_LOGGER = logging.getLogger(__name__)

# Grab mobile app headers (Android user-agent, required for API access)
_COMMON_HEADERS = {
    "User-Agent": "Grab/5.302.0 (Android 14; sdk_gphone64_arm64; en_TH)",
    "Accept": "application/json",
    "Content-Type": "application/json",
    "X-Platform": "Android",
    "X-App-Version": "5.302.0",
    "X-Country-Code": "TH",
    "X-Locale": "en_TH",
}


_TIMEOUT = aiohttp.ClientTimeout(total=15)


def jwt_claims(token: str | None) -> dict[str, Any]:
    """Return JWT payload claims, or {} if the token is not a decodable JWT."""
    try:
        payload = (token or "").split(".")[1]
        payload += "=" * (-len(payload) % 4)
        claims = json.loads(base64.urlsafe_b64decode(payload))
        return claims if isinstance(claims, dict) else {}
    except (IndexError, ValueError, TypeError):
        return {}


def jwt_expiry(token: str | None) -> float:
    """Return the JWT `exp` claim as epoch seconds, or 0.0 if unknown."""
    exp = jwt_claims(token).get("exp")
    return float(exp) if isinstance(exp, (int, float)) else 0.0


class GrabAuthError(Exception):
    """Raised when authentication fails."""


class GrabApiError(Exception):
    """Raised when an API call fails."""


class GrabFoodApiClient:
    """Async client for Grab Food Thailand API."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        access_token: str | None = None,
        refresh_token: str | None = None,
        token_expiry: float | None = None,
    ) -> None:
        """Initialize the client."""
        self._session = session
        self.access_token = access_token
        self.refresh_token = refresh_token
        # A real JWT exp beats any stored guess; 0.0 means "unknown".
        self.token_expiry = jwt_expiry(access_token) or token_expiry or 0.0
        self.on_tokens_updated: Callable[[], None] | None = None
        self._lock = asyncio.Lock()

    # ── Token handling ───────────────────────────────────────────────────

    def _apply_token_response(self, data: dict[str, Any]) -> None:
        """Store tokens from a refresh response and notify the owner."""
        self.access_token = data["access_token"]
        self.refresh_token = data.get("refresh_token") or self.refresh_token
        jwt_exp = jwt_expiry(self.access_token)
        self.token_expiry = jwt_exp or (time.time() + float(data.get("expires_in", 3600)))
        if self.on_tokens_updated is not None:
            try:
                self.on_tokens_updated()
            except Exception:  # noqa: BLE001 - never break a request over persistence
                _LOGGER.exception("Failed to persist refreshed tokens")

    async def _refresh_access_token(self) -> None:
        """Refresh the access token using the refresh token.

        Only a definitive rejection by Grab raises GrabAuthError (which starts
        the reauth flow). Network errors, timeouts and 5xx are GrabApiError so
        a transient problem never asks the user for a new token.
        """
        if not self.refresh_token:
            raise GrabAuthError("No refresh token available")

        payload = {
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token,
        }
        try:
            async with self._session.post(
                GRAB_TOKEN_REFRESH,
                json=payload,
                headers=_COMMON_HEADERS,
                timeout=_TIMEOUT,
            ) as resp:
                status = resp.status
                if status in (400, 401, 403):
                    raise GrabAuthError(f"Token refresh rejected (HTTP {status})")
                if status != 200:
                    raise GrabApiError(f"Token refresh failed (HTTP {status})")
                data = await resp.json()
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise GrabApiError(f"Token refresh error: {err!r}") from err

        if not isinstance(data, dict) or "access_token" not in data:
            raise GrabApiError("Token refresh returned no access_token")
        self._apply_token_response(data)
        _LOGGER.debug("Token refreshed successfully")

    async def _ensure_token(self) -> None:
        """Refresh proactively only when expiry is known and a refresh token exists.

        Without a refresh token (or with unknown expiry) the request is simply
        sent; a 401 then decides whether the token is really dead.
        """
        async with self._lock:
            if (
                self.refresh_token
                and self.token_expiry
                and time.time() >= self.token_expiry - 60
            ):
                await self._refresh_access_token()

    def _auth_headers(self) -> dict[str, str]:
        """Return headers with current bearer token."""
        return {
            **_COMMON_HEADERS,
            "Authorization": f"Bearer {self.access_token}",
        }

    # ── API requests ─────────────────────────────────────────────────────

    async def _fetch(self, url: str, params: dict | None) -> tuple[int, Any]:
        """Single GET. Returns (401, None) on 401, parsed JSON on 200."""
        try:
            async with self._session.get(
                url,
                headers=self._auth_headers(),
                params=params,
                allow_redirects=False,
                timeout=_TIMEOUT,
            ) as resp:
                if resp.status in (301, 302, 303, 307, 308):
                    location = resp.headers.get("Location", "unknown")
                    raise GrabApiError(
                        f"API endpoint redirected to {location}. "
                        "The Grab API URL may have changed — check const.py."
                    )
                if resp.status == 401:
                    return 401, None
                if resp.status != 200:
                    body = await resp.text()
                    raise GrabApiError(
                        f"API GET {url} failed ({resp.status}): {body[:200]}"
                    )
                return 200, await self._parse_json(url, resp)
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise GrabApiError(f"API GET {url} error: {err!r}") from err

    async def _api_get(self, url: str, params: dict | None = None) -> dict[str, Any]:
        """Authenticated GET with one refresh-and-retry on 401."""
        await self._ensure_token()
        used_token = self.access_token
        status, data = await self._fetch(url, params)
        if status != 401:
            return data

        if not self.refresh_token:
            raise GrabAuthError("Token rejected (401) and no refresh token available")
        async with self._lock:
            # Another task may already have refreshed while we waited.
            if self.access_token == used_token:
                await self._refresh_access_token()
        status, data = await self._fetch(url, params)
        if status == 401:
            raise GrabAuthError("Token rejected (401) even after refresh")
        return data

    @staticmethod
    async def _parse_json(url: str, resp: aiohttp.ClientResponse) -> dict[str, Any]:
        """Parse JSON from response, raising GrabApiError on non-JSON content."""
        content_type = resp.headers.get("Content-Type", "")
        if "json" not in content_type:
            body = await resp.text()
            raise GrabApiError(
                f"API GET {url} returned non-JSON ({content_type}): {body[:200]}"
            )
        return await resp.json()

    # ── Order data ───────────────────────────────────────────────────────

    async def get_active_orders(self) -> list[dict[str, Any]]:
        """Fetch currently active orders.

        Returns a list of order dicts (usually 0 or 1 active order).
        """
        data = await self._api_get(GRAB_ORDERS_ACTIVE)
        return data.get("orders", data.get("data", []))

    async def get_order_detail(self, order_id: str) -> dict[str, Any]:
        """Fetch full detail for a specific order."""
        url = f"{GRAB_ORDER_DETAIL}/{order_id}"
        return await self._api_get(url)

    async def get_order_history(self, limit: int = 5) -> list[dict[str, Any]]:
        """Fetch recent order history."""
        data = await self._api_get(
            GRAB_ORDERS_HISTORY,
            params={"limit": limit},
        )
        return data.get("orders", data.get("data", []))

    # ── Token export (for config entry persistence) ──────────────────────

    def export_tokens(self) -> dict[str, Any]:
        """Return current token state for storage."""
        return {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "token_expiry": self.token_expiry,
        }
