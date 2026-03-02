"""
Classes for connecting to Alphatronics UNii security systems.

Only TCP/IP connections are supported, UDP connections are currently not implemented.
"""

import asyncio
import logging
import random
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Final

from .task_helper import save_task_reference
from .unii_command import UNiiCommand
from .unii_command_data import UNiiData
from .unii_message import UNiiMessageError, UNiiRequestMessage, UNiiResponseMessage

logger = logging.getLogger(__name__)

DEFAULT_PORT: Final = 6502


class UNiiConnectionError(Exception):
    """
    UNii Connection Error.

    When an error occurs while connecting to the Alphatronics UNii.
    """


# class UNiiSequenceNumberError(Exception):
#     """
#     UNii Sequence Number Error.
#
#     When the received RX Sequence Number does not match the sent TX Sequence Number.
#     """
#
#     def __init__(self, expected_sequence_number: int, received_sequence_number: int):
#         self._expected_sequence_number = expected_sequence_number
#         self._received_sequence_number = received_sequence_number
#
#     def __str__(self) -> str:
#         return (
#             f"Invalid sequence number. Expected {self._expected_sequence_number}, "
#             + "received {self._received_sequence_number}."
#         )


class UNiiConnection(ABC):
    """
    Abstract connection class on which the different connection types are build.
    """

    _MAX_LENGTH_OF_ANSWER: Final = 1500

    last_message_sent: datetime = datetime.now()
    last_message_received: datetime = datetime.now()
    _message_received_callback = None
    unique_id: str

    def set_message_received_callback(self, callback):
        """
        Sets the call back for handling Event Occurred messages.
        """
        self._message_received_callback = callback

    @abstractmethod
    async def connect(self):
        """
        Opens a connection to the Alphatronics Unii.
        """
        raise NotImplementedError

    @abstractmethod
    async def close(self) -> bool:
        """
        Closes the connection to the Alphatronics UNii.
        """
        raise NotImplementedError

    @property
    def is_open(self) -> bool:
        """
        If the connection is open
        """
        raise NotImplementedError

    @property
    def is_encrypted(self) -> bool:
        """
        If the connection is open
        """
        raise NotImplementedError

    @abstractmethod
    async def send(
        self,
        command: UNiiCommand,
        data: UNiiData | None = None,
    ) -> int | None:
        """
        Constructs a message based on given command and data, writes this to the UNii and
        returns the TX Sequence ID or None if writing failed.
        """
        raise NotImplementedError


