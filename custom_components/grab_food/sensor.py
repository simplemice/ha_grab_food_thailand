"""Sensor platform for Grab Food Thailand."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTRIBUTION, DOMAIN, ORDER_STATES
from .coordinator import GrabFoodCoordinator


@dataclass(frozen=True, kw_only=True)
class GrabFoodSensorEntityDescription(SensorEntityDescription):
    """Extended description for Grab Food sensors."""

    value_fn: Callable[[dict[str, Any]], Any]
    extra_attrs_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None


SENSOR_DESCRIPTIONS: tuple[GrabFoodSensorEntityDescription, ...] = (
    GrabFoodSensorEntityDescription(
        key="order_status",
        translation_key="order_status",
        icon="mdi:moped",
        device_class=SensorDeviceClass.ENUM,
        options=ORDER_STATES,
        value_fn=lambda d: d.get("status", "no_active_order"),
        extra_attrs_fn=lambda d: {"order_id": d.get("order_id", "")},
    ),
    GrabFoodSensorEntityDescription(
        key="restaurant_name",
        translation_key="restaurant_name",
        icon="mdi:silverware-fork-knife",
        value_fn=lambda d: d.get("restaurant_name") or None,
    ),
    GrabFoodSensorEntityDescription(
        key="order_total",
        translation_key="order_total",
        icon="mdi:cash",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement="THB",
        suggested_display_precision=0,
        value_fn=lambda d: d.get("total"),
        extra_attrs_fn=lambda d: {"currency": d.get("currency", "THB")},
    ),
    GrabFoodSensorEntityDescription(
        key="estimated_delivery",
        translation_key="estimated_delivery",
        icon="mdi:clock-fast",
        value_fn=lambda d: d.get("eta"),
        extra_attrs_fn=lambda d: {"raw_eta": d.get("eta_raw")},
    ),
    GrabFoodSensorEntityDescription(
        key="driver_name",
        translation_key="driver_name",
        icon="mdi:account",
        value_fn=lambda d: d.get("driver_name") or None,
        extra_attrs_fn=lambda d: {
            "latitude": d.get("driver_latitude"),
            "longitude": d.get("driver_longitude"),
        },
    ),
    GrabFoodSensorEntityDescription(
        key="driver_plate",
        translation_key="driver_plate",
        icon="mdi:motorbike",
        value_fn=lambda d: d.get("driver_plate") or None,
    ),
    GrabFoodSensorEntityDescription(
        key="item_count",
        translation_key="item_count",
        icon="mdi:food",
        value_fn=lambda d: d.get("item_count", 0),
        extra_attrs_fn=lambda d: {"items": d.get("item_names", [])},
    ),
    GrabFoodSensorEntityDescription(
        key="order_id",
        translation_key="order_id",
        icon="mdi:identifier",
        value_fn=lambda d: d.get("order_id") or None,
    ),
    GrabFoodSensorEntityDescription(
        key="delivery_address",
        translation_key="delivery_address",
        icon="mdi:map-marker-radius",
        value_fn=lambda d: d.get("delivery_address") or None,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Grab Food sensors from a config entry."""
    coordinator: GrabFoodCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        GrabFoodSensor(coordinator, description)
        for description in SENSOR_DESCRIPTIONS
    )


class GrabFoodSensor(CoordinatorEntity[GrabFoodCoordinator], SensorEntity):
    """Sensor representing one aspect of a Grab Food order."""

    entity_description: GrabFoodSensorEntityDescription
    _attr_has_entity_name = True
    _attr_attribution = ATTRIBUTION

    def __init__(
        self,
        coordinator: GrabFoodCoordinator,
        description: GrabFoodSensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}_{description.key}"
        )
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.config_entry.entry_id)},
            name="Grab Food",
            manufacturer="Grab Holdings",
            model="Grab Food Thailand",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def native_value(self) -> Any:
        """Return the sensor value."""
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return additional attributes."""
        if (
            self.coordinator.data is None
            or self.entity_description.extra_attrs_fn is None
        ):
            return None
        return self.entity_description.extra_attrs_fn(self.coordinator.data)
