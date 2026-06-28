"""Config flow for Grab Food Thailand integration."""

from __future__ import annotations

import logging
import time
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import GrabApiError, GrabAuthError, GrabFoodApiClient
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_COUNTRY_CODE,
    CONF_OTP,
    CONF_PHONE,
    CONF_REFRESH_TOKEN,
    CONF_TOKEN_EXPIRY,
    DEFAULT_COUNTRY_CODE,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

STEP_TOKEN_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_ACCESS_TOKEN): str,
        vol.Optional(CONF_REFRESH_TOKEN, default=""): str,
    }
)

# Kept for possible future use but not exposed from the main user flow.
STEP_PHONE_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_COUNTRY_CODE, default=DEFAULT_COUNTRY_CODE): str,
        vol.Required(CONF_PHONE): str,
    }
)

STEP_OTP_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_OTP): str,
    }
)


class GrabFoodConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Grab Food Thailand."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._phone: str = ""
        self._country_code: str = DEFAULT_COUNTRY_CODE
        self._client: GrabFoodApiClient | None = None
        self._is_reauth: bool = False
        self._reauth_entry_id: str | None = None

    # ── Entry point ───────────────────────────────────────────────────────

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Go directly to the browser-token step.

        OTP phone login is not exposed here because Grab's API currently
        requires an undocumented clientId from the official mobile app.
        """
        return await self.async_step_token()

    # ── Browser token flow ────────────────────────────────────────────────

    async def async_step_token(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Paste access_token extracted from food.grab.com browser storage."""
        errors: dict[str, str] = {}

        if user_input is not None:
            access_token = user_input[CONF_ACCESS_TOKEN].strip()
            refresh_token = user_input.get(CONF_REFRESH_TOKEN, "").strip()

            if not self._is_reauth:
                uid = f"grab_food_token_{access_token[:16]}"
                await self.async_set_unique_id(uid)
                self._abort_if_unique_id_configured()

            session = async_get_clientsession(self.hass)
            client = GrabFoodApiClient(
                session=session,
                access_token=access_token,
                refresh_token=refresh_token,
                token_expiry=time.time() + 3600,
            )

            try:
                await client.get_active_orders()
            except GrabAuthError:
                errors["base"] = "invalid_token"
            except GrabApiError as err:
                _LOGGER.warning("Token check API error (continuing): %s", err)
            except Exception:
                _LOGGER.exception("Unexpected error during token validation")
                errors["base"] = "cannot_connect"

            if not errors:
                entry_data = {
                    CONF_PHONE: self._phone,
                    CONF_COUNTRY_CODE: self._country_code,
                    CONF_ACCESS_TOKEN: access_token,
                    CONF_REFRESH_TOKEN: refresh_token,
                    CONF_TOKEN_EXPIRY: client.token_expiry,
                }

                if self._is_reauth:
                    existing = self.hass.config_entries.async_get_entry(
                        self._reauth_entry_id
                    )
                    return self.async_update_reload_and_abort(
                        existing,
                        data_updates=entry_data,
                    )

                return self.async_create_entry(
                    title="Grab Food (token)",
                    data=entry_data,
                )

        return self.async_show_form(
            step_id="token",
            data_schema=STEP_TOKEN_SCHEMA,
            errors=errors,
        )

    # ── OTP flow (internal — not reachable from user step) ────────────────

    async def async_step_phone(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step OTP-1: Collect phone number and send OTP."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._country_code = user_input[CONF_COUNTRY_CODE].strip()
            self._phone = user_input[CONF_PHONE].strip().lstrip("0")

            await self.async_set_unique_id(f"grab_food_{self._country_code}{self._phone}")
            self._abort_if_unique_id_configured()

            session = async_get_clientsession(self.hass)
            self._client = GrabFoodApiClient(session)

            try:
                await self._client.request_otp(self._phone, self._country_code)
                return await self.async_step_otp()
            except GrabApiError:
                errors["base"] = "otp_send_failed"
            except GrabAuthError:
                errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="phone",
            data_schema=STEP_PHONE_SCHEMA,
            errors=errors,
            description_placeholders={"default_code": DEFAULT_COUNTRY_CODE},
        )

    async def async_step_otp(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step OTP-2: Verify OTP and store tokens."""
        errors: dict[str, str] = {}

        if user_input is not None:
            otp = user_input[CONF_OTP].strip()

            if self._client is None:
                errors["base"] = "unknown"
                return self.async_show_form(
                    step_id="otp",
                    data_schema=STEP_OTP_SCHEMA,
                    errors=errors,
                )
            try:
                token_data = await self._client.verify_otp(
                    self._phone, otp, self._country_code
                )
            except GrabAuthError:
                errors["base"] = "invalid_otp"
            else:
                entry_data = {
                    CONF_PHONE: self._phone,
                    CONF_COUNTRY_CODE: self._country_code,
                    CONF_ACCESS_TOKEN: token_data["access_token"],
                    CONF_REFRESH_TOKEN: token_data.get("refresh_token", ""),
                    CONF_TOKEN_EXPIRY: self._client.token_expiry,
                }

                if self._is_reauth:
                    existing = self.hass.config_entries.async_get_entry(
                        self._reauth_entry_id
                    )
                    return self.async_update_reload_and_abort(
                        existing,
                        data_updates=entry_data,
                    )

                return self.async_create_entry(
                    title=f"Grab Food ({self._country_code}{self._phone})",
                    data=entry_data,
                )

        return self.async_show_form(
            step_id="otp",
            data_schema=STEP_OTP_SCHEMA,
            errors=errors,
            description_placeholders={
                "phone": f"{self._country_code}{self._phone}",
            },
        )

    # ── Reauth ────────────────────────────────────────────────────────────

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> ConfigFlowResult:
        """Handle re-authentication — update the existing entry, not create a new one."""
        self._is_reauth = True
        self._reauth_entry_id = self.context["entry_id"]
        self._phone = entry_data.get(CONF_PHONE, "")
        self._country_code = entry_data.get(CONF_COUNTRY_CODE, DEFAULT_COUNTRY_CODE)
        return await self.async_step_token()
