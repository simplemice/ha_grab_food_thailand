"""Order parsing."""

from __future__ import annotations

import pytest

from custom_components.grab_food.const import ORDER_STATES
from custom_components.grab_food.coordinator import GrabFoodCoordinator


@pytest.fixture
def parse():
    c = GrabFoodCoordinator.__new__(GrabFoodCoordinator)
    return c._parse_order


@pytest.mark.parametrize(
    "raw",
    ["ON_THE_WAY", "weird state", "", None, 5, {"x": 1}],
)
async def test_status_always_valid_enum_option(parse, raw):
    data = parse({"id": "1", "state": raw}, {})
    assert data["status"] in ORDER_STATES


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("DELIVERING", "delivering"),
        ("picked up", "picked_up"),
        ("CANCELED", "cancelled"),
        ("COMPLETED", "delivered"),
    ],
)
async def test_status_mapping(parse, raw, expected):
    assert parse({"id": "1", "state": raw}, {})["status"] == expected


async def test_unknown_status_keeps_raw(parse):
    data = parse({"id": "1", "state": "SOMETHING_NEW"}, {})
    assert data["status"] == "unknown"
    assert data["status_raw"] == "SOMETHING_NEW"


async def test_bad_items_and_qty_do_not_crash(parse):
    data = parse(
        {"id": "1", "items": [{"name": "Pad Thai", "quantity": "2"}, "junk", None]},
        {},
    )
    assert data["item_names"] == ["2× Pad Thai"]
    assert data["item_count"] == 1


async def test_bad_price_does_not_crash(parse):
    assert parse({"id": "1", "total": {"amount": "n/a"}}, {})["total"] is None
    assert parse({"id": "1", "total": {"amount": "120.5"}}, {})["total"] == 120.5


async def test_zero_coordinates_kept(parse):
    data = parse({"id": "1", "driver": {"name": "A", "location": {"lat": 0, "lng": 0}}}, {})
    assert data["driver_latitude"] == 0 and data["driver_longitude"] == 0
