"""Config flow for Grab Food Thailand integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import GrabAuthError, GrabFoodApiClient
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


class GrabFoodConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Grab Food Thailand."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._phone: str = ""
        self._country_code: str = DEFAULT_COUNTRY_CODE
        self._client: GrabFoodApiClient | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 1: Collect phone number and send OTP."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._country_code = user_input[CONF_COUNTRY_CODE].strip()
            self._phone = user_input[CONF_PHONE].strip().lstrip("0")

            # Check for duplicates
            await self.async_set_unique_id(f"grab_food_{self._country_code}{self._phone}")
            self._abort_if_unique_id_configured()

            session = async_get_clientsession(self.hass)
            self._client = GrabFoodApiClient(session)

            if await self._client.request_otp(self._phone, self._country_code):
                return await self.async_step_otp()

            errors["base"] = "otp_send_failed"

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_PHONE_SCHEMA,
            errors=errors,
            description_placeholders={"default_code": DEFAULT_COUNTRY_CODE},
        )

    async def async_step_otp(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 2: Verify OTP and store tokens."""
        errors: dict[str, str] = {}

        if user_input is not None:
            otp = user_input[CONF_OTP].strip()
            assert self._client is not None

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
        """Confirm re-auth and send a new OTP."""
        if user_input is not None:
            session = async_get_clientsession(self.hass)
            self._client = GrabFoodApiClient(session)
            if await self._client.request_otp(self._phone, self._country_code):
                return await self.async_step_otp()

        return self.async_show_form(
            step_id="reauth_confirm",
            description_placeholders={
                "phone": f"{self._country_code}{self._phone}",
            },
        )
