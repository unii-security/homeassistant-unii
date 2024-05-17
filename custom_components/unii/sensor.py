# pylint: disable=R0801
"""
Creates Sensor entities for the UNii Home Assistant integration.
"""
import logging

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import UNDEFINED
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import DOMAIN, UNiiCoordinator
from .unii import (
    UNiiCommand,
    UNiiFeature,
    UNiiInputState,
    UNiiInputStatusRecord,
    UNiiSectionArmedState,
    UNiiSectionStatusRecord,
    UNiiSensorType,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the UNii sensor."""
    coordinator: UNiiCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    entities = []

    for _, unii_input in coordinator.unii.inputs.items():
        if "status" in unii_input and unii_input.status not in [
            None,
            UNiiInputState.DISABLED,
        ]:
            if unii_input.name is None:
                entity_description = SensorEntityDescription(
                    key=f"input{unii_input.number}-enum",
                )
            else:
                entity_description = SensorEntityDescription(
                    key=f"input{unii_input.number}-enum",
                    name=unii_input.name,
                )
            entities.append(
                UNiiInputSensor(
                    coordinator,
                    entity_description,
                    config_entry.entry_id,
                    unii_input.number,
                )
            )

    if UNiiFeature.ARM_SECTION not in coordinator.unii.features:
        for _, section in coordinator.unii.sections.items():
            if section.active:
                if section.name is None:
                    entity_description = SensorEntityDescription(
                        key=f"section{section.number}-enum",
                    )
                else:
                    entity_description = SensorEntityDescription(
                        key=f"section{section.number}-enum",
                        name=section.name,
                    )
                entities.append(
                    UNiiSectionSensor(
                        coordinator,
                        entity_description,
                        config_entry.entry_id,
                        section.number,
                    )
                )

    async_add_entities(entities)


class UNiiSensor(CoordinatorEntity, SensorEntity):
    # pylint: disable=too-few-public-methods
    """Base UNii Sensor."""
    _attr_has_entity_name = True
    _attr_available = False
    _attr_native_value = None
    _attr_icon = None

    def __init__(
        self,
        coordinator: UNiiCoordinator,
        entity_description: SensorEntityDescription,
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

        if self.coordinator.data is not None:
            command = self.coordinator.data.get("command")

            if command == UNiiCommand.NORMAL_DISCONNECT:
                self._attr_available = False
            elif command in [
                UNiiCommand.CONNECTION_REQUEST_RESPONSE,
                UNiiCommand.POLL_ALIVE_RESPONSE,
            ]:
                self._attr_available = True

        self.async_write_ha_state()


class UNiiInputSensor(UNiiSensor):
    # pylint: disable=too-few-public-methods
    """UNii Sensor for inputs."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["clear", "alarm", "tamper", "masking", "bypassed"]
    _attr_translation_key = "input"

    def __init__(
        self,
        coordinator: UNiiCoordinator,
        entity_description: SensorEntityDescription,
        config_entry_id: str,
        input_number: int,
    ):
        """Initialize the sensor."""
        super().__init__(coordinator, entity_description, config_entry_id)

        self.input_number = input_number
        self._attr_extra_state_attributes = {"input_number": input_number}
        self._attr_translation_placeholders = {"input_number": input_number}

    def _handle_input_status(self, input_status: UNiiInputStatusRecord):
        if "input_type" in input_status:
            self._attr_extra_state_attributes["input_type"] = str(
                input_status.input_type
            )
        if "sensor_type" in input_status:
            self._attr_extra_state_attributes["sensor_type"] = str(
                input_status.sensor_type
            )
        if "sections" in input_status:
            self._attr_extra_state_attributes["sections"] = [
                section.number for section in input_status.sections
            ]

        if input_status.status == UNiiInputState.DISABLED or input_status.supervision:
            self._attr_available = False
        else:
            self._attr_available = True
            if input_status.status == UNiiInputState.INPUT_OK:
                self._attr_native_value = "clear"
            elif input_status.bypassed is True:
                self._attr_native_value = "bypassed"
            elif input_status.status == UNiiInputState.ALARM:
                self._attr_native_value = "alarm"
            elif input_status.status == UNiiInputState.TAMPER:
                self._attr_native_value = "tamper"
            elif input_status.status == UNiiInputState.MASKING:
                self._attr_native_value = "masking"

        match input_status.sensor_type:
            # case UNiiSensorType.NOT_ACTIVE:
            #     self._attr_icon = ""
            case UNiiSensorType.BURGLARY:
                self._attr_icon = "mdi:motion-sensor"
            case UNiiSensorType.FIRE:
                self._attr_icon = "mdi:fire"
            case UNiiSensorType.TAMPER:
                self._attr_icon = "mdi:tools"
            case UNiiSensorType.HOLDUP:
                self._attr_icon = "mdi:robot-angry"
            case UNiiSensorType.MEDICAL:
                self._attr_icon = "mdi:medication"
            case UNiiSensorType.GAS:
                self._attr_icon = "mdi:waves-arrow-up"
            case UNiiSensorType.WATER:
                self._attr_icon = "mdi:water-alert"
            case UNiiSensorType.TECHNICAL:
                self._attr_icon = "mdi:cog"
            case UNiiSensorType.DIRECT_DIALER_INPUT:
                self._attr_icon = "mdi:cog"
            case UNiiSensorType.KEYSWITCH:
                self._attr_icon = "mdi:key"
            case UNiiSensorType.NO_ALARM:
                self._attr_icon = "mdi:cog"
            case UNiiSensorType.EN54_FIRE:
                self._attr_icon = "mdi:fire"
            case UNiiSensorType.EN54_FIRE_MCP:
                self._attr_icon = "mdi:fire"
            case UNiiSensorType.EN54_FAULT:
                self._attr_icon = "mdi:fire"
            case UNiiSensorType.GLASSBREAK:
                self._attr_icon = "mdi:window-closed-variant"

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


class UNiiSectionSensor(UNiiSensor):
    """UNii Sensor for sections."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["armed", "disarmed", "alarm"]
    _attr_translation_key = "section"

    def __init__(
        self,
        coordinator: UNiiCoordinator,
        entity_description: SensorEntityDescription,
        config_entry_id: str,
        section_number: int,
    ):
        """Initialize the sensor."""
        super().__init__(coordinator, entity_description, config_entry_id)

        self.section_number = section_number
        self._attr_extra_state_attributes = {"section_number": section_number}
        self._attr_translation_placeholders = {"section_number": section_number}

    def _handle_section_status(self, section: UNiiSectionStatusRecord):
        if not section.active:
            self._attr_available = False

        if section.armed_state == UNiiSectionArmedState.NOT_PROGRAMMED:
            self._attr_available = False
        elif section.armed_state == UNiiSectionArmedState.ARMED:
            self._attr_native_value = "armed"
            self._attr_icon = "mdi:lock"
        elif section.armed_state == UNiiSectionArmedState.DISARMED:
            self._attr_native_value = "disarmed"
            self._attr_icon = "mdi:lock-open-variant"
        elif section.armed_state == UNiiSectionArmedState.ALARM:
            self._attr_native_value = "alarm"
            self._attr_icon = "mdi:lock"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()

        if self.coordinator.unii.connected:
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
