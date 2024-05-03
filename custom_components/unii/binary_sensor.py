# pylint: disable=R0801
"""
Creates Binary Sensor entities for the UNii Home Assistant integration.
"""
import logging

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import UNDEFINED
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import DOMAIN, UNiiCoordinator
from .unii import UNiiCommand, UNiiInputState, UNiiInputStatusRecord

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the UNii binary sensors."""
    coordinator: UNiiCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    entities = []

    entity_description = BinarySensorEntityDescription(
        key="online",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
    )
    entities.append(UNiiOnlineBinarySensor(coordinator, entity_description))

    # Enum sensors are selected over Binary sensors to represent inputs.
    # for _, unii_input in coordinator.unii.inputs.items():
    #     if "status" in unii_input and unii_input.status not in [
    #         None,
    #         UNiiInputState.DISABLED,
    #     ]:
    #         if unii_input.name is None:
    #             entity_description = BinarySensorEntityDescription(
    #                 key=f"input{unii_input.number}-binary",
    #                 device_class=BinarySensorDeviceClass.TAMPER,
    #             )
    #         else:
    #             entity_description = BinarySensorEntityDescription(
    #                 key=f"input{unii_input.number}-binary",
    #                 device_class=BinarySensorDeviceClass.TAMPER,
    #                 name=unii_input.name,
    #             )
    #         entities.append(
    #             UNiiInputBinarySensor(
    #                 coordinator, entity_description, unii_input.number
    #             )
    #         )

    async_add_entities(entities)


class UNiiBinarySensor(CoordinatorEntity, BinarySensorEntity):
    # pylint: disable=too-few-public-methods
    """
    Base UNii Binary Sensor.
    """
    _attr_has_entity_name = True
    _attr_available = False
    _attr_is_on = None

    def __init__(
        self,
        coordinator: UNiiCoordinator,
        entity_description: BinarySensorEntityDescription,
    ):
        """Initialize the binary sensor."""
        super().__init__(coordinator, entity_description.key)

        self._attr_device_info = coordinator.device_info
        self._attr_unique_id = f"{coordinator.unii.unique_id}-{entity_description.key}"
        if entity_description.name not in [UNDEFINED, None]:
            self._attr_name = entity_description.name

        self.entity_description = entity_description

    async def async_added_to_hass(self) -> None:
        """Called when binary sensor is added to Home Assistant."""
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


class UNiiOnlineBinarySensor(UNiiBinarySensor):
    # pylint: disable=too-few-public-methods
    """
    Special binary sensor which is always available once the sensor is added to hass and changes
    state based on online status.
    """
    _attr_translation_key = "online"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()

        self._attr_available = True

        if self.coordinator.unii.connected:
            self._attr_is_on = True

        self.async_write_ha_state()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""

        if not self.coordinator.unii.connected:
            self._attr_is_on = False

        if self.coordinator.data is None:
            return

        command = self.coordinator.data.get("command")

        if (
            not self.coordinator.unii.connected
            or command == UNiiCommand.NORMAL_DISCONNECT
        ):
            self._attr_is_on = False
        if self.coordinator.unii.connected or command in [
            UNiiCommand.CONNECTION_REQUEST_RESPONSE,
            UNiiCommand.POLL_ALIVE_RESPONSE,
        ]:
            self._attr_is_on = True

        self.async_write_ha_state()


class UNiiInputBinarySensor(UNiiBinarySensor):
    # pylint: disable=too-few-public-methods
    """UNii Binary Sensor for inputs."""
    _attr_translation_key = "input"

    _attr_extra_state_attributes = {"alarm_type": "none"}

    def __init__(
        self,
        coordinator: UNiiCoordinator,
        entity_description: BinarySensorEntityDescription,
        input_number: int,
    ):
        """Initialize the binary sensor."""
        super().__init__(coordinator, entity_description)

        self.input_number = input_number
        self._attr_translation_placeholders = {"input_number": input_number}

    def _handle_input_status(self, input_status: UNiiInputStatusRecord):
        if input_status.status == UNiiInputState.DISABLED or input_status.supervision:
            self._attr_available = False
        else:
            if input_status.status == UNiiInputState.INPUT_OK:
                self._attr_is_on = False
                self._attr_extra_state_attributes["alarm_type"] = "none"
            elif input_status.bypassed is True:
                self._attr_is_on = True
                self._attr_extra_state_attributes["alarm_type"] = "none"
            elif input_status.status == UNiiInputState.ALARM:
                self._attr_is_on = True
                self._attr_extra_state_attributes["alarm_type"] = "alarm"
            elif input_status.status == UNiiInputState.TAMPER:
                self._attr_is_on = True
                self._attr_extra_state_attributes["alarm_type"] = "tamper"
            elif input_status.status == UNiiInputState.MASKING:
                self._attr_is_on = True
                self._attr_extra_state_attributes["alarm_type"] = "masking"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()

        if not self.coordinator.unii.connected:
            self._attr_available = False
        else:
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
            if self.input_number == 1:
                _LOGGER.debug("Input Status: %s", input_status)
            self._handle_input_status(input_status)
        elif (
            command == UNiiCommand.INPUT_STATUS_UPDATE
            and data.number == self.input_number
        ):
            self._handle_input_status(data)
        else:
            return

        self.async_write_ha_state()
