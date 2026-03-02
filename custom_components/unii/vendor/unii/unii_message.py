# pylint: disable=wildcard-import
# pylint: disable=unused-wildcard-import
"""
Messages used by the UNii library.
"""

import logging
from enum import IntEnum
from typing import Final

from Crypto.Cipher import AES

from .unii_command import UNiiCommand
from .unii_command_data import *

logger = logging.getLogger(__name__)


class UNiiMessageError(Exception):
    """
    UNii Base Message Error
    """


class UNiiChecksumError(UNiiMessageError):
    """
    UNii Checksum Error.

    When a received message fails validation against the checksum this error is thrown.
    """

    def __init__(self, expected_checksum: int, received_checksum: int):
        self._expected_checksum = expected_checksum
        self._received_checksum = received_checksum

    def __str__(self) -> str:
        return (
            f"Invalid checksum. Expected {self._expected_checksum}, "
            + f"received {self._received_checksum}."
        )


class UNiiIncompleteMessageError(UNiiMessageError):
    """
    UNii Checksum Error.

    When the length of a received message does not equal the message length header field this error
    is thrown.
    """

    def __init__(self, expected_lenght: int, received_lenght: int):
        self._expected_lenght = expected_lenght
        self._received_lenght = received_lenght

    def __str__(self) -> str:
        return (
            f"Incomplete message received. Expected {self._expected_lenght} bytes, "
            + f"received {self._received_lenght} bytes."
        )


class UNiiInvallidMessageError(UNiiMessageError):
    """
    UNii Invallid Message Error.

    When a message can not be parsed this error is thrown.
    """


class UNiiProtocolID(IntEnum):
    """
    UNii Protocol IDs

    Only no encryption and basic encryption are supported, advanced encryption is currently not
    implemented.
    """

    NO_ENCRYPTION: Final = 0x04
    BASIC_ENCRYPTION: Final = 0x05
    # Advanced encryption is currently not implemented.
    # ADVANCED_ENCRYPTION: Final = 0x??

    def __str__(self) -> str:
        return {
            self.NO_ENCRYPTION: "No Encryption",
            self.BASIC_ENCRYPTION: "Basic Encryption",
        }[self]


class UNiiPacketType(IntEnum):
    """
    UNii Packet Types
    """

    SESSION_SETUP: Final = 0x01
    NORMAL_CONECTION: Final = 0x02

    def __str__(self) -> str:
        return {
            self.SESSION_SETUP: "Session Setup",
            self.NORMAL_CONECTION: "Normal Connection",
        }[self]


class _UNiiMessage:
    # pylint: disable=too-few-public-methods
    """
    UNii Message class
    """

    _CRC16_INIT: Final = 0x0000
    _CRC16_POLYNOMIAL: Final = 0x1021
    _CRC16_REFIN: Final = False
    _CRC16_REFOUT: Final = False
    _CRC16_XOROUT: Final = 0x0000

    session_id: int | None = None
    tx_sequence: int | None = None
    rx_sequence: int | None = None
    command: UNiiCommand | None = None
    data: UNiiData | None = None

    def _calculate_crc16(self, message: bytes) -> int:
        """
        Calculates the CRC-16 checksum over the given message
        """
        crc = self._CRC16_INIT
        for _, byte in enumerate(message):
            crc ^= byte << 8
            for _ in range(8):
                if (crc & 0x8000) > 0:
                    crc <<= 1
                    crc ^= self._CRC16_POLYNOMIAL
                else:
                    crc <<= 1
        crc &= 0xFFFF
        # logger.debug("CRC-16 for 0x%s: %s", message.hex(), hex(crc))
        return crc

    def __str__(self) -> str:
        return str(
            {
                "session_id": self.session_id,
                "tx_sequence": self.tx_sequence,
                "rx_sequence": self.rx_sequence,
                "command": self.command,
                "data": self.data,
            }
        )


