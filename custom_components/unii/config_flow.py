"""Config flow for the Alphatronics UNii integration."""

from __future__ import annotations

import asyncio
import logging
import socket
from typing import Any, Final

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.components import dhcp
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_TYPE
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import format_mac
from unii import DEFAULT_PORT, UNiiEncryptionError, UNiiLocal

from . import CONF_SHARED_KEY, CONF_TYPE_LOCAL, DOMAIN

_LOGGER: Final = logging.getLogger(__name__)


class CannotConnect(HomeAssistantError):
    # pylint: disable=too-few-public-methods
    """Error to indicate we cannot connect."""


class UNiiConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Alphatronics UNii."""

    VERSION = 1

    _discovered_ip: str | None = None
    _discovered_mac: str | None = None

    _reauth_entry: ConfigEntry | None = None

    LOCAL_SCHEMA: Final = vol.Schema(
        {
            vol.Required(CONF_HOST): str,
            vol.Required(CONF_PORT, default=DEFAULT_PORT): cv.port,
            vol.Required(CONF_SHARED_KEY): str,
        }
    )
    DISCOVERED_SCHEMA: Final = vol.Schema(
        {
            vol.Required(CONF_SHARED_KEY): str,
        }
    )
    REAUTH_SCHEMA = DISCOVERED_SCHEMA

    async def async_step_dhcp(self, discovery_info: dhcp.DhcpServiceInfo) -> FlowResult:
        """Handle DHCP discovery."""
        discovered_ip = discovery_info.ip
        discovered_mac = discovery_info.macaddress

        _LOGGER.debug(
            "DHCP discovery detected Alphatronics UNii on %s (%s)",
            discovered_ip,
            format_mac(discovered_mac),
        )

        config_entry = await self.async_set_unique_id(discovered_ip)
        if config_entry is not None and config_entry.domain == DOMAIN:
            self.hass.config_entries.async_update_entry(
                config_entry, unique_id=format_mac(discovered_mac)
            )

        await self.async_set_unique_id(format_mac(discovered_mac))
        self._abort_if_unique_id_configured(updates={CONF_HOST: discovered_ip})

        _LOGGER.debug("Alphatronics UNii on %s is not yet configured", discovered_ip)

        # After a reboot of the UNii the port is not yet open, wait a bit for the device to start
        await asyncio.sleep(10)

        # Test if the default port is open
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.connect((discovered_ip, DEFAULT_PORT))
            sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            _LOGGER.debug("Alphatronics UNii default port is not open")
            return self.async_abort(reason="cannot_connect")

        _LOGGER.debug("Alphatronics UNii default port is open")

        self._discovered_ip = discovered_ip
        self._discovered_mac = discovered_mac

        return await self.async_step_setup_local()

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
        if user_input is None and self._discovered_mac is not None:
            return self.async_show_form(
                step_id="setup_local",
                data_schema=self.DISCOVERED_SCHEMA,
            )
        if user_input is None and self._reauth_entry is not None:
            return self.async_show_form(
                step_id="setup_local",
                data_schema=self.REAUTH_SCHEMA,
            )
        if user_input is None:
            return self.async_show_form(
                step_id="setup_local",
                data_schema=self.LOCAL_SCHEMA,
            )

        errors: dict[str, str] = {}

        if self._discovered_ip is not None:
            host = self._discovered_ip
            port = DEFAULT_PORT
        elif self._reauth_entry is not None:
            host = self._reauth_entry.data[CONF_HOST]
            port = self._reauth_entry.data[CONF_PORT]
        else:
            host = user_input.get(CONF_HOST)
            port = user_input.get(CONF_PORT, DEFAULT_PORT)

        shared_key = user_input.get(CONF_SHARED_KEY, "")
        # shared_key = shared_key.strip()
        # Validate the shared key
        if shared_key == "":
            errors[CONF_SHARED_KEY] = "invalid_shared_key"
        else:
            # String must be 16 characters, padded with spaces.
            shared_key = shared_key[:16].ljust(16, " ")
            _LOGGER.debug('Shared key: "%s"', shared_key)

            shared_key = shared_key.encode()

            unii = UNiiLocal(host, port, shared_key)

            # Test if we can connect to the device.
            can_connect = False
            try:
                can_connect = await unii.test_connection()
                if not can_connect:
                    errors["base"] = "cannot_connect"
                    _LOGGER.error(
                        "Unable to connect to Alphatronics UNii on %s", unii.connection
                    )
            except UNiiEncryptionError:
                errors[CONF_SHARED_KEY] = "invalid_shared_key"

            if can_connect:
                await unii.disconnect()

                # Wait a bit for the UNii to accept new connections later in the async_setup_entry.
                await asyncio.sleep(1)

                # If reauthenticating only the existing configuration needs to updated with the
                # new shared key.
                if self._reauth_entry is not None:
                    return self.async_update_reload_and_abort(
                        self._reauth_entry,
                        data={
                            CONF_HOST: host,
                            CONF_PORT: port,
                            CONF_SHARED_KEY: shared_key.hex(),
                        },
                    )

                mac_address = None
                if self._discovered_mac is not None:
                    mac_address = format_mac(self._discovered_mac)
                elif unii.equipment_information.mac_address is not None:
                    # Newer versions of the UNii firmware provide the mac address in the Equipment
                    # Information.
                    mac_address = format_mac(unii.equipment_information.mac_address)

                if mac_address is not None:
                    # Use the mac address as unique config id.
                    await self.async_set_unique_id(format_mac(mac_address))
                    self._abort_if_unique_id_configured(
                        updates={
                            CONF_HOST: host,
                            CONF_PORT: port,
                            CONF_SHARED_KEY: shared_key.hex(),
                        }
                    )
                else:
                    # Fallback to the unique id of the connection (hostname) if the firmware does
                    # not provide a mac address.
                    await self.async_set_unique_id(unii.connection.unique_id)
                    self._abort_if_unique_id_configured()

                title = f"Alphatronics {unii.equipment_information.device_name}"
                data = {
                    CONF_TYPE: CONF_TYPE_LOCAL,
                    CONF_HOST: host,
                    CONF_PORT: port,
                    CONF_SHARED_KEY: shared_key.hex(),
                }
                return self.async_create_entry(title=title, data=data)

        if self._discovered_mac is not None:
            data_schema = self.add_suggested_values_to_schema(
                self.DISCOVERED_SCHEMA, user_input
            )
        elif self._reauth_entry is not None:
            data_schema = self.add_suggested_values_to_schema(
                self.REAUTH_SCHEMA, user_input
            )
        else:
            data_schema = self.add_suggested_values_to_schema(
                self.LOCAL_SCHEMA, user_input
            )

        return self.async_show_form(
            step_id="setup_local",
            data_schema=data_schema,
            errors=errors,
        )

    async def async_step_reauth(self, user_input=None):
        """Perform reauth upon an API authentication error."""
        self._reauth_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        _LOGGER.debug(
            "Reauthentication needed for Alphatronics UNii on %s", self._reauth_entry
        )
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        """Dialog that informs the user that reauth is required."""
        if user_input is None:
            return self.async_show_form(
                step_id="reauth_confirm",
                data_schema=vol.Schema({}),
            )
        return await self.async_step_user()
