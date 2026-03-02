# pylint: disable=too-many-lines
"""
Data classes used by the UNii library.
"""

import logging
import string
from abc import ABC, abstractmethod
from datetime import datetime
from enum import IntEnum, IntFlag, auto
from typing import Final

import semver

from .sia_code import SIACode

logger = logging.getLogger(__name__)

# Helper functions


def bit_position_to_numeric(data: bytes) -> list[int]:
    """
    Returns which bits in an array of bytes are set, LSB first.

    00001010 => [2, 4]
    """
    data = int.from_bytes(data)
    numerics = []
    for i in range(0, 31):
        bit_position: int = pow(2, i)
        if data & bit_position:
            numerics.append(i + 1)
    return numerics


def bcd_encode(data: str) -> bytes:
    """ "
    Encodes numeric string values in BCD format padded with zeroes to the right.

    https://en.wikipedia.org/wiki/Binary-coded_decimal

    Example implementation from:
    """
    assert data.isdigit()

    # Add trailing zeroes
    while len(data) < 16:
        data += "0"
    logger.debug("Data: %s", data)

    return bytes.fromhex(data)


def decode_and_strip(data: bytes) -> str:
    """Decode a byte array to UTF-8 and strip all leading and trailing whitespace and \x00."""
    return data.decode("utf-8", "replace").strip(string.whitespace + "\x00")


def input_index_to_number(input_index: int) -> int:
    """Translate input index to input number according to Appendix 4 of the UNii API."""
    if input_index <= 511:
        return input_index + 1
    if 512 <= input_index <= 543:
        return input_index + 189
    # if 544 <= input_index <= 575:
    #     return -1
    if 576 <= input_index <= 639:
        return input_index + 25
    if 640 <= input_index <= 688:
        return input_index + 161
    # if 689 <= input_index <= 705:
    #     return -1
    if 706 <= input_index <= 962:
        return input_index + 295

    return -1


def input_number_to_index(input_number: int) -> int:
    """Translate input number to input index according to Appendix 4 of the UNii API."""
    if 1 <= input_number <= 512:
        return input_number - 1
    if 701 <= input_number <= 732:
        return input_number - 189
    if 601 <= input_number <= 664:
        return input_number - 25
    if 801 <= input_number <= 848:
        return input_number - 161
    if 1001 <= input_number <= 1128:
        return input_number - 295

    return -1


# Generic command data classes


class UNiiData(ABC):
    # pylint: disable=too-few-public-methods
    """
    UNii Base data class.

    All data classes which are used to send or receive data should inherit from this class.
    """


class UNiiSendData(ABC):
    # pylint: disable=too-few-public-methods
    """
    Method which should be implemented by data classes which are used to send data.
    """

    @abstractmethod
    def to_bytes(self):
        """
        Converts a message to bytes which can be send to the UNii.
        """
        raise NotImplementedError


class UNiiRawData(UNiiData, UNiiSendData):
    # pylint: disable=too-few-public-methods
    """
    UNii Raw data class.

    This dataclass represents the send or received data as a raw array of binary data and can be
    used when no other data classes are available.
    """

    def __init__(self, raw_data):
        self.raw_data = raw_data

    def to_bytes(self):
        return self.raw_data

    def __repr__(self) -> str:
        return "0x" + self.raw_data.hex()


class UNiiResultCode(IntEnum):
    """
    UNii Result Code data class.

    This data class is used as an ACK or NACK response from both sides for the defined commands.
    """

    # pylint: disable=too-few-public-methods

    OK: Final = 0x0000
    ERROR: Final = 0x0001

    @classmethod
    def _missing_(cls, value):
        if isinstance(value, (bytes, bytearray)):
            return cls(int.from_bytes(value))
        return super()._missing_(value)


