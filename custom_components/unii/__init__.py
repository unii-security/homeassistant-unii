"""The Alhpatronics UNii integration for Home Assistant"""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any, Callable

import homeassistant.helpers.config_validation as cv
import homeassistant.helpers.device_registry as dr
import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_TYPE, Platform
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ConfigEntryError, ConfigEntryNotReady
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import CONF_SHARED_KEY, CONF_TYPE_LOCAL, DOMAIN
from .unii import UNii, UNiiCommand, UNiiData, UNiiLocal

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.ALARM_CONTROL_PANEL,
    Platform.BINARY_SENSOR,
    Platform.SENSOR,
    # Platform.SWITCH,
    # Platform.SELECT,
    # Platform.NUMBER,
]


class UNiiCoordinator(DataUpdateCoordinator):
    """Alphatronics UNii Data Update Coordinator."""

    unii: UNii = None
    device_info: DeviceInfo = None

    def __init__(self, hass: HomeAssistant, unii: UNii, config_entry: ConfigEntry):
        """Initialize Alphatronics UNii Data Update Coordinator."""

        super().__init__(
            hass,
            _LOGGER,
            # Name of the data. For logging purposes.
            name=__name__,
        )

        self.unii = unii
        self.config_entry_id = config_entry.entry_id

        identifiers = set()
        connections = set()
        mac_address = None
        if unii.equipment_information.mac_address is not None:
            mac_address = dr.format_mac(unii.equipment_information.mac_address)
        elif len(config_entry.unique_id) == 17 and config_entry.unique_id.count(":") == 5:
            # Older versions of the firmware don't return the mac address in the Equipment
            # Information. Test if the config entry uses a mac address as unique id and use that
            # instead.
            mac_address = dr.format_mac(config_entry.unique_id)

        if mac_address is not None:
            identifiers.add((DOMAIN, mac_address))
            connections.add((dr.CONNECTION_NETWORK_MAC, mac_address))
        else:
            # If no mac address us know use the unique id of the connection (hostname) as an
            # identifier.
            identifiers.add((DOMAIN, unii.connection.unique_id))

        self.device_info = DeviceInfo(
            configuration_url="https://unii-security.com/",
            connections=connections,
            identifiers=identifiers,
            manufacturer="Alphatronics",
            model="UNii",
            name=unii.equipment_information.device_name,
            serial_number=unii.equipment_information.serial_number,
            sw_version=str(unii.equipment_information.software_version),
            translation_key="unii",
            translation_placeholders={
                "device_name": unii.equipment_information.device_name,
                "connection": unii.connection.unique_id,
            },
        )

        self.unii.add_event_occurred_callback(self.event_occurred_callback)

    async def async_disconnect(self):
        """
        Disconnect from UNii.

        To be called when coordinator is unloaded, e.g. when device is removed or HA is shutdown.
        """
        await self.unii.disconnect()
        _LOGGER.debug("Disconnected from Alphatronics UNii")

    @callback
    def event_occurred_callback(self, command: UNiiCommand, data: UNiiData):
        """Callback to be called by UNii library whenever an event occurs."""

        # Reload the configuration on disconnect
        if command in [
            UNiiCommand.RELOAD_CONFIGURATION,
        ]:
            self.hass.config_entries.async_schedule_reload(self.config_entry_id)
            return

        if command in [
            UNiiCommand.CONNECTION_REQUEST_RESPONSE,
            UNiiCommand.POLL_ALIVE_RESPONSE,
            UNiiCommand.NORMAL_DISCONNECT,
            UNiiCommand.EVENT_OCCURRED,
            UNiiCommand.INPUT_STATUS_CHANGED,
            UNiiCommand.RESPONSE_REQUEST_SECTION_STATUS,
            UNiiCommand.INPUT_STATUS_UPDATE,
            UNiiCommand.RESPONSE_REQUEST_INPUT_ARRANGEMENT,
        ]:
            self.async_set_updated_data({"command": command, "data": data})

        # For when events are going to be implemented
        # event_data = {}
        # self.hass.bus.async_fire(f"{DOMAIN}_event", event_data)

    async def _async_update_data(self):
        """Fetch data from Alphatronics UNii."""


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Alphatronics UNii from a config entry."""
    unii = None

    conf_type = entry.data.get(CONF_TYPE, CONF_TYPE_LOCAL)

    if conf_type == CONF_TYPE_LOCAL:
        host = entry.data[CONF_HOST]
        port = entry.data[CONF_PORT]
        unii = UNiiLocal(host, port, entry.data[CONF_SHARED_KEY])

        # Open the connection.
        if not await unii.connect():
            raise ConfigEntryNotReady(
                f"Unable to connect to Alphatronics UNii on {unii.connection}"
            )
    else:
        raise ConfigEntryError(
            f"Config type {conf_type} not supported for Alphatronics UNii"
        )

    if (
        unii.equipment_information.mac_address is not None
        and entry.unique_id == unii.connection.unique_id
    ):
        # The config entry uses the old unique id of the connection, the firmware has probably
        # been upgraded.
        _LOGGER.debug("Updating config entry")
        hass.config_entries.async_update_entry(
            entry, unique_id=unii.equipment_information.mac_address
        )

    # Setup coordinator
    coordinator = UNiiCoordinator(hass, unii, entry)

    # Fetch initial data so we have data when entities subscribe
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    await coordinator.async_request_refresh()

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    coordinator: UNiiCoordinator = hass.data[DOMAIN][entry.entry_id]
    await coordinator.async_disconnect()

    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
