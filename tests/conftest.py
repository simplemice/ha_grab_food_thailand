"""Shared fixtures and fakes."""

from __future__ import annotations

import asyncio
import base64
import json
import time
from typing import Any

import aiohttp
import pytest


@pytest.fixture(autouse=True)
def _enable_custom_integrations(enable_custom_integrations):
    """Allow HA to load custom_components/grab_food."""
    yield


def make_jwt(exp_in: float | None = 86400, sub: str = "user-1") -> str:
    """Build an unsigned JWT-shaped token (same header as real ones)."""

    def b64(obj: dict) -> str:
        raw = json.dumps(obj).encode()
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    claims: dict[str, Any] = {"sub": sub}
    if exp_in is not None:
        claims["exp"] = int(time.time() + exp_in)
    return f"{b64({'alg': 'HS256', 'typ': 'JWT'})}.{b64(claims)}.sig"


class FakeResp:
    """Minimal aiohttp response stand-in."""

    def __init__(self, status=200, data=None, content_type="application/json"):
        self.status = status
        self._data = data if data is not None else {}
        self.headers = {"Content-Type": content_type}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def json(self):
        return self._data

    async def text(self):
        return json.dumps(self._data)


class _Ctx:
    def __init__(self, item):
        self._item = item

    async def __aenter__(self):
        if isinstance(self._item, BaseException):
            raise self._item
        return self._item

    async def __aexit__(self, *exc):
        return False


class FakeSession:
    """Queue of responses per URL substring. Exceptions are raised on enter."""

    def __init__(self):
        self.routes: dict[str, list[Any]] = {}
        self.calls: list[tuple[str, str, dict]] = []

    def add(self, url_part: str, *items: Any) -> None:
        self.routes.setdefault(url_part, []).extend(items)

    def _pop(self, method: str, url: str, kwargs: dict):
        self.calls.append((method, url, kwargs.get("headers", {})))
        for part, queue in self.routes.items():
            if part in url:
                if not queue:
                    raise AssertionError(f"no queued response for {url}")
                return _Ctx(queue.pop(0))
        raise AssertionError(f"unexpected request {url}")

    def get(self, url, **kwargs):
        return self._pop("GET", url, kwargs)

    def post(self, url, **kwargs):
        return self._pop("POST", url, kwargs)


ClientError = aiohttp.ClientError
Timeout = asyncio.TimeoutError