# Equipment related
class UNiiEquipmentInformation(UNiiData):
    # pylint: disable=too-few-public-methods
    # pylint: disable=too-many-instance-attributes
    """
    UNii Equipment Information data class.

    This data class contains the response of the "Request Equipment Information" command.
    """

    def __init__(self, data: bytes):
        # pylint: disable=consider-using-min-builtin
        # pylint: disable=too-many-locals
        """ """
        # Version
        version = data[1]
        if version not in [2, 3]:
            raise ValueError("Invalid message version")

        if version == 2:
            software_version = decode_and_strip(data[2:7])
            # The software version can be truncated, to make it a valid SemVer add 0 if the
            # software version ends with .
            if software_version.endswith("."):
                software_version += "0"

            software_date = decode_and_strip(data[7:19])
            self.software_date = datetime.strptime(software_date, "%d-%m-%Y").date()
        elif version == 3:
            software_version = decode_and_strip(data[2:19])
            self.software_date = None

        try:
            self.software_version = semver.Version.parse(software_version)
        except ValueError as ex:
            # Fall back to version 0.0.0 when SemVer can not be parsed.
            self.software_version = semver.Version(0, 0, 0)
            logger.warning(ex)

        device_name_length = data[19]
        self.device_name = decode_and_strip(data[20 : 20 + device_name_length])
        data = data[20 + device_name_length :]

        self.max_inputs = int.from_bytes(data[0:2])
        self.max_groups = data[2]
        self.max_sections = data[3]
        self.max_users = int.from_bytes(data[4:6])

        if version == 3:
            device_id_length = data[6]
            self.device_id = decode_and_strip(data[7 : 7 + device_id_length])
            self.serial_number = self.device_id[:9]
            mac_address = self.device_id[-12:]
            self.mac_address = ":".join(
                mac_address.lower()[i : i + 2] for i in range(0, 12, 2)
            )
        else:
            self.device_id = None
            self.serial_number = None
            self.mac_address = None

    def __str__(self) -> str:
        return str(
            {
                "software_version": self.software_version,
                "software_date": str(self.software_date),
                "device_name": self.device_name,
                "device_id": self.device_id,
                "serial_number": self.serial_number,
                "mac_address": self.mac_address,
            }
        )

    def __eq__(self, other) -> bool:
        if not isinstance(other, UNiiEquipmentInformation):
            # don't attempt to compare against unrelated types
            return NotImplemented

        return (
            self.software_version == other.software_version
            and self.software_date == other.software_date
            and self.device_name == other.device_name
            and self.max_inputs == other.max_inputs
            and self.max_groups == other.max_groups
            and self.max_sections == other.max_sections
            and self.max_users == other.max_users
            and self.device_id == other.device_id
            and self.serial_number == other.serial_number
            and self.mac_address == other.mac_address
        )


# Section related
class UNiiSection(dict):
    """
    UNii Section.
    """

    # Get dictionarry keys as attributes.
    __getattr__ = dict.get

    def __init__(self, data: bytes):
        # Version
        version = data[0]
        if version not in [0, 1]:
            raise ValueError("Invalid message version")

        self["active"] = data[1] == 1
        if version == 0:
            name = decode_and_strip(data[2:19])
        elif version == 1:
            name_length = data[2]
            name = decode_and_strip(data[3 : 3 + name_length])
        self["name"] = name


class UNiiSectionArrangement(dict, UNiiData):
    """
    UNii Section Arrangement data class.

    This data class contains the response of the "Request Section Arrangement" command.
    """

    def __init__(self, data: bytes):
        offset = 0
        index = 1
        while offset < len(data):
            # Version
            version = data[0 + offset]
            if version not in [0, 1]:
                raise ValueError("Invalid message version")

            section_length = 19
            if version == 1:
                section_length = data[offset + 2] + 3
            section = UNiiSection(data[offset : offset + section_length])
            section["number"] = index
            self[index] = section

            index += 1
            offset += section_length


