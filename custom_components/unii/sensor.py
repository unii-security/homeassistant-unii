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
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import DOMAIN, UNiiCoordinator
from .unii import UNiiInputState, UNiiInputStatusRecord

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the UNii _attr_native_values."""
    coordinator: UNiiCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    entities = []

    for number, unii_input in coordinator.unii.inputs.items():
        if "status" in unii_input and unii_input.status not in [
            None,
            UNiiInputState.DISABLED,
        ]:
            name = f"Input {number}"
            if unii_input.name is not None:
                name = unii_input.name
            entity_description = SensorEntityDescription(
                key=f"input-enum{number}", name=name
            )
            entities.append(
                UNiiInputSensor(coordinator, entity_description, unii_input.number)
            )

    async_add_entities(entities)


class UNiiSensor(CoordinatorEntity, SensorEntity):
    # pylint: disable=too-few-public-methods
    """Base UNii Sensor."""
    _attr_has_entity_name = True
    _attr_available = False
    _attr_native_value = None

    def __init__(
        self,
        coordinator: UNiiCoordinator,
        entity_description: SensorEntityDescription,
    ):
        """Initialize the sensor."""
        super().__init__(coordinator, entity_description.key)

        self._attr_device_info = coordinator.device_info
        self._attr_unique_id = (
            f"{coordinator.unii.unique_id}-s-{entity_description.key}"
        )

        self.entity_description = entity_description

    async def async_added_to_hass(self) -> None:
        """Called when sensor is added to Home Assistant."""
        await super().async_added_to_hass()

        if self.coordinator.unii.connected:
            self._attr_available = True

        self.async_write_ha_state()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""

        if self.coordinator.unii.connected:
            self._attr_available = True
        else:
            self._attr_available = False

        self.async_write_ha_state()


class UNiiInputSensor(UNiiSensor):
    # pylint: disable=too-few-public-methods
    """UNii Sensor for inputs."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["clear", "alarm", "tamper", "masking", "bypassed"]

    def __init__(
        self,
        coordinator: UNiiCoordinator,
        entity_description: SensorEntityDescription,
        input_id: int,
    ):
        """Initialize the sensor."""
        super().__init__(coordinator, entity_description)

        self.input_id = input_id

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()

        if self.coordinator.unii.connected:
            input_status: UNiiInputStatusRecord = self.coordinator.unii.inputs[
                self.input_id
            ]

            if (
                input_status.status == UNiiInputState.DISABLED
                or input_status.supervision
            ):
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
                elif input_status == UNiiInputState.MASKING:
                    self._attr_native_value = "masking"

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
