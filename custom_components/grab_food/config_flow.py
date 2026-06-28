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


class GrabFoodConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Grab Food Thailand."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._is_reauth: bool = False
        self._reauth_entry_id: str | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Entry point — skip straight to the token step."""
        return await self.async_step_token(user_input)

    async def async_step_token(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Accept an access token pasted from the browser or HTTPCanary."""
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
                _LOGGER.warning("Token check API error (non-fatal): %s", err)
            except Exception:
                _LOGGER.exception("Unexpected error during token validation")
                errors["base"] = "cannot_connect"

            if not errors:
                entry_data = {
                    CONF_PHONE: "",
                    CONF_COUNTRY_CODE: DEFAULT_COUNTRY_CODE,
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
                    title="Grab Food",
                    data=entry_data,
                )

        return self.async_show_form(
            step_id="token",
            data_schema=STEP_TOKEN_SCHEMA,
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> ConfigFlowResult:
        """Re-auth flow — update the existing entry instead of creating a new one."""
        self._is_reauth = True
        self._reauth_entry_id = self.context["entry_id"]
        return await self.async_step_token()
