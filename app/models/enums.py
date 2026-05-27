"""领域枚举定义 — 通讯接口类型、协议分类、数据类型、校验算法等。"""
from enum import Enum


class InterfaceType(Enum):
    """物理总线/接口类型"""
    ETHERNET = "ethernet"
    RS422 = "rs422"
    RS232 = "rs232"
    CAN = "can"
    CANFD = "canfd"


class ProtocolCategory(Enum):
    """协议消息分类 (决定通讯方式)"""
    CONTROL_REQUEST = "control_request"      # 控制/请求指令
    PERIODIC_REPORT = "periodic_report"      # 周期上报消息
    STATUS_CHANGE = "status_change"          # 状态变化上报消息
    EXECUTION_FEEDBACK = "execution_feedback"  # 执行结果反馈消息


class DataType(Enum):
    """协议字段数据类型, 对应固定的字节长度 (见 DATA_TYPE_BYTE_SIZES)"""
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
    """CRC 校验算法类型"""
    NONE = "none"
    CRC8 = "crc8"
    CRC16_CCITT = "crc16_ccitt"
    CRC16_MODBUS = "crc16_modbus"
    CRC32 = "crc32"
    SUM8 = "sum8"    # 累加和校验
    XOR8 = "xor8"    # 异或校验


class Endian(Enum):
    """字节序"""
    BIG = "big"
    LITTLE = "little"


class FieldSource(Enum):
    """协议字段的数据来源"""
    STATUS_VAR = "status_var"    # 绑定状态量
    CONSTANT = "constant"        # 常量值
    CALCULATED = "calculated"    # 计算值 (如 CRC)
    CUSTOM = "custom"            # 自定义填充


class FrameLenMeaning(Enum):
    """帧长度字段的含义"""
    ALL = "all"                    # 包含整个帧
    DATA_ONLY = "data_only"        # 仅数据区
    HEAD_TO_CRC = "head_to_crc"   # 从帧头到 CRC 前


class Parity(Enum):
    """UART 校验位"""
    NONE = "none"
    ODD = "odd"
    EVEN = "even"


class FlowControl(Enum):
    """UART 流控"""
    NONE = "none"
    RTS_CTS = "rts_cts"
    XON_XOFF = "xon_xoff"


class CANFrameType(Enum):
    """CAN 帧类型"""
    STANDARD_DATA = "standard_data"
    STANDARD_REMOTE = "standard_remote"
    EXTENDED_DATA = "extended_data"
    EXTENDED_REMOTE = "extended_remote"


class FlagMode(Enum):
    """起始/结束标志配置模式"""
    FIXED = "fixed"                # 固定值, 总线级统一
    PER_PROTOCOL = "per_protocol"  # 每条协议独立配置
