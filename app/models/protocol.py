from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Optional, Union
from .enums import *


# ── ID generation ──
_counter: int = 0


def _new_id(prefix: str = "") -> str:
    global _counter
    _counter += 1
    return f"{prefix}{_counter}"


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
    sync_word_len: int = 2
    sync_word: str = "A55A"
    msg_id_offset: int = 2
    msg_id_len: int = 1
    src_addr_offset: int = -1
    src_addr_len: int = 1
    dst_addr_offset: int = -1
    dst_addr_len: int = 1
    frame_len_offset: int = -1
    frame_len_len: int = 1
    frame_len_meaning: FrameLenMeaning = FrameLenMeaning.ALL
    data_offset: int = 3
    data_max_len: int = 256
    crc_type: CRCType = CRCType.CRC16_MODBUS
    crc_offset: int = -1
    crc_range_start: int = 0
    crc_range_end: int = -1
    stop_flag: str = ""
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


# ── Interface ──

@dataclass
class Interface:
    id: str = field(default_factory=lambda: _new_id("if"))
    name: str = ""
    type: InterfaceType = InterfaceType.RS422
    params: Union[
        EthernetParams, RS422Params, RS232Params, CANParams, CANFDParams
    ] = field(default_factory=RS422Params)
    protocols: list[Protocol] = field(default_factory=list)


# ── Node ──

@dataclass
class Node:
    id: str = field(default_factory=lambda: _new_id("n"))
    name: str = ""
    description: str = ""
    x: float = 0.0
    y: float = 0.0
    interfaces: list[Interface] = field(default_factory=list)
    status_variables: list[StatusVariable] = field(default_factory=list)


# ── Connection ──

@dataclass
class Connection:
    id: str = field(default_factory=lambda: _new_id("c"))
    from_node_id: str = ""
    from_interface_id: str = ""
    to_node_id: str = ""
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
    nodes: list[Node] = field(default_factory=list)
    connections: list[Connection] = field(default_factory=list)

    def find_node(self, node_id: str) -> Optional[Node]:
        for n in self.nodes:
            if n.id == node_id:
                return n
        return None

    def find_interface(self, if_id: str) -> Optional[tuple[Node, Interface]]:
        for n in self.nodes:
            for iface in n.interfaces:
                if iface.id == if_id:
                    return n, iface
        return None

    def status_var_ref_count(self, sv_id: str) -> int:
        count = 0
        for node in self.nodes:
            for iface in node.interfaces:
                for proto in iface.protocols:
                    for fld in proto.fields:
                        if fld.status_var_ref == sv_id:
                            count += 1
        return count

    def find_status_var(self, sv_id: str) -> Optional[tuple[Node, StatusVariable]]:
        for node in self.nodes:
            for sv in node.status_variables:
                if sv.id == sv_id:
                    return node, sv
        return None