class UNiiSectionArmedState(IntEnum):
    """
    The available armed states.
    """

    NOT_PROGRAMMED: Final = 0
    ARMED: Final = 1
    DISARMED: Final = 2
    ALARM: Final = 7
    EXIT_TIMER: Final = 8
    ENTRY_TIMER: Final = 9

    def __repr__(self) -> str:
        return self.name

    def __str__(self) -> str:
        return self.name.lower()


class UNiiSectionStatusRecord(dict):
    """
    UNii Section Status record.
    """

    # Get dictionarry keys as attributes.
    __getattr__ = dict.get

    def __init__(self, data: bytes):
        self["number"] = data[0]
        self["armed_state"] = UNiiSectionArmedState(data[1])


class UNiiSectionStatus(dict, UNiiData):
    """
    UNii Section Status data class.

    This data class contains the response of the "Request Section Status" command.
    """

    # Get dictionarry keys as attributes.
    __getattr__ = dict.get

    def __init__(self, data: bytes):
        # Split data in chunks of 2 bytes
        chunks = [data[pos : pos + 2] for pos in range(0, len(data), 2)]
        # Convert chunks to Section Status Records
        for chunk in chunks:
            section_status_record = UNiiSectionStatusRecord(chunk)
            self[section_status_record.number] = section_status_record


class UNiiArmDisarmSection(UNiiData, UNiiSendData):
    # pylint: disable=too-few-public-methods
    """
    This data class contains the request for "Request Arm Section" and "Request Disarm Section"
    """

    def __init__(self, code: str, number: int):
        self.code = code
        self.number = number

    def to_bytes(self):
        bytes_ = bytearray()
        bytes_.append(0x00)
        bytes_.extend(bcd_encode(self.code))
        bytes_.extend(self.number.to_bytes(1))
        bytes_.append(0x01)
        return bytes(bytes_)


class UNiiReadyToArmState(IntEnum):
    # pylint: disable=too-few-public-methods
    """
    The available Ready To Arm states.
    """

    NOT_PROGRAMMED: Final = 0
    SECTION_ARMED: Final = 1
    # SECTION_DISARMED: Final = 2
    SECTION_READY_FOR_ARMING: Final = 3
    SECTION_NOT_READY_FOR_ARMING: Final = 4
    NOT_AUTHORIZED_TO_ARM: Final = 5
    SYSTEM_ERROR: Final = 6

    def __repr__(self) -> str:
        return self.name

    def __str__(self) -> str:
        return self.name.lower()


class UNiiReadyToArmSectionStatus(UNiiData):
    # pylint: disable=too-few-public-methods
    """
    UNii Ready To Arm Section State data class
    """

    def __init__(self, data: bytes):
        self.section_number = data[0]
        self.section_state = data[1]


class UNiiArmState(IntEnum):
    # pylint: disable=too-few-public-methods
    """
    The available Arm states.
    """

    NO_CHANGE: Final = 0
    SECTION_ARMED: Final = 1
    ARMING_FAILED_SECTION_NOT_READY: Final = 2
    ARMING_FAILED_NOT_AUTHORIZED: Final = 3

    def __repr__(self) -> str:
        return self.name

    def __str__(self) -> str:
        return self.name.lower()


class UNiiArmSectionStatus(UNiiData):
    # pylint: disable=too-few-public-methods
    """
    UNii Arm Section State data class
    """

    def __init__(self, data: bytes):
        self.number = data[0]
        self.arm_state = UNiiArmState(data[1])

    def __repr__(self) -> str:
        return str({"number": self.number, "arm_state": self.arm_state})


class UNiiDisarmState(IntEnum):
    # pylint: disable=too-few-public-methods
    """
    The available Disarm states.
    """

    NO_CHANGE: Final = 0
    SECTION_DISARMED: Final = 1
    DISARMING_FAILED: Final = 2
    DISARMING_FAILED_NOT_AUTHORIZED: Final = 3

    def __repr__(self) -> str:
        return self.name

    def __str__(self) -> str:
        return self.name.lower()