class UNiiRequestMessage(_UNiiMessage):
    """
    UNii Message class for sending

    All numbers are exchanged in big endian order (Most significant byte first)
    """

    _protocol_id: UNiiProtocolID | None = None

    @property
    def packet_type(self) -> UNiiPacketType | None:
        """
        Get packet type based on command
        """
        if self.command is None:
            return None
        if self.command < 0x0008:
            return UNiiPacketType.SESSION_SETUP
        return UNiiPacketType.NORMAL_CONECTION

    def _create_header(self):
        """
        Creates the header, first 14 bytes, of the message.
        """
        header = bytearray()
        # 2 byte Session ID
        header += self.session_id.to_bytes(2)
        # 4 byte Sequence number
        header += self.tx_sequence.to_bytes(4)
        # 4 byte Last received sequence number
        header += self.rx_sequence.to_bytes(4)
        # 1 byte Protocol ID
        header += self._protocol_id.to_bytes(1)
        # 1 byte Packet Type
        if self.command < 0x0008:
            header += UNiiPacketType.SESSION_SETUP.to_bytes(1)
        else:
            header += UNiiPacketType.NORMAL_CONECTION.to_bytes(1)
        # 2 byte Total Packet Length
        # To be replaced with the actual packet length once the total message is constructed.
        header.append(0x00)
        header.append(0x00)

        return header

    def _create_payload(self):
        """
        Creates the payload of the message, existing of command, data length and data.
        """
        payload = bytearray()

        # 2 byte Command
        payload += self.command.to_bytes(2)

        # 2 byte Data Length
        data_length = 0
        if self.data is not None:
            data_length = len(self.data.to_bytes())
        payload += data_length.to_bytes(2)

        # variable length The actual data
        if self.data is not None:
            payload += self.data.to_bytes()

        return payload

    def to_bytes(self, shared_key: bytes | None = None) -> bytes:
        """
        Converts the UNii Message to a sequence of bytes
        """
        if shared_key is None:
            self._protocol_id = UNiiProtocolID.NO_ENCRYPTION
        else:
            self._protocol_id = UNiiProtocolID.BASIC_ENCRYPTION

        header = self._create_header()
        payload = self._create_payload()

        # Add Padding
        packet_length = len(header) + len(payload) + 2  # Add 2 for the Checksum
        n_padding_bytes = 16 - (packet_length % 16)
        for _ in range(n_padding_bytes):
            payload.append(0x00)

        if shared_key is not None:
            # logger.debug("Payload: 0x%s", payload.hex())
            # logger.debug("Shared Key: 0x%s", shared_key.hex())

            # As Initialization Vector for the encryption the first 12 bytes of the header are used.
            initial_value = header[:12]
            # The block counter is reset to 0 for every new message.
            initial_value += b"\00\00\00\00"
            # logger.debug("Initial value: 0x%s", initial_value.hex())

            aes = AES.new(
                shared_key, AES.MODE_CTR, initial_value=initial_value, nonce=b""
            )
            payload = aes.encrypt(payload)
            # logger.debug("Encrypted Payload: 0x%s", payload.hex())

        message = header + payload

        # Insert Total Packet Length
        packet_length = len(message) + 2  # Add 2 for the Checksum
        packet_length = packet_length.to_bytes(2)
        message[12] = packet_length[0]
        message[13] = packet_length[1]

        # 2 byte Checksum
        crc = self._calculate_crc16(bytes(message))
        message += crc.to_bytes(2)

        # logger.debug("Message: %s", message.hex())
        return bytes(message)


