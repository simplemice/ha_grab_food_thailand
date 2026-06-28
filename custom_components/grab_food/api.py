"""Grab Food API client."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import aiohttp

from .const import (
    GRAB_API_BASE,
    GRAB_FOOD_BASE,
    GRAB_ORDER_DETAIL,
    GRAB_ORDERS_ACTIVE,
    GRAB_ORDERS_HISTORY,
    GRAB_OTP_REQUEST,
    GRAB_OTP_VERIFY,
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
        self.token_expiry = token_expiry or 0.0
        self._lock = asyncio.Lock()

    # ── Auth flow ────────────────────────────────────────────────────────

    async def request_otp(self, phone_number: str, country_code: str = "+66") -> bool:
        """Request an OTP to the given phone number.

        Returns True if the OTP was sent successfully.
        """
        payload = {
            "method": "SMS",
            "countryCode": country_code,
            "phoneNumber": phone_number,
        }
        try:
            async with self._session.post(
                GRAB_OTP_REQUEST,
                json=payload,
                headers=_COMMON_HEADERS,
            ) as resp:
                if resp.status == 200:
                    return True
                body = await resp.text()
                _LOGGER.error("OTP request failed (%s): %s", resp.status, body)
                return False
        except aiohttp.ClientError as err:
            _LOGGER.error("OTP request error: %s", err)
            return False

    async def verify_otp(
        self,
        phone_number: str,
        otp: str,
        country_code: str = "+66",
    ) -> dict[str, Any]:
        """Verify the OTP and return tokens.

        Returns dict with access_token, refresh_token, expires_in on success.
        Raises GrabAuthError on failure.
        """
        payload = {
            "method": "SMS",
            "countryCode": country_code,
            "phoneNumber": phone_number,
            "otp": otp,
        }
        try:
            async with self._session.post(
                GRAB_OTP_VERIFY,
                json=payload,
                headers=_COMMON_HEADERS,
            ) as resp:
                data = await resp.json()
                if resp.status == 200 and "access_token" in data:
                    self.access_token = data["access_token"]
                    self.refresh_token = data.get("refresh_token", "")
                    self.token_expiry = time.time() + data.get("expires_in", 3600)
                    return data
                raise GrabAuthError(
                    f"OTP verification failed ({resp.status}): {data}"
                )
        except aiohttp.ClientError as err:
            raise GrabAuthError(f"OTP verification error: {err}") from err

    async def _refresh_access_token(self) -> None:
        """Refresh the access token using the refresh token."""
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
            ) as resp:
                data = await resp.json()
                if resp.status == 200 and "access_token" in data:
                    self.access_token = data["access_token"]
                    self.refresh_token = data.get("refresh_token", self.refresh_token)
                    self.token_expiry = time.time() + data.get("expires_in", 3600)
                    _LOGGER.debug("Token refreshed successfully")
                    return
                raise GrabAuthError(
                    f"Token refresh failed ({resp.status}): {data}"
                )
        except aiohttp.ClientError as err:
            raise GrabAuthError(f"Token refresh error: {err}") from err

    async def _ensure_token(self) -> None:
        """Ensure the access token is valid, refreshing if needed."""
        async with self._lock:
            if time.time() >= (self.token_expiry - 60):
                await self._refresh_access_token()

    def _auth_headers(self) -> dict[str, str]:
        """Return headers with current bearer token."""
        return {
            **_COMMON_HEADERS,
            "Authorization": f"Bearer {self.access_token}",
        }

    # ── API requests ─────────────────────────────────────────────────────

    async def _api_get(self, url: str, params: dict | None = None) -> dict[str, Any]:
        """Authenticated GET request."""
        await self._ensure_token()
        try:
            async with self._session.get(
                url,
                headers=self._auth_headers(),
                params=params,
            ) as resp:
                if resp.status == 401:
                    # Token expired mid-request — retry once
                    await self._refresh_access_token()
                    async with self._session.get(
                        url,
                        headers=self._auth_headers(),
                        params=params,
                    ) as retry:
                        if retry.status != 200:
                            body = await retry.text()
                            raise GrabApiError(
                                f"API GET {url} failed ({retry.status}): {body}"
                            )
                        return await retry.json()
                if resp.status != 200:
                    body = await resp.text()
                    raise GrabApiError(
                        f"API GET {url} failed ({resp.status}): {body}"
                    )
                return await resp.json()
        except aiohttp.ClientError as err:
            raise GrabApiError(f"API GET {url} error: {err}") from err

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