class UNiiDisarmSectionStatus(UNiiData):
    # pylint: disable=too-few-public-methods
    """
    UNii Disarm Section State data class
    """

    def __init__(self, data: bytes):
        self.number = data[0]
        self.disarm_state = UNiiDisarmState(data[1])

    def __repr__(self) -> str:
        return str({"number": self.number, "disarm_state": self.disarm_state})


# Input related


class UNiiInputType(IntEnum):
    """
    The available input types.
    """

    WIRED: Final = auto()
    KEYPAD: Final = auto()
    SPARE: Final = auto()
    WIRELESS: Final = auto()
    KNX: Final = auto()
    DOOR: Final = auto()

    def __repr__(self) -> str:
        return self.name

    def __str__(self) -> str:
        return self.name.lower()


class UNiiSensorType(IntEnum):
    """
    The different kind of sensor types.
    """

    NOT_ACTIVE: Final = 0
    BURGLARY: Final = 1
    FIRE: Final = 2
    TAMPER: Final = 3
    HOLDUP: Final = 4
    MEDICAL: Final = 5
    GAS: Final = 6
    WATER: Final = 7
    TECHNICAL: Final = 8
    DIRECT_DIALER_INPUT: Final = 9
    KEYSWITCH: Final = 10
    NO_ALARM: Final = 11
    EN54_FIRE: Final = 12
    EN54_FIRE_MCP: Final = 13
    EN54_FAULT: Final = 14
    GLASSBREAK: Final = 15

    def __repr__(self) -> str:
        return self.name

    def __str__(self) -> str:
        return self.name.lower()


class UNiiReaction(IntEnum):
    """
    The different kind of reactions.
    """

    DIRECT: Final = 0
    DELAYED: Final = 1
    FOLLOWER: Final = 2
    TWENT_FOUR_HOUR: Final = 3
    LAST_DOOR: Final = 4
    DELAYED_ALARM: Final = 5

    def __repr__(self) -> str:
        return self.name

    def __str__(self) -> str:
        return self.name.lower()


class UNiiInput(dict):
    """
    UNii Input.
    """

    # Get dictionarry keys as attributes.
    __getattr__ = dict.get

    def __init__(self, data: bytes):
        input_number = int.from_bytes(data[0:2])
        self["number"] = input_number

        input_type = UNiiInputType.SPARE
        if 1 <= input_number <= 512:
            input_type = UNiiInputType.WIRED
        elif 701 <= input_number <= 732:
            input_type = UNiiInputType.KEYPAD
        elif 601 <= input_number <= 664:
            input_type = UNiiInputType.WIRELESS
        elif 801 <= input_number <= 845:
            input_type = UNiiInputType.KNX
        elif 1001 <= input_number <= 1128:
            input_type = UNiiInputType.DOOR
        self["input_type"] = input_type

        self["sensor_type"] = UNiiSensorType(data[2])
        self["reaction"] = UNiiReaction(data[3])
        name_length = data[4]
        name = None
        if name_length > 0:
            name = decode_and_strip(data[5 : 5 + name_length])
        self["name"] = name
        self["sections"] = bit_position_to_numeric(data[5 + name_length :])
        self["status"] = UNiiInputState.DISABLED


class UNiiInputArrangement(dict, UNiiData):
    # pylint: disable=too-few-public-methods
    """
    UNii Input Arrangement data class.

    This data class contains the response of the "Request Input Arrangement" command.
    """

    def __init__(self, data: bytes):
        """ """
        # Version
        version = data[1]
        if version != 2:
            raise ValueError("Invalid message version")

        # Block Number
        block_number = int.from_bytes(data[2:4])

        if block_number == 0xFFFF:
            raise ValueError("Invalid block number")

        self.block_number = block_number

        offset = 4
        while offset < len(data):
            name_length = data[4 + offset]
            input_information = data[offset : 9 + offset + name_length]
            input_information = UNiiInput(input_information)
            self[input_information.number] = input_information

            offset += 9 + name_length

    def __str__(self) -> str:
        return str({"block_number": self.block_number, "inputs": super().__str__()})


