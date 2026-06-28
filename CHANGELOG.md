# Changelog

## [1.0.4] - 2026-06-28

### fix autorization and other bugs

### fix autorization and other bugs

### fix autorization and other

### fix request_otp and other

### fix request_otp and other


## [1.0.3] - 2026-06-28

### Added
- Manual token authentication — new "Paste token from browser / app" option in the setup menu bypasses the OTP flow entirely
- Auth method menu at setup start: choose between OTP or manual token
- Reauth now also offers both methods
- `invalid_token` error shown when a pasted token is rejected by Grab

### Fixed
- OTP flow diagnostic confirmed Grab API returns HTTP 400 for all request variations — the API requires an undocumented `clientId` from the official mobile app; the manual token path works around this
- Removed leftover `assert` in OTP verify step

## [1.0.2] - 2026-06-28

### add License


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