class UNiiResponseMessage(_UNiiMessage):
    # pylint: disable=too-few-public-methods
    # pylint: disable=too-many-instance-attributes
    # pylint: disable=too-many-locals
    """
    UNii Message class for receiving
    """

    def __init__(self, message: bytes, shared_key: bytes | None = None):
        # pylint: disable=too-many-statements
        """ """
        assert message is not None

        # First 14 bytes Header
        header = message[:14]
        payload = message[14:-2]
        checksum = message[-2:]

        # Length
        packet_length = int.from_bytes(header[12:14])

        if packet_length != len(message):
            raise UNiiIncompleteMessageError(packet_length, len(message))

        # Last 2 bytes Checksum
        received_checksum = int.from_bytes(checksum)

        expected_checksum = self._calculate_crc16(message[0:-2])
        if received_checksum != expected_checksum:
            raise UNiiChecksumError(expected_checksum, received_checksum)

        # Session ID
        self.session_id = int.from_bytes(header[:2])

        # TX Sequence
        self.tx_sequence = int.from_bytes(header[2:6])
        # RX Sequence
        self.rx_sequence = int.from_bytes(header[6:10])
        # Protocol ID
        protocol_id = UNiiProtocolID(header[10])
        # Packet Type
        # packet_type = UNiiPacketType(header[11])
        # Length
        # message_length = int.from_bytes(header[11:13])

        if protocol_id == UNiiProtocolID.BASIC_ENCRYPTION and shared_key is not None:
            # As Initialization Vector for the encryption the first 12 bytes of the header are used.
            initial_value = header[:12]
            # The block counter is reset to 0 for every new message.
            initial_value += b"\00\00\00\00"

            payload = self._decrypt(shared_key, initial_value, payload)

        # Command
        command = int.from_bytes(payload[:2])

        try:
            self.command = UNiiCommand(command)
        except ValueError as ex:
            logger.warning(ex)
            self.command = None

        # Data length
        data_length = int.from_bytes(payload[2:4])

        # Data
        data: bytes | UNiiData | None = None
        if data_length > 0:
            data = payload[4 : 4 + data_length]
            # logger.debug("%s data: %i bytes, 0x%s", self.command, len(data), data.hex())
            try:
                match self.command:
                    # Generic
                    case UNiiCommand.GENERAL_RESPONSE:
                        data = UNiiResultCode(data)
                    # Equipment related
                    case UNiiCommand.RESPONSE_REQUEST_EQUIPMENT_INFORMATION:
                        data = UNiiEquipmentInformation(data)
                    # Section related
                    case UNiiCommand.RESPONSE_REQUEST_SECTION_ARRANGEMENT:
                        data = UNiiSectionArrangement(data)
                    case UNiiCommand.RESPONSE_REQUEST_SECTION_STATUS:
                        data = UNiiSectionStatus(data)
                    case UNiiCommand.RESPONSE_READY_TO_ARM_SECTIONS:
                        data = UNiiReadyToArmSectionStatus(data)
                    case UNiiCommand.RESPONSE_ARM_SECTION:
                        data = UNiiArmSectionStatus(data)
                    case UNiiCommand.RESPONSE_DISARM_SECTION:
                        data = UNiiDisarmSectionStatus(data)
                    # Input related
                    case UNiiCommand.RESPONSE_REQUEST_INPUT_ARRANGEMENT:
                        data = UNiiInputArrangement(data)
                    case UNiiCommand.INPUT_STATUS_CHANGED:
                        data = UNiiInputStatus(data)
                    case UNiiCommand.INPUT_STATUS_UPDATE:
                        data = UNiiInputStatusUpdate(data)
                    case UNiiCommand.RESPONSE_REQUEST_TO_BYPASS_AN_INPUT:
                        data = UNiiBypassZoneInputResult(data)
                    case UNiiCommand.RESPONSE_REQUEST_TO_UNBYPASS_AN_INPUT:
                        data = UNiiUnbypassZoneInputResult(data)
                    # Output related
                    case UNiiCommand.RESPONSE_REQUEST_OUTPUT_ARRANGEMENT:
                        data = UNiiOutputArrangement(data)
                    # Device related
                    case UNiiCommand.DEVICE_STATUS_CHANGED:
                        data = UNiiDeviceStatus(data)
                    # Event related
                    case UNiiCommand.EVENT_OCCURRED:
                        data = UNiiEventRecord(data)
                    case _:
                        data = UNiiRawData(data)
            except ValueError as ex:
                data = None
                if (
                    self.command
                    in [
                        UNiiCommand.RESPONSE_REQUEST_INPUT_ARRANGEMENT,
                        UNiiCommand.RESPONSE_REQUEST_OUTPUT_ARRANGEMENT,
                    ]
                    and str(ex) == "Invalid block number"
                ):
                    pass
                else:
                    logger.error(ex)
                    logger.debug("Payload: 0x%s", payload.hex())
                    raise UNiiInvallidMessageError() from ex
            except (LookupError, TypeError) as ex:
                logger.error(ex)
                logger.debug("Payload: 0x%s", payload.hex())
                data = None
                raise UNiiInvallidMessageError() from ex
            # Catch all exceptions while in development, to be removed once stable.
            # pylint: disable=broad-exception-caught
            except Exception as ex:
                logger.error(ex)
                logger.debug("Payload: 0x%s", payload.hex())
                data = None
                raise UNiiInvallidMessageError() from ex
        self.data = data

    def _decrypt(self, shared_key: bytes, initial_value: bytes, payload: bytes):
        aes = AES.new(shared_key, AES.MODE_CTR, initial_value=initial_value, nonce=b"")

        return aes.decrypt(payload)