class UNiiInputState(IntEnum):
    """
    The available input states.
    """

    INPUT_OK: Final = 0x0
    ALARM: Final = 0x1
    TAMPER: Final = 0x2
    MASKING: Final = 0x4
    DISABLED: Final = 0xF

    def __repr__(self) -> str:
        return self.name

    def __str__(self) -> str:
        return self.name.lower()


class UNiiInputStatusRecord(dict):
    """
    UNii Input Status record.
    """

    # Get dictionarry keys as attributes.
    __getattr__ = dict.get

    def __init__(self, data: int):
        self["status"] = UNiiInputState(data & 0x0F)
        self["bypassed"] = data & 0b00010000 == 0b00010000
        self["alarm_memorized"] = data & 0b00100000 == 0b00100000
        self["low_battery"] = data & 0b01000000 == 0b01000000
        self["supervision"] = data & 0b10000000 == 0b10000000


class UNiiInputStatus(dict, UNiiData):
    # pylint: disable=too-few-public-methods
    """
    UNii Input Status data class.
    """

    def __init__(self, data: bytes):
        # Version
        version = data[1]
        if version != 2:
            raise ValueError()

        for index, input_status in enumerate(data[2:]):
            input_status = UNiiInputStatusRecord(input_status)
            input_status["number"] = input_index_to_number(index)

            if input_status.number >= 0:
                self[input_status.number] = input_status


class UNiiInputStatusUpdate(UNiiInputStatusRecord, UNiiData):
    # pylint: disable=too-few-public-methods
    """
    UNii Input Status Update data class.
    """

    # Get dictionarry keys as attributes.
    __getattr__ = dict.get

    def __init__(self, data: bytes):
        # Version
        version = data[1]
        if version != 2:
            raise ValueError()

        super().__init__(data[4])
        self["number"] = int.from_bytes(data[2:4])


class UNiiBypassMode(IntEnum):
    """
    The different modes to (un)bypass a Zone or Input
    """

    USER_CODE = 0x00
    USER_NUMBER = 0x01


class UNiiBypassUnbypassZoneInput(UNiiData, UNiiSendData):
    # pylint: disable=too-few-public-methods
    """
    This data class contains the request for "Request to Bypass a Zone/Input" and "Request to
    Unbypass a Zone/Input".
    """

    def __init__(self, mode: UNiiBypassMode, code: str, number: int):
        self.mode = mode
        self.code = code[:8].ljust(8, "0")
        self.number = number

    def to_bytes(self):
        bytes_ = bytearray()
        bytes_.append(self.mode)
        bytes_.extend(bcd_encode(self.code))
        bytes_.extend(self.number.to_bytes(2))
        return bytes(bytes_)


class UNiiBypassZoneInputResult(UNiiData):
    # pylint: disable=too-few-public-methods
    """
    Result of bypassing a zone or input.
    """
    NOT_PROGRAMMED = 0
    SUCCESSFUL = 1
    AUTHENTICATION_FAILED = 2
    NOT_ALLOWED = 3

    def __init__(self, data: bytes):
        self.number = int.from_bytes(data[:2])
        self.result = data[2]

    def __repr__(self) -> str:
        return str({"number": self.number, "result": self.result})


class UNiiUnbypassZoneInputResult(UNiiData):
    # pylint: disable=too-few-public-methods
    """
    Result of unbypassing a zone or input.
    """
    NOT_PROGRAMMED = 0
    SUCCESSFUL = 1
    AUTHENTICATION_FAILED = 2
    NOT_BYPASSED = 3

    def __init__(self, data: bytes):
        self.number = int.from_bytes(data[:2])
        self.result = data[2]

    def __repr__(self) -> str:
        return str({"number": self.number, "result": self.result})


