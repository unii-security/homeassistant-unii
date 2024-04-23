"""The Alhpatronics UNii integration for Home Assistant"""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any, Callable

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_TYPE, Platform
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ConfigEntryError, ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import CONF_SHARED_KEY, CONF_TYPE_LOCAL, DOMAIN
from .unii import UNii, UNiiCommand, UNiiData, UNiiLocal

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
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

    def __init__(self, hass, unii: UNii):
        """Initialize Alphatronics UNii Data Update Coordinator."""

        super().__init__(
            hass,
            _LOGGER,
            # Name of the data. For logging purposes.
            name=__name__,
        )

        self.unii = unii

        # Create the device if not exists
        # device_registry = dr.async_get(hass)
        # device_entry = device_registry.async_get_or_create(
        #     config_entry_id=entry.entry_id,
        #     identifiers={(DOMAIN, unii.unique_id)},
        #     name=f"Alphatronics {unii.equipment_information.device_name} on {unii.connection}",
        #     manufacturer="Alphatronics",
        #     sw_version = unii.equipment_information.software_version,
        # )

        # ToDo: Get device info from Device Entry?
        self.device_info = DeviceInfo(
            identifiers={(DOMAIN, unii.unique_id)},
            name=f"Alphatronics {unii.equipment_information.device_name} on {unii.connection}",
            manufacturer="Alphatronics",
            sw_version=unii.equipment_information.software_version,
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

        self.async_set_updated_data({"command": command, "data": data})

        # For when events are going to be implemented
        # event_data = {}
        # self.hass.bus.async_fire(f"{DOMAIN}_event", event_data)

    async def _async_update_data(self):
        """Fetch data from Alphatronics UNii."""


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Alphatronics UNii from a config entry."""
    unii = None

    conf_type = CONF_TYPE_LOCAL
    if CONF_TYPE in entry.data:
        conf_type = entry.data[CONF_TYPE]

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

    # Setup coordinator
    coordinator = UNiiCoordinator(hass, unii)

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
