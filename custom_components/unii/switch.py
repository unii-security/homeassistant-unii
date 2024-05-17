# pylint: disable=R0801
"""
Creates Switch entities for the UNii Home Assistant integration.
"""
import logging

from homeassistant.components.switch import (
    SwitchDeviceClass,
    SwitchEntity,
    SwitchEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import UNDEFINED
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import DOMAIN, UNiiCoordinator
from .unii import UNiiCommand, UNiiFeature, UNiiOutputType

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the UNii switches."""
    coordinator: UNiiCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    entities = []

    if UNiiFeature.SET_OUTPUT in coordinator.unii.features:
        for _, output in coordinator.unii.outputs.items():
            if "status" in output and output.status not in [
                None,
                UNiiOutputType.NOT_ACTIVE,
            ]:
                if output.name is None:
                    entity_description = SwitchEntityDescription(
                        key=f"output{output.number}-switch",
                        device_class=SwitchDeviceClass.SWITCH,
                    )
                else:
                    entity_description = SwitchEntityDescription(
                        key=f"output{output.number}-switch",
                        device_class=SwitchDeviceClass.SWITCH,
                        name=output.name,
                    )
                entities.append(
                    UNiiOutputSwitch(
                        coordinator,
                        entity_description,
                        config_entry.entry_id,
                        output.number,
                    )
                )

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
        config_entry_id: str,
    ):
        """Initialize the switch."""
        super().__init__(coordinator, entity_description.key)

        self._attr_device_info = coordinator.device_info
        self._attr_unique_id = f"{config_entry_id}-{entity_description.key}"
        if entity_description.name not in [UNDEFINED, None]:
            self._attr_name = entity_description.name

        self.entity_description = entity_description

    async def async_added_to_hass(self) -> None:
        """Called when switch is added to Home Assistant."""
        await super().async_added_to_hass()

        if self.coordinator.unii.connected:
            self._attr_available = True

        self.async_write_ha_state()

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        if not self._attr_available:
            return self._attr_available

        return self.coordinator.last_update_success

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""

        if not self.coordinator.unii.connected:
            self._attr_available = False

        if self.coordinator.data is None:
            command = self.coordinator.data.get("command")

            if command == UNiiCommand.NORMAL_DISCONNECT:
                self._attr_available = False
            elif command in [
                UNiiCommand.CONNECTION_REQUEST_RESPONSE,
                UNiiCommand.POLL_ALIVE_RESPONSE,
            ]:
                self._attr_available = True

        self.async_write_ha_state()


class UNiiOutputSwitch(UNiiSwitch):
    """UNii Switch for outputs."""

    def __init__(
        self,
        coordinator: UNiiCoordinator,
        entity_description: SwitchEntityDescription,
        config_entry_id: str,
        output_number: int,
    ):
        """Initialize the switch."""
        super().__init__(coordinator, entity_description, config_entry_id)

        self.output_number = output_number
        self._attr_extra_state_attributes = {"output_number": output_number}
        self._attr_translation_placeholders = {"output_number": output_number}

    # def _handle_output_status(self, output_status: UNiiOutputStatusRecord):
    #     pass
    #
    # async def async_added_to_hass(self) -> None:
    #     await super().async_added_to_hass()
    #
    #     if not self.coordinator.unii.connected:
    #         self._attr_available = False
    #     else:
    #         output_status: UNiiOutputStatusRecord = self.coordinator.unii.outputs.get(
    #             self.output_number
    #         )
    #
    #         self._handle_output_status(output_status)
    #
    #     self.async_write_ha_state()
    #
    # @callback
    # def _handle_coordinator_update(self) -> None:
    #     """Handle updated data from the coordinator."""
    #
    #     super()._handle_coordinator_update()
    #
    #     if self.coordinator.data is None:
    #         return
    #
    #     command = self.coordinator.data.get("command")
    #     data = self.coordinator.data.get("data")
    #
    #     if (
    #         command == UNiiCommand.EVENT_OCCURRED
    #         and data.output_number == self.output_number
    #     ):
    #         # ToDo
    #         pass
    #     elif command == UNiiCommand.OUTPUT_STATUS_CHANGED and self.output_number in data:
    #         output_status: UNiiOutputStatusRecord = data.get(self.output_number)
    #         self._handle_output_status(output_status)
    #     elif (
    #         command == UNiiCommand.OUTPUT_STATUS_UPDATE
    #         and data.number == self.output_number
    #     ):
    #         self._handle_output_status(data)
    #     else:
    #         return
    #
    #     self.async_write_ha_state()
