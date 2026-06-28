"""DataUpdateCoordinator for Grab Food Thailand."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .api import GrabApiError, GrabAuthError, GrabFoodApiClient
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_REFRESH_TOKEN,
    CONF_TOKEN_EXPIRY,
    DOMAIN,
    SCAN_INTERVAL_ACTIVE,
    SCAN_INTERVAL_IDLE,
)

_LOGGER = logging.getLogger(__name__)


class GrabFoodCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator that polls Grab Food for active order data.

    Adaptive polling:
      - Every 30 s when an order is active
      - Every 5 min when idle (no active order)
    """

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        client: GrabFoodApiClient,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=SCAN_INTERVAL_IDLE,
        )
        self.client = client
        self.config_entry = entry

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from the Grab API."""
        try:
            active_orders = await self.client.get_active_orders()
        except GrabAuthError as err:
            # Tokens are invalid — trigger the reauth flow rather than retry.
            raise ConfigEntryAuthFailed(f"Authentication error: {err}") from err
        except GrabApiError as err:
            # API unavailable or wrong endpoint — log and return empty data so
            # setup doesn't fail and sensors remain available (showing idle state).
            _LOGGER.warning("Grab API error (will retry): %s", err)
            return self._empty_data()

        # Persist tokens after every successful call (they may have refreshed)
        await self._persist_tokens()

        if not active_orders:
            self.update_interval = SCAN_INTERVAL_IDLE
            return self._empty_data()

        self.update_interval = SCAN_INTERVAL_ACTIVE
        order = active_orders[0]

        order_id = order.get("orderID") or order.get("id") or order.get("order_id", "")
        detail: dict[str, Any] = {}
        if order_id:
            try:
                detail = await self.client.get_order_detail(str(order_id))
            except GrabApiError:
                _LOGGER.debug("Could not fetch detail for order %s", order_id)

        return self._parse_order(order, detail)

    # ── Parsers ──────────────────────────────────────────────────────────

    def _parse_order(
        self,
        order: dict[str, Any],
        detail: dict[str, Any],
    ) -> dict[str, Any]:
        """Normalise order data into a flat dict for sensors."""
        merged = {**order, **detail}

        status = (
            merged.get("state")
            or merged.get("status")
            or merged.get("orderState")
            or "unknown"
        )

        # Restaurant — guard against API returning a plain string instead of dict
        restaurant_raw = merged.get("restaurant") or merged.get("merchant")
        if isinstance(restaurant_raw, dict):
            restaurant_name = (
                restaurant_raw.get("name")
                or restaurant_raw.get("merchantName")
                or merged.get("restaurantName")
                or "Unknown"
            )
        else:
            restaurant_name = merged.get("restaurantName") or "Unknown"

        # Price
        total_raw = (
            merged.get("totalPrice")
            or merged.get("total")
            or merged.get("amount")
            or merged.get("orderValue")
        )
        total = self._parse_price(total_raw)

        # ETA
        eta_raw = (
            merged.get("eta")
            or merged.get("estimatedDeliveryTime")
            or merged.get("deliveryETA")
        )
        eta = self._parse_eta(eta_raw)

        # Driver — guard against API returning a plain string
        driver_raw = merged.get("driver") or merged.get("deliveryInfo")
        if isinstance(driver_raw, dict):
            driver_name = driver_raw.get("name") or driver_raw.get("driverName") or ""
            driver_plate = (
                driver_raw.get("licensePlate")
                or driver_raw.get("plateNumber")
                or driver_raw.get("vehiclePlate")
                or ""
            )
            loc_raw = driver_raw.get("location") or driver_raw.get("coordinates") or {}
            driver_lat = loc_raw.get("latitude") or loc_raw.get("lat") if isinstance(loc_raw, dict) else None
            driver_lng = loc_raw.get("longitude") or loc_raw.get("lng") if isinstance(loc_raw, dict) else None
        else:
            driver_name = ""
            driver_plate = ""
            driver_lat = None
            driver_lng = None

        # Items
        items = merged.get("items") or merged.get("orderItems") or []
        item_count = len(items) if isinstance(items, list) else 0
        item_names = []
        for item in (items if isinstance(items, list) else []):
            name = item.get("name") or item.get("itemName") or ""
            qty = item.get("quantity") or item.get("qty") or 1
            if name:
                item_names.append(f"{qty}× {name}" if qty > 1 else name)

        # Delivery address — fix operator-precedence bug in original and guard types
        address_raw = merged.get("deliveryAddress") or merged.get("address")
        if isinstance(address_raw, str):
            delivery_address = address_raw
        elif isinstance(address_raw, dict):
            delivery_address = (
                address_raw.get("address")
                or address_raw.get("displayAddress")
                or ""
            )
        else:
            delivery_address = ""

        order_id = (
            merged.get("orderID")
            or merged.get("id")
            or merged.get("order_id")
            or ""
        )

        return {
            "has_active_order": True,
            "order_id": str(order_id),
            "status": str(status).lower().replace(" ", "_"),
            "restaurant_name": restaurant_name,
            "total": total,
            "currency": merged.get("currency", "THB"),
            "eta": eta,
            "eta_raw": eta_raw,
            "driver_name": driver_name,
            "driver_plate": driver_plate,
            "driver_latitude": driver_lat,
            "driver_longitude": driver_lng,
            "item_count": item_count,
            "item_names": item_names,
            "delivery_address": delivery_address,
            "raw": merged,
        }

    def _empty_data(self) -> dict[str, Any]:
        """Return the idle-state payload."""
        return {
            "has_active_order": False,
            "order_id": "",
            "status": "no_active_order",
            "restaurant_name": "",
            "total": None,
            "currency": "THB",
            "eta": None,
            "eta_raw": None,
            "driver_name": "",
            "driver_plate": "",
            "driver_latitude": None,
            "driver_longitude": None,
            "item_count": 0,
            "item_names": [],
            "delivery_address": "",
            "raw": {},
        }

    @staticmethod
    def _parse_price(value: Any) -> float | None:
        """Coerce various price formats to float."""
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, dict):
            return float(value.get("amount", 0))
        try:
            return float(str(value).replace(",", "").replace("฿", "").strip())
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _parse_eta(value: Any) -> str | None:
        """Normalise ETA to an ISO timestamp or minute string."""
        if value is None:
            return None
        if isinstance(value, str):
            return value
        if isinstance(value, (int, float)):
            if value < 200:
                return f"{int(value)} min"
            return datetime.fromtimestamp(value, tz=timezone.utc).isoformat()
        if isinstance(value, dict):
            return value.get("displayTime") or value.get("etaDisplay") or str(value)
        return str(value)

    # ── Token persistence ────────────────────────────────────────────────

    async def _persist_tokens(self) -> None:
        """Save current tokens back into the config entry."""
        tokens = self.client.export_tokens()
        current = dict(self.config_entry.data)
        changed = False
        for key, conf_key in [
            ("access_token", CONF_ACCESS_TOKEN),
            ("refresh_token", CONF_REFRESH_TOKEN),
            ("token_expiry", CONF_TOKEN_EXPIRY),
        ]:
            if tokens.get(key) and tokens[key] != current.get(conf_key):
                current[conf_key] = tokens[key]
                changed = True
        if changed:
            self.hass.config_entries.async_update_entry(
                self.config_entry, data=current
            )
