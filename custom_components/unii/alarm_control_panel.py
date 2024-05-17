# pylint: disable=R0801
"""
Creates Alarm Control Panel entities for the UNii Home Assistant integration.
"""

import logging

from homeassistant.components.alarm_control_panel import (
    AlarmControlPanelEntity,
    AlarmControlPanelEntityDescription,
    AlarmControlPanelEntityFeature,
)
from homeassistant.components.alarm_control_panel.const import CodeFormat
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import UNDEFINED
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import DOMAIN, UNiiCoordinator
from .unii import UNiiCommand, UNiiFeature, UNiiSection, UNiiSectionArmedState

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the UNii lock."""
    coordinator: UNiiCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    entities = []

    if UNiiFeature.ARM_SECTION in coordinator.unii.features:
        for _, section in coordinator.unii.sections.items():
            if section.active:
                if section.name is None:
                    entity_description = AlarmControlPanelEntityDescription(
                        key=f"section{section.number}-arm",
                    )
                else:
                    entity_description = AlarmControlPanelEntityDescription(
                        key=f"section{section.number}-arm",
                        name=section.name,
                    )
                entities.append(
                    UNiiArmSection(
                        coordinator,
                        entity_description,
                        config_entry.entry_id,
                        section.number,
                    )
                )

    async_add_entities(entities)


class UNiiAlarmControlPanel(CoordinatorEntity, AlarmControlPanelEntity):
    """Base UNii Alarm Control Panel."""

    _attr_has_entity_name = True
    _attr_available = False
    _attr_is_disarmed = None
    _attr_state = None
    _attr_is_arming = None
    _attr_is_disarming = None

    def __init__(
        self,
        coordinator: UNiiCoordinator,
        entity_description: AlarmControlPanelEntityDescription,
        config_entry_id: str,
    ):
        """Initialize the sensor."""
        super().__init__(coordinator, entity_description.key)

        self._attr_device_info = coordinator.device_info
        self._attr_unique_id = f"{config_entry_id}-{entity_description.key}"
        if entity_description.name not in [UNDEFINED, None]:
            self._attr_name = entity_description.name

        self.entity_description = entity_description

    async def async_added_to_hass(self) -> None:
        """Called when sensor is added to Home Assistant."""
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
            return

        command = self.coordinator.data.get("command")

        if command == UNiiCommand.NORMAL_DISCONNECT:
            self._attr_available = False
        elif command in [
            UNiiCommand.CONNECTION_REQUEST_RESPONSE,
            UNiiCommand.POLL_ALIVE_RESPONSE,
        ]:
            self._attr_available = True

        self.async_write_ha_state()


class UNiiArmSection(UNiiAlarmControlPanel):
    """UNii Alarm Control Panel to for a Section."""

    _attr_translation_key = "section"

    _attr_code_format = CodeFormat.NUMBER
    _attr_supported_features: AlarmControlPanelEntityFeature = (
        AlarmControlPanelEntityFeature.ARM_AWAY
    )

    def __init__(
        self,
        coordinator: UNiiCoordinator,
        entity_description: AlarmControlPanelEntityDescription,
        config_entry_id: str,
        section_number: int,
    ):
        """Initialize the sensor."""
        super().__init__(coordinator, entity_description, config_entry_id)

        self.section_number = section_number
        self._attr_translation_placeholders = {"section_number": section_number}

    def _handle_section(self, section: UNiiSection):
        if section.armed_state == UNiiSectionArmedState.NOT_PROGRAMMED:
            self._attr_available = False
        elif section.armed_state in [
            UNiiSectionArmedState.ARMED,
            UNiiSectionArmedState.ALARM,
        ]:
            self._attr_is_disarmed = False
            self._attr_state = "armed"
        elif section.armed_state == UNiiSectionArmedState.DISARMED:
            self._attr_is_disarmed = True
            self._attr_state = "disarmed"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()

        if not self.coordinator.unii.connected:
            self._attr_available = False
        else:
            section = self.coordinator.unii.sections.get(self.section_number)
            self._handle_section(section)

        self.async_write_ha_state()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""

        super()._handle_coordinator_update()

        if self.coordinator.data is None:
            return

        command = self.coordinator.data.get("command")
        data = self.coordinator.data.get("data")

        if command == UNiiCommand.RESPONSE_REQUEST_SECTION_STATUS:
            section = self.coordinator.unii.sections.get(self.section_number)
            self._handle_section(section)

        self.async_write_ha_state()

    async def async_alarm_arm_away(self, code: str):
        """Send arm away command."""
        self._attr_is_arming = True
        self.async_write_ha_state()

        if await self.coordinator.unii.arm_section(self.section_number, code):
            self._attr_is_disarmed = False
            self._attr_is_arming = False
        else:
            self._attr_is_arming = False

        self.async_write_ha_state()

    async def async_alarm_disarm(self, code: str):
        """Send disarm command."""
        self._attr_is_disarming = True
        self.async_write_ha_state()

        if await self.coordinator.unii.disarm_section(self.section_number, code):
            self._attr_is_disarmed = True
            self._attr_is_disarming = False
        else:
            self._attr_is_disarming = False

        self.async_write_ha_state()
