"""Config flow for the Alphatronics UNii integration."""

from __future__ import annotations

import logging
from typing import Any, Final

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_TYPE
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError

from . import CONF_SHARED_KEY, CONF_TYPE_LOCAL, DOMAIN
from .unii import DEFAULT_PORT, UNiiLocal

_LOGGER: Final = logging.getLogger(__name__)


class CannotConnect(HomeAssistantError):
    # pylint: disable=too-few-public-methods
    """Error to indicate we cannot connect."""


class UNiiConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Alphatronics UNii."""

    VERSION = 1

    LOCAL_SCHEMA: Final = vol.Schema(
        {
            vol.Required(CONF_HOST): str,
            vol.Required(CONF_PORT, default=DEFAULT_PORT): cv.port,
            vol.Required(CONF_SHARED_KEY): str,
        }
    )

    CONNECT_SCHEMA = vol.Schema({})

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        # pylint: disable=unused-argument
        """Handle the initial step."""
        # Currently only supporting a local UNii
        # Select CONF_TYPE
        # if user_input is not None:
        #     user_selection = user_input[CONF_TYPE]
        #     if user_selection == "Local":
        #         return await self.async_step_setup_local()
        #
        #     return await self.async_step_setup_online()
        #
        # list_of_types = ["Local", "Online"]
        # schema = vol.Schema({vol.Required(CONF_TYPE): vol.In(list_of_types)})
        # return self.async_show_form(step_id="user", data_schema=schema)

        return await self.async_step_setup_local()

    async def async_step_setup_local(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the setup local."""
        if user_input is None:
            return self.async_show_form(
                step_id="setup_local",
                data_schema=self.LOCAL_SCHEMA,
            )

        errors: dict[str, str] = {}

        host = user_input.get(CONF_HOST)
        port = user_input.get(CONF_PORT, DEFAULT_PORT)
        # ToDo: Test if the host exists?

        shared_key = user_input.get(CONF_SHARED_KEY, None)
        # ToDo: Validate the shared key?
        if shared_key is not None and shared_key.strip() == "":
            shared_key = None
        else:
            if len(shared_key) > 16:
                shared_key = shared_key[:16]

            # If the shared key is shorter than 16 bytes it's padded with spaces (0x20).
            while len(shared_key) < 16:
                shared_key += str(0x20)

            shared_key = shared_key.encode()

        unii = UNiiLocal(host, port, shared_key)

        # Test if we can connect to the device.
        if not await unii.connect():
            errors["base"] = "cannot_connect"
            _LOGGER.error(
                "Unable to connect to Alphatronics UNii on %s", unii.connection
            )
        else:
            await unii.disconnect()

            await self.async_set_unique_id(unii.unique_id)
            self._abort_if_unique_id_configured()

            title = f"Alphatronics {unii.equipment_information.device_name} on {unii.connection}"
            data = {
                CONF_TYPE: CONF_TYPE_LOCAL,
                CONF_HOST: host,
                CONF_PORT: port,
                CONF_SHARED_KEY: shared_key.hex(),
            }
            return self.async_create_entry(title=title, data=data)

        return self.async_show_form(
            step_id="setup_local",
            data_schema=self.LOCAL_SCHEMA,
            errors=errors,
        )
