"""
Implementation of the Alphatronics UNii library
"""

try:
    from ._version import __version__
except ModuleNotFoundError:
    pass
from .sia_code import SIACode
from .unii import (
    DEFAULT_PORT,
    UNii,
    UNiiCommand,
    UNiiData,
    UNiiEncryptionError,
    UNiiFeature,
    UNiiLocal,
)
from .unii_command_data import (
    UNiiInputState,
    UNiiInputStatusRecord,
    UNiiSection,
    UNiiSectionArmedState,
    UNiiSectionStatusRecord,
    UNiiSensorType,
)