# Output related


class UNiiOutputType(IntEnum):
    """
    The available output types.
    """

    NOT_ACTIVE: Final = 0
    DIRECT: Final = 1
    TIMED: Final = 2
    FOLLOW_INPUT: Final = 3


class UNiiOutput(dict):
    """
    UNii Output.
    """

    # Get dictionarry keys as attributes.
    __getattr__ = dict.get

    def __init__(self, data: bytes):
        output_number = int.from_bytes(data[0:2])
        self["number"] = output_number

        self["type"] = UNiiOutputType(data[2])

        name_length = data[3]
        name = None
        if name_length > 0:
            name = decode_and_strip(data[4 : 4 + name_length])
        self["name"] = name
        self["sections"] = bit_position_to_numeric(data[5 + name_length :])


class UNiiOutputArrangement(dict, UNiiData):
    # pylint: disable=too-few-public-methods
    """
    UNii Output Arrangement data class.

    This data class contains the response of the "Request Output Arrangement" command.
    """

    def __init__(self, data: bytes):
        """ """
        # Version
        version = data[1]
        if version != 1:
            raise ValueError("Invalid message version")

        # Block Number
        block_number = int.from_bytes(data[2:4])

        if block_number == 0xFFFF:
            raise ValueError("Invalid block number")

        self.block_number = block_number

        offset = 4
        while offset < len(data):
            name_length = data[3 + offset]
            output_information = data[offset : 8 + offset + name_length]
            output_information = UNiiOutput(output_information)
            self[output_information.number] = output_information

            offset += 8 + name_length

    def __str__(self) -> str:
        return str({"block_number": self.block_number, "inputs": super().__str__()})


# Device related


class UNiiDeviceStatusRecord(IntFlag):
    """
    UNii Device Status Record
    """

    LAN_CONNECTION_FAILURE: Final = 32762
    POWER_UNIT_FAILURE_RESTORED: Final = 16384
    POWER_UNIT_FAILURE: Final = 8192
    BATTERY_FAULT_RESTORED: Final = 4096
    BATTERY_FAULT: Final = 2048
    BATTERY_MISSING_RESTORED: Final = 1024
    BATTERY_MISSING: Final = 512
    DEVICE_PRESENT: Final = 256
    RS485_BUS_COMMUNICATION_FAILURE_RESTORED: Final = 128
    RS485_BUS_COMMUNICATION_FAILURE: Final = 64
    TAMPER_SWITCH_OPEN_RESTORED: Final = 32
    TAMPER_SWITCH_OPEN: Final = 16
    LOW_BATTERY_RESTORED: Final = 8
    LOW_BATTERY: Final = 4
    MAINS_FAILURE_RESTORED: Final = 2
    MAINS_FAILURE: Final = 1

    def __repr__(self) -> str:
        return str(self.name)


class UNiiDeviceStatus(UNiiData):
    # pylint: disable=too-few-public-methods
    """
    UNii Device Status data class.

    This data class contains the response of the "Request Device Status" command.
    """

    io_devices: list[UNiiDeviceStatusRecord]
    keyboard_devices: list[UNiiDeviceStatusRecord]
    wiegand_devices: list[UNiiDeviceStatusRecord]
    uwi_devices: list[UNiiDeviceStatusRecord]

    def __init__(self, data: bytes):
        # Version
        version = data[1]
        if version != 2:
            raise ValueError("Invalid message version")

        # Split data in chunks of 2 bytes
        chunks = [data[pos : pos + 2] for pos in range(2, len(data), 2)]
        # Convert chunks to list of Device Status Records
        device_status_records: list[UNiiDeviceStatusRecord] = [
            UNiiDeviceStatusRecord.from_bytes(chunk) for chunk in chunks
        ]

        # Control Panel
        self.control_panel = device_status_records[0]

        # IO Devices
        self.io_devices = device_status_records[1:16]

        # Keyboard Devices
        self.keyboard_devices = device_status_records[16:32]

        # Wiegand Devices
        self.wiegand_devices = device_status_records[32:48]

        # KNX Device
        self.knx_device = device_status_records[48]

        # UWI Devices
        self.uwi_devices = device_status_records[49:51]

        # Redundant Device
        redundant_device = None
        if len(device_status_records) == 52:
            redundant_device = device_status_records[51]
        self.redundant_device = redundant_device

    def __str__(self) -> str:
        return str(
            {
                "control_panel": self.control_panel,
                "io_devices": self.io_devices,
                "keyboard_devices": self.keyboard_devices,
                "wiegand_devices": self.wiegand_devices,
                "knx_device": self.knx_device,
                "uwi_devices": self.uwi_devices,
                "redundant_device": self.redundant_device,
            }
        )


