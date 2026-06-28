# Changelog

## [1.0.12] - 2026-06-28

### add brand icons and screenshot


## [1.0.11] - 2026-06-28

### docs: replace browser token method with HTTPCanary step-by-step guide


## [1.0.10] - 2026-06-28

### fix: handle API redirect and non-JSON response; don't block setup on API errors

- api.py: add allow_redirects=False to detect Grab API endpoint changes;
  add _parse_json helper to raise a clear error on HTML/non-JSON responses
- coordinator.py: on GrabApiError return empty data instead of UpdateFailed
  so sensors stay available and setup succeeds even when API endpoint is wrong


## [1.0.9] - 2026-06-28

### fix: resolve 500 error caused by _reauth_entry_id property conflict

In newer HA versions ConfigFlow defines _reauth_entry_id as a read-only
property. Setting it in __init__ raised AttributeError which HA caught
and returned as a 500 on config flow load.

Fixes:
- Remove __init__ entirely; use self.source == SOURCE_REAUTH instead
  of custom _is_reauth flag, and self._get_reauth_entry() instead of
  manually tracking _reauth_entry_id
- Move DeviceInfo import in sensor.py from deprecated
  homeassistant.helpers.entity to homeassistant.helpers.device_registry


## [1.0.8] - 2026-06-28

### fix autorization and other bugs


## [1.0.7] - 2026-06-28

### fix: collapse config flow to single user step, fix 500 error

async_step_user now owns the token form directly with step_id='user'.
Previous design redirected user->token step which caused a step_id
mismatch that HA flow loader rejected with 500. Removed async_step_token
and ConfigFlowResult import; strings.json now has one step (user) with
the token fields, matching exactly what the code shows.


## [1.0.6] - 2026-06-28

### fix: remove phone/OTP flow, fix config flow 500 error

- Remove async_step_phone, async_step_otp and all OTP schemas — they
  caused a 500 because newer HA validates async_step_* methods against
  strings.json and those steps had no strings entries
- Add required 'user' step to strings.json (HA needs it as the flow
  entry-point declaration)
- Remove unused CONF_OTP constant from const.py
- Flow now goes directly user→token, no menu, no phone


## [1.0.5] - 2026-06-28

### fix autorization and other bugs


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
