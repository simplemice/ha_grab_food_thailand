"""Config flow for Grab Food Thailand integration."""

from __future__ import annotations

import logging
import time
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import SOURCE_REAUTH, ConfigFlow
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import GrabApiError, GrabAuthError, GrabFoodApiClient
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_REFRESH_TOKEN,
    CONF_TOKEN_EXPIRY,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

STEP_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_ACCESS_TOKEN): str,
        vol.Optional(CONF_REFRESH_TOKEN, default=""): str,
    }
)


class GrabFoodConfigFlow(ConfigFlow, domain=DOMAIN):
    """Config flow for Grab Food Thailand — token only."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Show the access-token form and validate on submit."""
        errors: dict[str, str] = {}
        is_reauth = self.source == SOURCE_REAUTH

        if user_input is not None:
            access_token = user_input[CONF_ACCESS_TOKEN].strip()
            refresh_token = user_input.get(CONF_REFRESH_TOKEN, "").strip()

            if not is_reauth:
                uid = f"grab_food_{access_token[:20]}"
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
                _LOGGER.warning("Token validation API error (non-fatal): %s", err)
            except Exception:
                _LOGGER.exception("Unexpected error during token validation")
                errors["base"] = "cannot_connect"

            if not errors:
                entry_data = {
                    CONF_ACCESS_TOKEN: access_token,
                    CONF_REFRESH_TOKEN: refresh_token,
                    CONF_TOKEN_EXPIRY: client.token_expiry,
                }

                if is_reauth:
                    return self.async_update_reload_and_abort(
                        self._get_reauth_entry(),
                        data_updates=entry_data,
                    )

                return self.async_create_entry(title="Grab Food", data=entry_data)

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_SCHEMA,
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]):
        """Handle re-auth: update existing entry, never create a duplicate."""
        return await self.async_step_user()
