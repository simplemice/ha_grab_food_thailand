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

STEP_TOKEN_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_ACCESS_TOKEN): str,
        vol.Optional(CONF_REFRESH_TOKEN, default=""): str,
        vol.Optional(CONF_PHONE, default=""): str,
        vol.Optional(CONF_COUNTRY_CODE, default=DEFAULT_COUNTRY_CODE): str,
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

    # ── Entry point: choose auth method ──────────────────────────────────

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show menu: OTP login or manual token."""
        return self.async_show_menu(
            step_id="user",
            menu_options=["phone", "token"],
        )

    # ── OTP flow ─────────────────────────────────────────────────────────

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
                return self.async_create_entry(
                    title=f"Grab Food ({self._country_code}{self._phone})",
                    data={
                        CONF_PHONE: self._phone,
                        CONF_COUNTRY_CODE: self._country_code,
                        CONF_ACCESS_TOKEN: token_data["access_token"],
                        CONF_REFRESH_TOKEN: token_data.get("refresh_token", ""),
                        CONF_TOKEN_EXPIRY: self._client.token_expiry,
                    },
                )

        return self.async_show_form(
            step_id="otp",
            data_schema=STEP_OTP_SCHEMA,
            errors=errors,
            description_placeholders={
                "phone": f"{self._country_code}{self._phone}",
            },
        )

    # ── Manual token flow ─────────────────────────────────────────────────

    async def async_step_token(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Alternative: paste access_token extracted from browser/app."""
        errors: dict[str, str] = {}

        if user_input is not None:
            access_token = user_input[CONF_ACCESS_TOKEN].strip()
            refresh_token = user_input.get(CONF_REFRESH_TOKEN, "").strip()
            phone = user_input.get(CONF_PHONE, "").strip().lstrip("0")
            country_code = user_input.get(CONF_COUNTRY_CODE, DEFAULT_COUNTRY_CODE).strip()

            uid = f"grab_food_{country_code}{phone}" if phone else f"grab_food_token_{access_token[:16]}"
            await self.async_set_unique_id(uid)
            self._abort_if_unique_id_configured()

            session = async_get_clientsession(self.hass)
            client = GrabFoodApiClient(
                session=session,
                access_token=access_token,
                refresh_token=refresh_token,
                # Set expiry far in the future; coordinator will refresh as needed
                token_expiry=time.time() + 3600,
            )

            # Quick connectivity check
            try:
                await client.get_active_orders()
            except GrabAuthError:
                errors["base"] = "invalid_token"
            except GrabApiError as err:
                _LOGGER.warning("Token check API error (continuing anyway): %s", err)
            except Exception:
                errors["base"] = "cannot_connect"

            if not errors:
                title = (
                    f"Grab Food ({country_code}{phone})"
                    if phone
                    else "Grab Food (token)"
                )
                return self.async_create_entry(
                    title=title,
                    data={
                        CONF_PHONE: phone,
                        CONF_COUNTRY_CODE: country_code,
                        CONF_ACCESS_TOKEN: access_token,
                        CONF_REFRESH_TOKEN: refresh_token,
                        CONF_TOKEN_EXPIRY: client.token_expiry,
                    },
                )

        return self.async_show_form(
            step_id="token",
            data_schema=STEP_TOKEN_SCHEMA,
            errors=errors,
        )

    # ── Reauth ────────────────────────────────────────────────────────────

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> ConfigFlowResult:
        """Handle re-authentication when tokens expire permanently."""
        self._phone = entry_data.get(CONF_PHONE, "")
        self._country_code = entry_data.get(CONF_COUNTRY_CODE, DEFAULT_COUNTRY_CODE)
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm re-auth: choose OTP or paste a new token."""
        return self.async_show_menu(
            step_id="reauth_confirm",
            menu_options=["phone", "token"],
            description_placeholders={"phone": f"{self._country_code}{self._phone}"},
        )
