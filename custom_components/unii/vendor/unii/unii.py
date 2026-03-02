# pylint: disable=wildcard-import
# pylint: disable=unused-wildcard-import
"""
Classes for interfacing with Alphatronics UNii security systems.
"""

import asyncio
import logging
import time
from abc import ABC
from datetime import datetime, timedelta
from enum import IntFlag, auto
from typing import Any, Final

from .task_helper import save_task_reference
from .unii_command import UNiiCommand
from .unii_command_data import *
from .unii_connection import (
    DEFAULT_PORT,
    UNiiConnection,
    UNiiConnectionError,
    UNiiTCPConnection,
)

logger = logging.getLogger(__name__)

_POLL_ALIVE_INTERVAL: Final = timedelta(seconds=30)


class UNiiEncryptionError(Exception):
    """
    UNii Encryption Error.

    When sending an encrypted message fails.
    """


class UNiiFeature(IntFlag):
    """Features implemented by the UNii library."""

    ARM_SECTION: Final = auto()
    BYPASS_INPUT: Final = auto()
    BYPASS_ZONE: Final = auto()
    SET_OUTPUT: Final = auto()


class UNii(ABC):
    """
    UNii base class for interfacing with Alphatronics UNii security systems.
    """

    unique_id: str | None = None
    model: str = "Unknown"
    connected: bool = False

    equipment_information: UNiiEquipmentInformation | None = None
    sections: dict[int, UNiiSection]
    inputs: dict[int, UNiiInput]
    outputs: dict[int, UNiiOutput]
    device_status: UNiiDeviceStatus | None = None

    connection: UNiiConnection

    features: list[UNiiFeature]

    _event_occurred_callbacks: list[Any]

    def __init__(
        self,
    ):
        super().__init__()

        self.sections = {}
        self.inputs = {}
        self.outputs = {}

        self.features = []

        self._event_occurred_callbacks = []

    async def test_connection(self) -> bool:
        """
        Connect to Alphatronics UNii

        Throws UNiiConnectionError when no connection can be established.
        Returns False when no connection can be established
        """
        raise NotImplementedError

    async def connect(self) -> bool:
        """
        Connect to Alphatronics UNii

        Throws UNiiEncryptionError when no encrypted message can be send.
        Returns False when no connection can be established
        """
        raise NotImplementedError

    async def disconnect(self) -> bool:
        """
        Disconnect from Alphatronics UNii
        """
        raise NotImplementedError

    def add_event_occurred_callback(self, callback):
        """
        Adds an Event Occurred Callback to the UNii.
        """
        self._event_occurred_callbacks.append(callback)

    def _forward_to_event_occurred_callbacks(
        self, command: UNiiCommand, data: UNiiData | None
    ):
        for callback in self._event_occurred_callbacks:
            try:
                callback(command, data)
            # pylint: disable=broad-exception-caught
            except Exception:
                logger.exception("Exception in Event Occurred Callback: %s", callback)

    async def bypass_input(self, number: int, user_code: str) -> bool:
        """Bypass an input."""
        raise NotImplementedError

    async def unbypass_input(self, number: int, user_code: str) -> bool:
        """Unypass an input."""
        raise NotImplementedError

    async def arm_section(self, number: int, user_code: str) -> bool:
        """Arm a section."""
        raise NotImplementedError

    async def disarm_section(self, number: int, user_code: str) -> bool:
        """Disarm a section."""
        raise NotImplementedError


