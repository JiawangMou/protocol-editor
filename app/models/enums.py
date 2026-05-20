from enum import Enum


class InterfaceType(Enum):
    ETHERNET = "ethernet"
    RS422 = "rs422"
    RS232 = "rs232"
    CAN = "can"
    CANFD = "canfd"


class ProtocolCategory(Enum):
    CONTROL_REQUEST = "control_request"
    PERIODIC_REPORT = "periodic_report"
    STATUS_CHANGE = "status_change"
    EXECUTION_FEEDBACK = "execution_feedback"


class DataType(Enum):
    UINT8 = "uint8"
    UINT16 = "uint16"
    UINT32 = "uint32"
    UINT64 = "uint64"
    INT8 = "int8"
    INT16 = "int16"
    INT32 = "int32"
    INT64 = "int64"
    FLOAT = "float"
    DOUBLE = "double"
    BOOL = "bool"
    STRING = "string"


class CRCType(Enum):
    NONE = "none"
    CRC8 = "crc8"
    CRC16_CCITT = "crc16_ccitt"
    CRC16_MODBUS = "crc16_modbus"
    CRC32 = "crc32"
    SUM8 = "sum8"
    XOR8 = "xor8"


class Endian(Enum):
    BIG = "big"
    LITTLE = "little"


class FieldSource(Enum):
    STATUS_VAR = "status_var"
    CONSTANT = "constant"
    CALCULATED = "calculated"
    CUSTOM = "custom"


class FrameLenMeaning(Enum):
    ALL = "all"
    DATA_ONLY = "data_only"
    HEAD_TO_CRC = "head_to_crc"


class Parity(Enum):
    NONE = "none"
    ODD = "odd"
    EVEN = "even"


class FlowControl(Enum):
    NONE = "none"
    RTS_CTS = "rts_cts"
    XON_XOFF = "xon_xoff"


class CANFrameType(Enum):
    STANDARD_DATA = "standard_data"
    STANDARD_REMOTE = "standard_remote"
    EXTENDED_DATA = "extended_data"
    EXTENDED_REMOTE = "extended_remote"