class UNiiTCPConnection(UNiiConnection):
    # pylint: disable=too-many-instance-attributes
    """
    Connection to an Alphatronics UNii over TCP/IP.
    """

    _reader: asyncio.StreamReader | None = None
    _writer: asyncio.StreamWriter | None = None
    _session_id: int | None = None
    _tx_sequence: int = -1
    _rx_sequence: int = 0

    _receive_task: asyncio.Task | None = None

    def __init__(
        self, host: str, port: int = DEFAULT_PORT, shared_key: bytes | None = None
    ):
        assert host is not None
        assert port is not None

        self._host = host
        self._port = port
        self._shared_key = shared_key
        self._writer_lock = asyncio.Lock()
        self.unique_id = host

    def __str__(self) -> str:
        return f"{self._host}:{self._port}"

    async def connect(self):
        try:
            if not self.is_open:
                logger.info("Connecting to %s", self)
                self._reader, self._writer = await asyncio.wait_for(
                    asyncio.open_connection(self._host, self._port), timeout=10
                )
                logger.info("Connected to %s", self)

                # Fixed session ID only one session
                self._session_id = 0xFFFF
                # Start with a random TX Sequence
                self._tx_sequence = random.randint(0, 65535)

                # Start the read coroutine
                self._receive_task = asyncio.create_task(self._receive_coroutine())
                save_task_reference(self._receive_task)
        except TimeoutError as ex:
            raise UNiiConnectionError("Open connection timeout") from ex
        except (
            OSError,
            ConnectionRefusedError,
            ConnectionResetError,
            asyncio.CancelledError,
        ) as ex:
            raise UNiiConnectionError(ex) from ex

    async def _close(self) -> bool:
        if self.is_open:
            try:
                async with self._writer_lock:
                    self._writer.close()
                    await self._writer.wait_closed()
            except ConnectionResetError as ex:
                logger.error(ex)

            self._writer = None
            self._reader = None

        if not self.is_open:
            logger.debug("Connection closed")
            return True

        logger.error("Failed to close connection")
        return False

    async def close(self) -> bool:
        if not await self._cancel_receive():
            return False

        return await self._close()

    @property
    def is_open(self) -> bool:
        """
        If the connection is open
        """
        return self._writer is not None

    @property
    def is_encrypted(self) -> bool:
        """
        If the connection is open
        """
        return self._shared_key is not None

    async def _cancel_receive(self) -> bool:
        if self._receive_task is not None and not (
            self._receive_task.done() or self._receive_task.cancelled()
        ):
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                logger.debug("Receive task was cancelled")
                self._receive_task = None

        if self._receive_task is not None:
            logger.error("Failed to cancel receive task")
            logger.debug("Receive task: %s", self._receive_task)
            return False

        return True

    async def _receive_coroutine(self):
        while self._reader is not None:
            try:
                response = await asyncio.wait_for(self._reader.read(14), timeout=0.1)
                if len(response) < 13:
                    continue

                # Length
                packet_length = int.from_bytes(response[12:14])

                # Read remaining part of the message
                while len(response) < packet_length:
                    response += await self._reader.read(packet_length - len(response))
                    if len(response) < packet_length:
                        logger.debug("Response not yet fully received")

                message = UNiiResponseMessage(response, self._shared_key)
                if message.command not in [
                    # UNiiCommand.CONNECTION_REQUEST_RESPONSE,
                    UNiiCommand.POLL_ALIVE_RESPONSE,
                    UNiiCommand.INPUT_STATUS_CHANGED,
                    UNiiCommand.DEVICE_STATUS_CHANGED,
                    UNiiCommand.RESPONSE_REQUEST_INPUT_ARRANGEMENT,
                    UNiiCommand.RESPONSE_REQUEST_EQUIPMENT_INFORMATION,
                ]:
                    logger.debug("Received: 0x%s", response.hex())
                    logger.debug("Received: %s", message)
                else:
                    logger.debug(
                        "Received: %i, %s", message.rx_sequence, message.command
                    )
                self.last_message_received = datetime.now()
                # logger.debug("Last message received: %s", self.last_message_sent)
                if message.rx_sequence != self._tx_sequence:
                    logger.warning(
                        "Invalid sequence number. Expected %i, received %i.",
                        self._tx_sequence,
                        message.rx_sequence,
                    )

                self._session_id = message.session_id
                self._rx_sequence = message.tx_sequence

                if self._message_received_callback is not None:
                    await self._message_received_callback(
                        message.rx_sequence, message.command, message.data
                    )
            except UNiiMessageError as ex:
                logger.error(ex)
            except ConnectionResetError as ex:
                logger.debug(ex)
                await self._close()
                break
            except asyncio.CancelledError:
                logger.debug("Receive coroutine was canceled")
                break
            except TimeoutError:
                pass
            except IndexError as ex:
                logger.error(ex)
            await asyncio.sleep(0.1)

        self._receive_task = None
        logger.debug("Receive coroutine stopped")

    async def send(
        self,
        command: UNiiCommand,
        data: UNiiData | None = None,
    ) -> int | None:
        if self.is_open:
            message = UNiiRequestMessage()
            message.session_id = self._session_id
            self._tx_sequence += 1
            message.tx_sequence = self._tx_sequence
            message.rx_sequence = self._rx_sequence
            message.command = command
            message.data = data
            # logger.debug("Sending: %s", message)
            # logger.debug("Sending: 0x%s", message.to_bytes(self._shared_key).hex())
            if self._writer is not None:
                try:
                    async with self._writer_lock:
                        self._writer.write(message.to_bytes(self._shared_key))
                        await self._writer.drain()
                        self.last_message_sent = datetime.now()
                        # logger.debug("Last message sent: %s", self.last_message_sent)

                    return message.tx_sequence
                except ConnectionResetError as ex:
                    await self.close()
                    raise UNiiConnectionError(str(ex)) from ex

        return None


# UDP connections are currently not implemented.
# class UNiiUDPConnection(UNiiConnection):
#     """
#     Connection to an Alphatronics UNii over UDP
#     """
#     pass