class UNiiLocal(UNii):
    # pylint: disable=too-many-instance-attributes
    """
    UNii class for interfacing with Alphatronics UNii security systems on the local
    network.
    """

    _received_message_queue: dict[int, list[Any]]
    _waiting_for_message: dict[int, UNiiCommand | None]

    _poll_alive_task: asyncio.Task | None = None

    def __init__(
        self, host: str, port: int = DEFAULT_PORT, shared_key: bytes | None = None
    ):
        super().__init__()

        # If the shared key is provided as hex string convert it to bytes.
        if shared_key is not None and isinstance(shared_key, str):
            shared_key = bytes.fromhex(shared_key)
        self.connection = UNiiTCPConnection(host, port, shared_key)
        self.unique_id = f"{host}:{port}"

        self._received_message_queue = {}
        self._waiting_for_message = {}

        self._received_message_queue_lock = asyncio.Lock()

    async def test_connection(self) -> bool:
        success = False

        await self.connection.connect()

        self.connection.set_message_received_callback(self._message_received_callback)
        response, _ = await self._send_receive(
            UNiiCommand.CONNECTION_REQUEST,
            None,
            UNiiCommand.CONNECTION_REQUEST_RESPONSE,
            False,
        )

        if response is None and self.connection.is_encrypted:
            await self.disconnect()
            raise UNiiEncryptionError()

        if response == UNiiCommand.CONNECTION_REQUEST_RESPONSE:
            response, data = await self._send_receive(
                UNiiCommand.REQUEST_EQUIPMENT_INFORMATION,
                None,
                UNiiCommand.RESPONSE_REQUEST_EQUIPMENT_INFORMATION,
                False,
            )
            if (
                response is None
                or data is None
                or response != UNiiCommand.RESPONSE_REQUEST_EQUIPMENT_INFORMATION
                or self.equipment_information is None
            ):
                logger.error("Failed to retrieve equipment information.")
            else:
                success = True

        await self.disconnect()
        return success

    async def _connect(self) -> bool:
        await self.connection.connect()

        self.connection.set_message_received_callback(self._message_received_callback)
        response, _ = await self._send_receive(
            UNiiCommand.CONNECTION_REQUEST,
            None,
            UNiiCommand.CONNECTION_REQUEST_RESPONSE,
            False,
        )

        if response is None and self.connection.is_encrypted:
            await self.disconnect()
            raise UNiiEncryptionError()

        if response == UNiiCommand.CONNECTION_REQUEST_RESPONSE:
            response, data = await self._send_receive(
                UNiiCommand.REQUEST_EQUIPMENT_INFORMATION,
                None,
                UNiiCommand.RESPONSE_REQUEST_EQUIPMENT_INFORMATION,
                False,
            )
            if (
                response is None
                or data is None
                or response != UNiiCommand.RESPONSE_REQUEST_EQUIPMENT_INFORMATION
                or self.equipment_information is None
            ):
                logger.error("Failed to retrieve equipment information.")
                await self._disconnect()
                return False

            await self._send_receive(
                UNiiCommand.REQUEST_SECTION_ARRANGEMENT,
                None,
                UNiiCommand.RESPONSE_REQUEST_SECTION_ARRANGEMENT,
                False,
            )

            await self._send_receive(
                UNiiCommand.REQUEST_SECTION_STATUS,
                UNiiRawData(
                    bytes.fromhex(
                        "0102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f20"
                    )
                ),
                UNiiCommand.RESPONSE_REQUEST_SECTION_STATUS,
                False,
            )

            block = 0
            while True:
                block += 1
                _, data = await self._send_receive(
                    UNiiCommand.REQUEST_INPUT_ARRANGEMENT,
                    UNiiRawData(block.to_bytes(2)),
                    UNiiCommand.RESPONSE_REQUEST_INPUT_ARRANGEMENT,
                    False,
                )
                if data is None:
                    break

            await self._send_receive(
                UNiiCommand.REQUEST_INPUT_STATUS,
                None,
                UNiiCommand.INPUT_STATUS_CHANGED,
                False,
            )

            software_version = (
                self.equipment_information.software_version.finalize_version()
            )
            if software_version.match(">=2.17.0"):
                block = 0
                while True:
                    block += 1
                    _, data = await self._send_receive(
                        UNiiCommand.REQUEST_OUTPUT_ARRANGEMENT,
                        UNiiRawData(block.to_bytes(2)),
                        UNiiCommand.RESPONSE_REQUEST_OUTPUT_ARRANGEMENT,
                        False,
                    )
                    if data is None:
                        break

            await self._send_receive(
                UNiiCommand.REQUEST_DEVICE_STATUS,
                None,
                UNiiCommand.DEVICE_STATUS_CHANGED,
                False,
            )

            self.connected = True

            self._forward_to_event_occurred_callbacks(
                UNiiCommand.CONNECTION_REQUEST_RESPONSE, None
            )

            return True
        return False

    async def connect(self) -> bool:
        try:
            if await self._connect():
                self._poll_alive_task = asyncio.create_task(
                    self._poll_alive_coroutine()
                )
                save_task_reference(self._poll_alive_task)
                return True
        except UNiiConnectionError as ex:
            logger.error(str(ex))

        return False

    async def _disconnect(self) -> bool:
        try:
            await self._send(UNiiCommand.NORMAL_DISCONNECT, None, False)
        except UNiiEncryptionError:
            pass

        if await self.connection.close():
            self.connected = False
            # Re-using the Normal Disconnect command to let the Event Occurred Callbacks know the
            # UNii is disconnected.
            self._forward_to_event_occurred_callbacks(
                UNiiCommand.NORMAL_DISCONNECT, None
            )
            return True

        return False

    async def disconnect(self) -> bool:
        await self._cancel_poll_alive()

        if self.connection is not None and self.connection.is_open:
            try:
                if not await self._disconnect():
                    return False
            except UNiiConnectionError as ex:
                logger.error(str(ex))
                return False

        if self._poll_alive_task is not None:
            await self._cancel_poll_alive()
        return True

    async def _send(
        self, command: UNiiCommand, data: UNiiData | None = None, reconnect: bool = True
    ) -> int | None:
        try:
            if self.connection is None and reconnect:
                logger.info("Trying to connect")
                await self._connect()
            elif not self.connection.is_open and reconnect:
                logger.info("Trying to reconnect")
                await self._connect()
            elif self.connection is None or not self.connection.is_open:
                # ToDo: Throw exception?
                return None

            # logger.debug("Sending command %s", command)
            return await self.connection.send(command, data)
        except UNiiEncryptionError:
            self._forward_to_event_occurred_callbacks(UNiiCommand.REAUTHENTICATE, None)
            raise

    async def _send_receive(
        self,
        command: UNiiCommand,
        data: UNiiData | None = None,
        expected_response: UNiiCommand | None = None,
        reconnect: bool = True,
    ) -> list[Any]:
        tx_sequence = await self._send(command, data, reconnect)
        if tx_sequence is not None:
            return await self._get_received_message(tx_sequence, expected_response)
        return [None, None]

    def _handle_equipment_information(self, data: UNiiEquipmentInformation):
        if (
            self.equipment_information is not None
            and self.equipment_information != data
        ):
            self._forward_to_event_occurred_callbacks(
                UNiiCommand.RELOAD_CONFIGURATION, None
            )

        self.equipment_information = data

        # Set the supported features of the equipment
        self.features = []

        # Feature that applies to all versions of the firmware
        self.features.append(UNiiFeature.BYPASS_INPUT)
        self.features.append(UNiiFeature.ARM_SECTION)

        # Get capabilities based on firmware version number
        # Library doesn't distinct between versions yet, so disabled for now
        # software_version = (
        #     self.equipment_information.software_version.finalize_version()
        # )
        # if software_version.match(">=2.17.0"):
        #     self.features.append(UNiiFeature.BYPASS_ZONE)
        #     self.features.append(UNiiFeature.SET_OUTPUT)

    def _handle_section_arrangement(self, data: UNiiSectionArrangement):
        for _, section in data.items():
            if section.number not in self.sections and section.active:
                self.sections[section.number] = section
            elif section.number in self.sections:
                self.sections[section.number].update(section)

    def _handle_section_status(self, data: UNiiSectionStatus):
        for _, section_status in data.items():
            if section_status.number in self.sections:
                section_status["active"] = (
                    section_status.armed_state != UNiiSectionArmedState.NOT_PROGRAMMED
                )
                self.sections[section_status.number].update(section_status)
            elif section_status.armed_state != UNiiSectionArmedState.NOT_PROGRAMMED:
                # This should never happen
                logger.warning(
                    "Status for unknown section %i changed", section_status.number
                )

    def _handle_input_status_update(self, input_status: UNiiInputStatusRecord):
        if input_status.number in self.inputs:
            self.inputs[input_status.number].update(input_status)
        elif input_status.status != UNiiInputState.DISABLED:
            # This should never happen
            logger.warning("Status for unknown input %i changed", input_status.number)

    def _handle_input_status_changed(self, data: UNiiInputStatus):
        for _, input_status in data.items():
            self._handle_input_status_update(input_status)

    def _handle_input_arrangement(self, data: UNiiInputArrangement):
        if data is None:
            return
        for _, unii_input in data.items():
            # Expand sections
            for index, section in enumerate(unii_input.sections):
                unii_input["sections"][index] = self.sections[section]

            if unii_input.number not in self.inputs:
                self.inputs[unii_input.number] = unii_input
            else:
                # Retain the input status before updating the input with new data.
                unii_input.status = self.inputs[unii_input.number].status
                self.inputs[unii_input.number].update(unii_input)

    async def _message_received_callback(
        self, tx_sequence: int, command: UNiiCommand, data: UNiiData
    ):
        match command:
            case UNiiCommand.EVENT_OCCURRED:
                self._forward_to_event_occurred_callbacks(command, data)
                if self.connected:
                    try:
                        await self._send(
                            UNiiCommand.RESPONSE_EVENT_OCCURRED, None, False
                        )
                    except UNiiEncryptionError:
                        pass
            case UNiiCommand.INPUT_STATUS_CHANGED:
                self._handle_input_status_changed(data)
            case UNiiCommand.INPUT_STATUS_UPDATE:
                self._handle_input_status_update(data)
            case UNiiCommand.DEVICE_STATUS_CHANGED:
                self.device_status = data
            case UNiiCommand.RESPONSE_REQUEST_SECTION_ARRANGEMENT:
                self._handle_section_arrangement(data)
            case UNiiCommand.RESPONSE_REQUEST_SECTION_STATUS:
                self._handle_section_status(data)
            case UNiiCommand.RESPONSE_REQUEST_INPUT_ARRANGEMENT:
                self._handle_input_arrangement(data)
            case UNiiCommand.RESPONSE_REQUEST_EQUIPMENT_INFORMATION:
                self._handle_equipment_information(data)

        if tx_sequence in self._waiting_for_message and self._waiting_for_message[
            tx_sequence
        ] in [None, command]:
            async with self._received_message_queue_lock:
                self._received_message_queue[tx_sequence] = [command, data]

        self._forward_to_event_occurred_callbacks(command, data)

    async def _get_received_message(
        self, tx_sequence: int, expected_response: UNiiCommand | None = None
    ) -> list[Any]:
        timeout = time.time() + 5
        self._waiting_for_message[tx_sequence] = expected_response
        while self.connection.is_open and time.time() < timeout:
            async with self._received_message_queue_lock:
                if tx_sequence in self._received_message_queue:
                    return self._received_message_queue.pop(tx_sequence)
            # logger.debug("Waiting for message %i to be received", tx_sequence)
            await asyncio.sleep(0.1)

        logger.error("Message %i was not received", tx_sequence)
        del self._waiting_for_message[tx_sequence]
        return [None, None]

    async def _poll_alive(self) -> bool:
        try:
            response, _ = await self._send_receive(
                UNiiCommand.POLL_ALIVE_REQUEST,
                None,
                UNiiCommand.POLL_ALIVE_RESPONSE,
                True,
            )
            # logger.debug("Response received: %s", response)
            if response == UNiiCommand.POLL_ALIVE_RESPONSE:
                # logger.debug("Poll Alive success")
                return True
        except UNiiConnectionError as ex:
            logger.error(str(ex))

        if self.connection.is_open:
            logger.error("Poll Alive failed")
        return False

    async def _cancel_poll_alive(self) -> bool:
        if self._poll_alive_task is not None and not (
            self._poll_alive_task.done() or self._poll_alive_task.cancelled()
        ):
            self._poll_alive_task.cancel()
            try:
                await self._poll_alive_task
            except asyncio.CancelledError:
                logger.debug("Poll alive task was cancelled")
                self._poll_alive_task = None

        if self._poll_alive_task is not None:
            logger.error("Failed to cancel poll alive task")
            logger.debug("Poll alive task: %s", self._poll_alive_task)
            return False

        return True

    async def _poll_alive_coroutine(self):
        """
        To keep the connection alive (and NAT entries active) a poll message has to be sent every
        30 seconds if no other messages where sent during the last 30 seconds.
        """
        while True:
            try:
                if (
                    not self.connection.is_open
                    or datetime.now()
                    > self.connection.last_message_sent + _POLL_ALIVE_INTERVAL
                ) and not await self._poll_alive():
                    if self.connection.is_open:
                        await self._disconnect()
                await asyncio.sleep(1)
            except asyncio.CancelledError:
                logger.debug("Poll alive coroutine was canceled")
                break
            except UNiiEncryptionError:
                break

        self._poll_alive_task = None
        logger.debug("Poll Alive coroutine stopped")

    async def bypass_input(self, number: int, user_code: str) -> bool:
        response, data = await self._send_receive(
            UNiiCommand.REQUEST_TO_BYPASS_AN_INPUT,
            UNiiBypassUnbypassZoneInput(UNiiBypassMode.USER_CODE, user_code, number),
            UNiiCommand.RESPONSE_REQUEST_TO_BYPASS_AN_INPUT,
        )
        if (
            response == UNiiCommand.RESPONSE_REQUEST_TO_BYPASS_AN_INPUT
            and data.number == number
            and data.result == UNiiBypassZoneInputResult.SUCCESSFUL
        ):
            return True

        logger.error("Failed to bypass input %i, reason: %s", number, data.result)
        return False

    async def unbypass_input(self, number: int, user_code: str) -> bool:
        response, data = await self._send_receive(
            UNiiCommand.REQUEST_TO_UNBYPASS_AN_INPUT,
            UNiiBypassUnbypassZoneInput(UNiiBypassMode.USER_CODE, user_code, number),
            UNiiCommand.RESPONSE_REQUEST_TO_UNBYPASS_AN_INPUT,
        )
        if (
            response == UNiiCommand.RESPONSE_REQUEST_TO_UNBYPASS_AN_INPUT
            and data.number == number
            and data.result == UNiiUnbypassZoneInputResult.SUCCESSFUL
        ):
            return True

        logger.error("Failed to unbypass input %i, reason: %s", number, data.result)
        return False

    async def arm_section(self, number: int, user_code: str) -> bool:
        """Arm a section."""
        response, data = await self._send_receive(
            UNiiCommand.REQUEST_ARM_SECTION,
            UNiiArmDisarmSection(user_code, number),
            UNiiCommand.RESPONSE_ARM_SECTION,
        )
        if (
            response == UNiiCommand.RESPONSE_ARM_SECTION
            and data.number == number
            and data.arm_state
            in [
                UNiiArmState.SECTION_ARMED,
                UNiiArmState.NO_CHANGE,
            ]
        ):
            return True

        logger.error("Arming failed: %s", data.arm_state)
        return False

    async def disarm_section(self, number: int, user_code: str) -> bool:
        """Disarm a section."""
        response, data = await self._send_receive(
            UNiiCommand.REQUEST_DISARM_SECTION,
            UNiiArmDisarmSection(user_code, number),
            UNiiCommand.RESPONSE_DISARM_SECTION,
        )
        if (
            response == UNiiCommand.RESPONSE_DISARM_SECTION
            and data.number == number
            and data.disarm_state
            in [
                UNiiDisarmState.SECTION_DISARMED,
                UNiiDisarmState.NO_CHANGE,
            ]
        ):
            return True

        if data is not None:
            logger.error("Disarming failed: %s", data.disarm_state)
        else:
            logger.error("Disarming failed")
        return False
