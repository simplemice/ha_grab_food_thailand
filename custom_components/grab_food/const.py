"""Constants for the Grab Food Thailand integration."""

from datetime import timedelta

DOMAIN = "grab_food"

# ── Grab API ─────────────────────────────────────────────────────────────────
GRAB_API_BASE = "https://api.grab.com"
GRAB_AUTH_BASE = "https://api.grab.com/grabid/v1"
GRAB_FOOD_BASE = "https://food.grab.com/api"

# Auth endpoints
GRAB_OTP_REQUEST = f"{GRAB_AUTH_BASE}/phone/otp"
GRAB_OTP_VERIFY = f"{GRAB_AUTH_BASE}/phone/otp/verify"
GRAB_TOKEN_REFRESH = f"{GRAB_AUTH_BASE}/oauth2/token"

# Food endpoints
GRAB_ORDERS_ACTIVE = f"{GRAB_FOOD_BASE}/v2/orders/active"
GRAB_ORDERS_HISTORY = f"{GRAB_FOOD_BASE}/v2/orders/history"
GRAB_ORDER_DETAIL = f"{GRAB_FOOD_BASE}/v2/orders"  # + /{order_id}

# ── Config keys ──────────────────────────────────────────────────────────────
CONF_PHONE = "phone_number"
CONF_COUNTRY_CODE = "country_code"
CONF_OTP = "otp"
CONF_ACCESS_TOKEN = "access_token"
CONF_REFRESH_TOKEN = "refresh_token"
CONF_TOKEN_EXPIRY = "token_expiry"

# ── Defaults ─────────────────────────────────────────────────────────────────
DEFAULT_COUNTRY_CODE = "+66"  # Thailand
DEFAULT_SCAN_INTERVAL = timedelta(seconds=30)
SCAN_INTERVAL_IDLE = timedelta(minutes=5)
SCAN_INTERVAL_ACTIVE = timedelta(seconds=30)

# ── Sensor keys ──────────────────────────────────────────────────────────────
SENSOR_ORDER_STATUS = "order_status"
SENSOR_RESTAURANT_NAME = "restaurant_name"
SENSOR_ORDER_TOTAL = "order_total"
SENSOR_ETA = "estimated_delivery"
SENSOR_DRIVER_NAME = "driver_name"
SENSOR_DRIVER_PLATE = "driver_plate"
SENSOR_ITEM_COUNT = "item_count"
SENSOR_ORDER_ID = "order_id"
SENSOR_LAST_ORDER_STATUS = "last_order_status"
SENSOR_DELIVERY_ADDRESS = "delivery_address"

# ── Order states ─────────────────────────────────────────────────────────────
ORDER_STATES = [
    "no_active_order",
    "placed",
    "confirmed",
    "preparing",
    "driver_assigned",
    "picked_up",
    "delivering",
    "delivered",
    "cancelled",
]

# ── Attribution ──────────────────────────────────────────────────────────────
ATTRIBUTION = "Data provided by Grab Food Thailand"
