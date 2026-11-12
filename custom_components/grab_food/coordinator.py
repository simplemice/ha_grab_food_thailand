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
    STATE_MAP,
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
        # Save rotated tokens the moment they change, not after the next
        # successful poll (a failed poll would otherwise lose them).
        client.on_tokens_updated = self._persist_tokens

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
        self._persist_tokens()

        if not active_orders:
            self.update_interval = SCAN_INTERVAL_IDLE
            return self._empty_data()

        self.update_interval = SCAN_INTERVAL_ACTIVE
        order = active_orders[0] if isinstance(active_orders[0], dict) else {}

        order_id = order.get("orderID") or order.get("id") or order.get("order_id", "")
        detail: dict[str, Any] = {}
        if order_id:
            try:
                detail = await self.client.get_order_detail(str(order_id))
            except GrabAuthError as err:
                raise ConfigEntryAuthFailed(f"Authentication error: {err}") from err
            except GrabApiError:
                _LOGGER.debug("Could not fetch detail for order %s", order_id)
            if not isinstance(detail, dict):
                detail = {}

        return self._parse_order(order, detail)

    # ── Parsers ──────────────────────────────────────────────────────────

    def _parse_order(
        self,
        order: dict[str, Any],
        detail: dict[str, Any],
    ) -> dict[str, Any]:
        """Normalise order data into a flat dict for sensors."""
        merged = {**order, **detail}

        status_raw = (
            merged.get("state")
            or merged.get("status")
            or merged.get("orderState")
            or ""
        )
        status_key = (
            str(status_raw).strip().lower().replace(" ", "_").replace("-", "_")
            if isinstance(status_raw, (str, int, float))
            else ""
        )
        status = STATE_MAP.get(status_key, "unknown")

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
            if isinstance(loc_raw, dict):
                driver_lat = self._first(loc_raw.get("latitude"), loc_raw.get("lat"))
                driver_lng = self._first(loc_raw.get("longitude"), loc_raw.get("lng"))
            else:
                driver_lat = driver_lng = None
        else:
            driver_name = ""
            driver_plate = ""
            driver_lat = None
            driver_lng = None

        # Items
        items = merged.get("items") or merged.get("orderItems") or []
        item_list = [i for i in items if isinstance(i, dict)] if isinstance(items, list) else []
        item_count = len(item_list)
        item_names = []
        for item in item_list:
            name = item.get("name") or item.get("itemName") or ""
            try:
                qty = int(float(item.get("quantity") or item.get("qty") or 1))
            except (TypeError, ValueError):
                qty = 1
            if name:
                item_names.append(f"{qty}× {name}" if qty > 1 else str(name))

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
            "status": status,
            "status_raw": str(status_raw) if status_raw != "" else None,
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
            "status_raw": None,
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
            value = value.get("amount")
            if value is None:
                return None
            if isinstance(value, (int, float)):
                return float(value)
        try:
            return float(str(value).replace(",", "").replace("฿", "").strip())
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _first(*values: Any) -> Any:
        """Return the first value that is not None (keeps 0)."""
        return next((v for v in values if v is not None), None)

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

    def _persist_tokens(self) -> None:
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
