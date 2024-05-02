# pylint: disable=R0801
"""
Creates Switch entities for the UNii Home Assistant integration.
"""
import logging

from homeassistant.components.switch import (SwitchDeviceClass, SwitchEntity,
                                             SwitchEntityDescription)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import UNDEFINED
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import DOMAIN, UNiiCoordinator
from .unii import (UNiiCommand, UNiiOutputState, UNiiOututStatusRecord,
                   UNiiSection, UNiiSectionArmedState)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the UNii switches."""
    coordinator: UNiiCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    entities = []

    for _, output in coordinator.unii.outputs.items():
    #     if "status" in output and output.status not in [
    #         None,
    #         UNiiInputState.DISABLED,
    #     ]:
    #         entity_description = BinarySensorEntityDescription(
    #             key=f"input{output.number}-binary",
    #             device_class=BinarySensorDeviceClass.TAMPER,
    #         )
    #         entities.append(
    #             UNiiInputBinarySensor(
    #                 coordinator, entity_description, output.number
    #             )
    #         )

    async_add_entities(entities)


class UNiiSwitch(CoordinatorEntity, SwitchEntity):
    # pylint: disable=too-few-public-methods
    """
    Base UNii Switch.
    """
    _attr_has_entity_name = True
    _attr_available = False
    _attr_is_on = None

    def __init__(
        self,
        coordinator: UNiiCoordinator,
        entity_description: SwitchEntityDescription,
    ):
        """Initialize the switch."""
        super().__init__(coordinator, entity_description.key)

        self._attr_device_info = coordinator.device_info
        self._attr_unique_id = f"{coordinator.unii.unique_id}-{entity_description.key}"
        if entity_description.name != UNDEFINED:
            self._attr_name = entity_description.name

        self.entity_description = entity_description
