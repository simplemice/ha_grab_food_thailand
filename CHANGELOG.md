# Changelog

## [1.0.1] - 2026-06-28

### Initial commit

### Temporarily remove workflow

### Initial commit


## [1.0.0] - 2026-06-28

### Initial release

- OTP-based authentication via Grab's phone/SMS flow
- 9 sensors: order status, restaurant name, order total, ETA, driver name, driver plate, item count, order ID, delivery address
- Adaptive polling — 30 s when an order is active, 5 min when idle
- Automatic token refresh with persistence across HA restarts
- Reauth flow triggered automatically when tokens expire permanently
- HACS support via hacs.json
