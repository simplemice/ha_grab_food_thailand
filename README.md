# Grab Food Thailand — Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/release/simplemice/ha-grab-food.svg)](https://github.com/simplemice/ha-grab-food/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Track your active Grab Food Thailand orders directly inside Home Assistant — order status, restaurant, ETA, driver info, item list, and more.

---

## Features

- **Browser token authentication** — copy your token from food.grab.com (no app needed)
- **9 sensors** covering the full order lifecycle
- **Adaptive polling** — 30 s while an order is active, 5 min when idle
- **Automatic token refresh** — sessions persist across Home Assistant restarts
- **Reauth flow** — triggered automatically when tokens expire
- **HACS ready** — one-click install via HACS custom repository

---

## Installation

### HACS (recommended)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=simplemice&repository=ha-grab-food&category=integration)

Or manually:

1. Open HACS → **Integrations** → ⋮ → **Custom repositories**
2. Add `https://github.com/simplemice/ha-grab-food` — category **Integration**
3. Search for **Grab Food Thailand** and click **Download**
4. Restart Home Assistant

### Manual

1. Download the latest release ZIP from [GitHub Releases](https://github.com/simplemice/ha-grab-food/releases)
2. Extract and copy `custom_components/grab_food/` to your HA `config/custom_components/` directory
3. Restart Home Assistant

---

## Setup

### Step 1 — Get your Grab token from the browser

1. Open **[food.grab.com](https://food.grab.com)** in Chrome or Firefox
2. Log in with your Grab account (phone + OTP via the website)
3. Press **F12** to open DevTools
4. Go to **Application** tab → **Local Storage** → `https://food.grab.com`
5. Find the key `access_token` and copy its full value

> **Tip:** The token is a long string starting with `eyJ...`. Copy the entire value — it can be several hundred characters long.

### Step 2 — Add the integration in Home Assistant

1. Go to **Settings → Devices & Services → Add Integration**
2. Search for **Grab Food Thailand**
3. Choose **"Paste token from browser / app"**
4. Paste your `access_token` into the **Access token** field
5. Click **Submit** — all sensors appear under a **Grab Food** device

### Token expiry & reauth

When the token expires, Home Assistant will show a notification to re-authenticate. Open the integration, choose your preferred method, and paste a fresh token from the browser.

> **Note on OTP login:** The integration also includes a phone/OTP login option, but Grab's API currently requires an undocumented `clientId` from the official mobile app to accept OTP requests. Use the browser token method above — it works reliably.

---

## Sensors

| Sensor | Entity key | Description | Extra attributes |
|---|---|---|---|
| Order Status | `order_status` | Enum — see states below | `order_id` |
| Restaurant | `restaurant_name` | Restaurant name | — |
| Order Total | `order_total` | Price in THB | `currency` |
| Estimated Delivery | `estimated_delivery` | ISO timestamp or "X min" | `raw_eta` |
| Driver | `driver_name` | Driver's name | `latitude`, `longitude` |
| Driver Plate | `driver_plate` | Vehicle license plate | — |
| Items Ordered | `item_count` | Number of items | `items` (list of names) |
| Order ID | `order_id` | Grab order identifier | — |
| Delivery Address | `delivery_address` | Delivery destination | — |

### Order Status states

| State | Meaning |
|---|---|
| `no_active_order` | No order in progress |
| `placed` | Order submitted |
| `confirmed` | Restaurant accepted |
| `preparing` | Food being prepared |
| `driver_assigned` | Driver picked for delivery |
| `picked_up` | Driver collected food |
| `delivering` | En route to you |
| `delivered` | Order delivered |
| `cancelled` | Order cancelled |

---

## Automation examples

### Announce when food is picked up

```yaml
trigger:
  - platform: state
    entity_id: sensor.grab_food_order_status
    to: "picked_up"
action:
  - service: tts.speak
    data:
      message: >
        Your order from {{ states('sensor.grab_food_restaurant_name') }}
        has been picked up. ETA: {{ states('sensor.grab_food_estimated_delivery') }}.
```

### Notify on delivery

```yaml
trigger:
  - platform: state
    entity_id: sensor.grab_food_order_status
    to: "delivered"
action:
  - service: notify.mobile_app
    data:
      title: "Food delivered!"
      message: >
        {{ states('sensor.grab_food_restaurant_name') }} —
        {{ states('sensor.grab_food_order_total') }} THB
        ({{ states('sensor.grab_food_item_count') }} items)
```

### Show driver on a map card

```yaml
type: map
entities:
  - entity: sensor.grab_food_driver_name
    attribute: latitude
  - entity: sensor.grab_food_driver_name
    attribute: longitude
```

---

## Architecture

```
config_flow.py  →  Menu: browser token OR phone OTP → tokens stored in config entry
__init__.py     →  Creates API client + coordinator; forwards to platforms
coordinator.py  →  Polls Grab API, adaptive interval, persists refreshed tokens
sensor.py       →  9 CoordinatorEntity sensors with extra state attributes
api.py          →  Async Grab API client (auth, token refresh, order fetch)
```

---

## Important notes

- **Unofficial API** — this integration uses Grab's internal mobile API. Endpoints and field names can change without notice.
- **Rate limiting** — Grab may throttle aggressive polling. The defaults (30 s active / 5 min idle) are intentionally conservative.
- **One active order** — Grab Food only allows one active food order at a time; the integration always tracks the first one returned.
- **Thailand focus** — default country code is `+66`; the token method works regardless of country.

---

## License

[MIT](LICENSE)
