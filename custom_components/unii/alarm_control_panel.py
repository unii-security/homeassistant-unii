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
from homeassistant.const import (
    STATE_ALARM_ARMED_AWAY,
    STATE_ALARM_ARMING,
    STATE_ALARM_DISARMED,
    STATE_ALARM_DISARMING,
    STATE_ALARM_TRIGGERED,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import UNDEFINED
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from unii import (
    UNiiCommand,
    UNiiFeature,
    UNiiInputState,
    UNiiInputStatusRecord,
    UNiiSection,
    UNiiSectionArmedState,
    UNiiSectionStatusRecord,
)

from . import DOMAIN, UNiiCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the UNii lock."""
    coordinator: UNiiCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    entities = []

    if coordinator.can_write() and UNiiFeature.ARM_SECTION in coordinator.unii.features:
        for section in (
            section for section in coordinator.unii.sections.values() if section.active
        ):
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

    # if UNiiFeature.BYPASS_INPUT in coordinator.unii.features:
    #     for _, unii_input in coordinator.unii.inputs.items():
    #         if "status" in unii_input and unii_input.status not in [
    #             None,
    #             UNiiInputState.DISABLED,
    #         ]:
    #             if unii_input.name is None:
    #                 entity_description = AlarmControlPanelEntityDescription(
    #                     key=f"input{unii_input.number}-bypass",
    #                 )
    #             else:
    #                 entity_description = AlarmControlPanelEntityDescription(
    #                     key=f"input{unii_input.number}-bypass",
    #                     name=f"Bypass {unii_input.name}",
    #                 )
    #             entities.append(
    #                 UNiiBypassInput(
    #                     coordinator,
    #                     entity_description,
    #                     config_entry.entry_id,
    #                     unii_input.number,
    #                 )
    #             )

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
    """UNii Alarm Control Panel to arm a Section."""

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

    def _handle_section_status(self, section_status: UNiiSection):
        if not section_status.active:
            self._attr_available = False

        match section_status.armed_state:
            case UNiiSectionArmedState.NOT_PROGRAMMED:
                self._attr_available = False
            case UNiiSectionArmedState.ARMED:
                self._attr_state = STATE_ALARM_ARMED_AWAY
            case UNiiSectionArmedState.DISARMED:
                self._attr_state = STATE_ALARM_DISARMED
            case UNiiSectionArmedState.ALARM:
                self._attr_state = STATE_ALARM_TRIGGERED
            case UNiiSectionArmedState.EXIT_TIMER:
                self._attr_state = STATE_ALARM_ARMING
            case UNiiSectionArmedState.ENTRY_TIMER:
                self._attr_state = STATE_ALARM_ARMED_AWAY

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()

        if not self.coordinator.unii.connected:
            self._attr_available = False
        else:
            section = self.coordinator.unii.sections.get(self.section_number)
            self._handle_section_status(section)

        self.async_write_ha_state()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""

        super()._handle_coordinator_update()

        if self.coordinator.data is None:
            return

        command = self.coordinator.data.get("command")
        data = self.coordinator.data.get("data")

        if (
            command == UNiiCommand.EVENT_OCCURRED
            and self.section_number in data.sections
        ):
            # ToDo
            pass
        elif (
            command == UNiiCommand.RESPONSE_REQUEST_SECTION_STATUS
            and self.section_number in data
        ):
            section_status: UNiiSectionStatusRecord = data.get(self.section_number)
            self._handle_section_status(section_status)

        self.async_write_ha_state()

    async def async_alarm_arm_away(self, code: str):
        """Send arm away command."""
        self._attr_state = STATE_ALARM_ARMING
        self.async_write_ha_state()

        if await self.coordinator.unii.arm_section(self.section_number, code):
            self._attr_state = STATE_ALARM_ARMED_AWAY

        self.async_write_ha_state()

    async def async_alarm_disarm(self, code: str):
        """Send disarm command."""
        self._attr_state = STATE_ALARM_DISARMING
        self.async_write_ha_state()

        if await self.coordinator.unii.disarm_section(self.section_number, code):
            self._attr_state = STATE_ALARM_DISARMED

        self.async_write_ha_state()


class UNiiBypassInput(UNiiAlarmControlPanel):
    """UNii Alarm Control Panel to bypass inputs."""

    _attr_translation_key = "bypass_input"

    _attr_code_format = CodeFormat.NUMBER
    _attr_supported_features: AlarmControlPanelEntityFeature = (
        AlarmControlPanelEntityFeature.ARM_CUSTOM_BYPASS
    )

    def __init__(
        self,
        coordinator: UNiiCoordinator,
        entity_description: AlarmControlPanelEntityDescription,
        config_entry_id: str,
        input_number: int,
    ):
        """Initialize the sensor."""
        super().__init__(coordinator, entity_description, config_entry_id)

        self.input_number = input_number
        self._attr_translation_placeholders = {"input_number": input_number}

    def _handle_input_status(self, input_status: UNiiInputStatusRecord):
        # if "input_type" in input_status:
        #     self._attr_extra_state_attributes["input_type"] = str(
        #         input_status.input_type
        #     )
        # if "sensor_type" in input_status:
        #     self._attr_extra_state_attributes["sensor_type"] = str(
        #         input_status.sensor_type
        #     )

        if input_status.bypassed:
            self._attr_state = "armed_custom_bypass"
        else:
            self._attr_state = "armed"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()

        if self.coordinator.unii.connected:
            input_status: UNiiInputStatusRecord = self.coordinator.unii.inputs.get(
                self.input_number
            )

            self._handle_input_status(input_status)

        self.async_write_ha_state()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""

        super()._handle_coordinator_update()

        if self.coordinator.data is None:
            return

        command = self.coordinator.data.get("command")
        data = self.coordinator.data.get("data")

        if (
            command == UNiiCommand.EVENT_OCCURRED
            and data.input_number == self.input_number
        ):
            # ToDo
            pass
        elif command == UNiiCommand.INPUT_STATUS_CHANGED and self.input_number in data:
            input_status: UNiiInputStatusRecord = data.get(self.input_number)
            self._handle_input_status(input_status)
        elif (
            command == UNiiCommand.INPUT_STATUS_UPDATE
            and data.number == self.input_number
        ):
            self._handle_input_status(data)
        else:
            return

        self.async_write_ha_state()

    async def async_alarm_arm_custom_bypass(self, code=None) -> None:
        """Send arm custom bypass command."""
