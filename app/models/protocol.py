"""数据模型 — Project / BusConfig / Device / Protocol 等核心 dataclass。

架构说明:
  - BusConfig: 总线级定义, 描述一种总线类型的物理参数与帧格式
  - Device: 单机级定义, 通过 DeviceInterface.bus_config_id 引用 BusConfig
  - DeviceInterface: 设备通讯接口, 不再直接存储 type/params, 改为引用总线
  - Protocol: 挂载在 DeviceInterface 下, 定义具体通讯协议及其字段
"""
from dataclasses import dataclass, field, asdict
from typing import Optional, Union
from .enums import *


# ── ID generation ──
_counter: int = 0


def _new_id(prefix: str = "") -> str:
    global _counter
    _counter += 1
    return f"{prefix}{_counter}"


def sync_counter_from_project(project: "Project"):
    """从已加载工程的各项 ID 中提取最大数字后缀, 同步全局 _counter。
    防止新建对象时产生重复 ID (counter 复位为0导致与已有 ID 碰撞)。"""
    global _counter
    max_n = 0
    for d in project.devices:
        max_n = max(max_n, _extract_num(d.id))
        for sv in d.status_variables:
            max_n = max(max_n, _extract_num(sv.id))
        for iface in d.interfaces:
            max_n = max(max_n, _extract_num(iface.id))
            for p in iface.protocols:
                max_n = max(max_n, _extract_num(p.id))
                for fld in p.fields:
                    max_n = max(max_n, _extract_num(fld.id))
    for bc in project.bus_configs:
        max_n = max(max_n, _extract_num(bc.id))
    for conn in project.connections:
        max_n = max(max_n, _extract_num(conn.id))
    _counter = max(_counter, max_n)


def _extract_num(id_str: str) -> int:
    """从 id 字符串 (如 'sv6', 'd2', 'p1') 提取末尾数字部分。"""
    num = ""
    for ch in reversed(id_str):
        if ch.isdigit():
            num = ch + num
        else:
            break
    return int(num) if num else 0


# ── 数据类型 → 字节长度映射 ──
DATA_TYPE_BYTE_SIZES: dict[DataType, int] = {
    DataType.UINT8: 1, DataType.INT8: 1, DataType.BOOL: 1,
    DataType.UINT16: 2, DataType.INT16: 2,
    DataType.UINT32: 4, DataType.INT32: 4, DataType.FLOAT: 4,
    DataType.UINT64: 8, DataType.INT64: 8, DataType.DOUBLE: 8,
    DataType.STRING: 0,
}

# ── CRC 类型 → 字节长度映射 ──
CRC_BYTE_SIZES: dict[CRCType, int] = {
    CRCType.NONE: 0,
    CRCType.CRC8: 1, CRCType.SUM8: 1, CRCType.XOR8: 1,
    CRCType.CRC16_CCITT: 2, CRCType.CRC16_MODBUS: 2,
    CRCType.CRC32: 4,
}


# ── Interface Params (by type) ──

@dataclass
class EthernetParams:
    ip: str = "192.168.1.1"
    port: int = 5000
    protocol: str = "tcp"
    mac_addr: str = ""


@dataclass
class UARTParams:
    port_name: str = "COM1"
    baud_rate: int = 115200
    data_bits: int = 8
    stop_bits: float = 1.0
    parity: Parity = Parity.NONE


@dataclass
class RS422Params(UARTParams):
    pass


@dataclass
class RS232Params(UARTParams):
    flow_control: FlowControl = FlowControl.NONE


@dataclass
class CANParams:
    channel: str = "can0"
    bitrate: int = 500000
    frame_format: str = "standard"
    termination: bool = True


@dataclass
class CANFDParams:
    channel: str = "can0"
    arb_bitrate: int = 500000
    data_bitrate: int = 2000000
    frame_format: str = "standard"


# ── Frame Config (by interface type) ──

@dataclass
class UARTFrameConfig:
    """UART 帧格式 — 顺序结构: [起始标志][信息标识][信息长度][信息内容][CRC校验][结束标志]"""
    start_flag_len: int = 0          # 起始标志字节长度, 0=不使用
    start_flag_mode: str = "fixed"   # "fixed" | "per_protocol"
    start_flag_value: str = ""       # hex值, mode=fixed时填写
    msg_id_len: int = 1              # 信息标识(消息ID)字节长度
    frame_len_len: int = 1           # 信息长度字段字节长度
    data_max_len: int = 256          # 信息内容最大长度(字节)
    crc_len: int = 2                 # CRC校验字节长度, 0=不使用
    crc_type: CRCType = CRCType.CRC16_MODBUS
    end_flag_len: int = 0            # 结束标志字节长度, 0=不使用
    end_flag_mode: str = "fixed"    # "fixed" | "per_protocol"
    end_flag_value: str = ""         # hex值, mode=fixed时填写
    endian: Endian = Endian.BIG


@dataclass
class CANFrameConfig:
    arbitration_id: str = "0x000"
    frame_type: CANFrameType = CANFrameType.STANDARD_DATA
    dlc: int = 8
    brs: bool = False


@dataclass
class EthernetFrameConfig:
    protocol: str = "tcp"
    header_len: int = 8
    msg_type_offset: int = 0
    msg_type_len: int = 2
    seq_offset: int = -1
    seq_len: int = 2
    data_len_offset: int = -1
    data_len_len: int = 2
    timestamp_offset: int = -1
    timestamp_len: int = 4
    data_offset: int = 4
    data_max_len: int = 1472
    crc_type: CRCType = CRCType.NONE
    crc_offset: int = -1
    endian: Endian = Endian.BIG


# ── Bus Config ──