# Event related


class UNiiEventRecord(UNiiData):
    """
    UNii Event Record data class.
    """

    # pylint: disable=too-few-public-methods
    # pylint: disable=too-many-instance-attributes

    event_description: str | None = None
    user_number: int | None = None
    user_name: str | None = None
    input_number: int | None = None
    input_name: str | None = None
    device_number: int | None = None
    device_name: str | None = None
    bus_number: int | None = None
    sections: list[int] | None = None
    sia_code: SIACode | None = None

    def __init__(self, data: bytes):
        # pylint: disable=consider-using-min-builtin
        # pylint: disable=too-many-locals
        """ """
        # Version
        version = data[1]
        if version != 3:
            raise ValueError("Invalid message version")

        # Event Number
        self.event_number = int.from_bytes(data[2:4])

        # Timestamp
        year = 1900 + data[4]
        month = data[5] + 1
        day = data[6]
        hour = data[7]
        minute = data[8]
        second = data[9]
        self.timestamp = datetime(year, month, day, hour, minute, second)

        data = data[10:]

        # Description
        event_description_length = data[0]
        if event_description_length > 0:
            self.event_description = decode_and_strip(
                data[1 : 1 + event_description_length]
            )

        data = data[1 + event_description_length :]

        # User
        user_number = int.from_bytes(data[0:2])
        if user_number > 0:
            self.user_number = user_number

        user_name_length = data[2]
        if user_name_length > 0:
            self.user_name = decode_and_strip(data[3 : 3 + user_name_length])

        data = data[3 + user_name_length :]

        # Input
        input_number = int.from_bytes(data[0:2])
        if input_number > 0:
            self.input_number = input_number

        input_name_length = data[2]
        if input_name_length > 0:
            self.input_name = decode_and_strip(data[3 : 3 + input_name_length])

        data = data[3 + input_name_length :]

        # Device
        device_number = int.from_bytes(data[0:2])
        if device_number > 0:
            self.device_number = device_number

        device_name_length = data[2]
        if device_name_length > 0:
            self.device_name = decode_and_strip(data[3 : 3 + device_name_length])

        data = data[3 + device_name_length :]

        # Bus
        self.bus_number = data[0]

        # Sections
        self.sections = bit_position_to_numeric(data[1:5])

        # SIA Code
        sia_code = decode_and_strip(data[5:7])
        if sia_code != "":
            try:
                self.sia_code = SIACode(sia_code)
            except ValueError as ex:
                logger.warning(ex)

    def __repr__(self) -> str:
        return str(
            {
                "event_number": self.event_number,
                "timestamp": str(self.timestamp),
                "event_description": self.event_description,
                "user_number": self.user_number,
                "user_name": self.user_name,
                "input_number": self.input_number,
                "input_name": self.input_name,
                "device_number": self.device_number,
                "device_name": self.device_name,
                "bus_number": self.bus_number,
                "sections": self.sections,
                "sia_code": self.sia_code,
            }
        )