@dataclass
class BusConfig:
    """总线配置 — 定义一种总线类型及其帧格式参数。"""
    id: str = field(default_factory=lambda: _new_id("bus"))
    name: str = ""
    type: InterfaceType = InterfaceType.RS422
    frame_config: Union[UARTFrameConfig, CANFrameConfig, EthernetFrameConfig] = field(
        default_factory=UARTFrameConfig
    )


# ── Protocol Field ──

@dataclass
class ProtocolField:
    id: str = field(default_factory=lambda: _new_id("f"))
    name: str = ""
    data_type: DataType = DataType.UINT8
    byte_length: int = 1
    source: FieldSource = FieldSource.CUSTOM
    status_var_ref: str = ""
    constant_value: str = ""
    description: str = ""
    unit: str = ""


# ── Status Variable ──

@dataclass
class StatusVariable:
    id: str = field(default_factory=lambda: _new_id("sv"))
    name: str = ""
    data_type: DataType = DataType.UINT16
    byte_length: int = 2
    unit: str = ""
    meaning: str = ""
    remarks: str = ""


# ── Protocol ──

@dataclass
class Protocol:
    id: str = field(default_factory=lambda: _new_id("p"))
    name: str = ""
    category: ProtocolCategory = ProtocolCategory.CONTROL_REQUEST
    comm_method: str = ""
    frame_config: Union[UARTFrameConfig, CANFrameConfig, EthernetFrameConfig] = field(
        default_factory=UARTFrameConfig
    )
    fields: list[ProtocolField] = field(default_factory=list)
    report_period_ms: int = 1000
    change_threshold: str = ""
    start_flag_value: str = ""      # 当总线起始标志=独立配置时, 此协议自定义起始标志hex
    end_flag_value: str = ""        # 当总线结束标志=独立配置时, 此协议自定义结束标志hex


# ── Device Interface ──

@dataclass
class DeviceInterface:
    """设备通讯接口 — 通过 bus_config_id 引用总线配置。"""
    id: str = field(default_factory=lambda: _new_id("if"))
    name: str = ""
    bus_config_id: str = ""
    protocols: list[Protocol] = field(default_factory=list)


# ── Device (原 Node) ──

@dataclass
class Device:
    """设备 (单机) — 挂载通讯接口和状态量。"""
    id: str = field(default_factory=lambda: _new_id("d"))
    name: str = ""
    description: str = ""
    x: float = 0.0
    y: float = 0.0
    interfaces: list[DeviceInterface] = field(default_factory=list)
    status_variables: list[StatusVariable] = field(default_factory=list)


# ── Connection ──

@dataclass
class Connection:
    id: str = field(default_factory=lambda: _new_id("c"))
    from_device_id: str = ""
    from_interface_id: str = ""
    to_device_id: str = ""
    to_interface_id: str = ""
    label: str = ""


# ── Project ──

@dataclass
class Project:
    name: str = ""
    version: str = "1.0"
    author: str = ""
    endian: Endian = Endian.BIG
    description: str = ""
    bus_configs: list[BusConfig] = field(default_factory=list)
    devices: list[Device] = field(default_factory=list)
    connections: list[Connection] = field(default_factory=list)

    def find_device(self, device_id: str) -> Optional[Device]:
        """按 ID 查找设备。"""
        for d in self.devices:
            if d.id == device_id:
                return d
        return None

    def find_bus_config(self, bus_id: str) -> Optional[BusConfig]:
        """按 ID 查找总线配置。"""
        for bc in self.bus_configs:
            if bc.id == bus_id:
                return bc
        return None

    def find_interface(self, if_id: str) -> Optional[tuple[Device, DeviceInterface]]:
        """按 ID 查找接口, 返回 (所属设备, 接口) 元组或 None。"""
        for d in self.devices:
            for iface in d.interfaces:
                if iface.id == if_id:
                    return d, iface
        return None

    def find_bus_config_for_interface(self, iface_id: str) -> Optional[BusConfig]:
        """根据接口 ID 找到其绑定的 BusConfig。"""
        result = self.find_interface(iface_id)
        if result:
            return self.find_bus_config(result[1].bus_config_id)
        return None

    def status_var_ref_count(self, sv_id: str) -> int:
        """统计某个状态量被协议字段引用的次数。"""
        count = 0
        for device in self.devices:
            for iface in device.interfaces:
                for proto in iface.protocols:
                    for fld in proto.fields:
                        if fld.status_var_ref == sv_id:
                            count += 1
        return count

    def find_status_var(self, sv_id: str) -> Optional[tuple[Device, StatusVariable]]:
        """按 ID 查找状态量, 返回 (所属设备, 状态量) 元组或 None。"""
        for device in self.devices:
            for sv in device.status_variables:
                if sv.id == sv_id:
                    return device, sv
        return None

    def find_protocol(self, proto_id: str) -> Optional[Protocol]:
        """按 ID 在全部设备中查找协议。"""
        for device in self.devices:
            for iface in device.interfaces:
                for proto in iface.protocols:
                    if proto.id == proto_id:
                        return proto
        return None

    def find_parent_device_of_protocol(self, proto_id: str) -> Optional[Device]:
        """查找包含指定协议的 Device (用于协议编辑器获取状态量列表)。"""
        for device in self.devices:
            for iface in device.interfaces:
                for proto in iface.protocols:
                    if proto.id == proto_id:
                        return device
        return None

    def find_parent_interface_of_protocol(self, proto_id: str) -> Optional[DeviceInterface]:
        """查找包含指定协议的 DeviceInterface。"""
        for device in self.devices:
            for iface in device.interfaces:
                for proto in iface.protocols:
                    if proto.id == proto_id:
                        return iface
        return None
