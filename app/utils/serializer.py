"""序列化/反序列化 — Project ↔ JSON 文件。

特性:
  - 自定义 _custom_asdict: 为已知 dataclass 添加 _type 标记, 确保反序列化时恢复正确类型
  - v1→v2 自动迁移: 旧格式 (nodes + Interface.type) → 新格式 (devices + bus_configs)
  - _reconstruct: 将 JSON dict 中的 _type 标记替换为真正的 dataclass 实例
  - _decode_dataclass: 递归解码并正确处理 enum 字段
"""
import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Union

from app.models.protocol import Project, Device, DeviceInterface, Protocol, ProtocolField, StatusVariable, Connection, BusConfig
from app.models.protocol import (
    EthernetParams, RS422Params, RS232Params, CANParams, CANFDParams,
    UARTFrameConfig, CANFrameConfig, EthernetFrameConfig,
    CRC_BYTE_SIZES,
)
from app.models.enums import *

# ── type tag map ──
_PARAMS_CLASS = {
    "EthernetParams": EthernetParams,
    "RS422Params": RS422Params,
    "RS232Params": RS232Params,
    "CANParams": CANParams,
    "CANFDParams": CANFDParams,
}
_CONFIG_CLASS = {
    "UARTFrameConfig": UARTFrameConfig,
    "CANFrameConfig": CANFrameConfig,
    "EthernetFrameConfig": EthernetFrameConfig,
}


def _enum_decode(cls, value):
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        try:
            return cls(value)
        except ValueError:
            return value
    return value


def _convert_enums(obj: Any) -> Any:
    """After from_dict, convert raw strings back to enum values."""
    if isinstance(obj, dict):
        for key, val in list(obj.items()):
            obj[key] = _convert_enums(val)
        return obj
    elif isinstance(obj, list):
        return [_convert_enums(v) for v in obj]
    return obj


def _decode_dataclass(cls, d: dict) -> Any:
    """Recursively decode a dict into the target dataclass."""
    field_types = {f.name: f.type for f in cls.__dataclass_fields__.values()}
    kwargs = {}
    for k, v in d.items():
        if k not in field_types:
            kwargs[k] = v
            continue
        ftype = field_types[k]
        # Handle Optional
        origin = getattr(ftype, "__origin__", None)
        if origin is Union:
            args = ftype.__args__
            non_none = [a for a in args if a is not type(None)]
            if non_none:
                ftype = non_none[0]
        # Handle list[...]
        origin = getattr(ftype, "__origin__", None)
        if origin is list:
            item_type = ftype.__args__[0] if ftype.__args__ else str
            new_list = []
            for item in v:
                if is_dataclass(item_type) and isinstance(item, dict):
                    new_list.append(_decode_dataclass(item_type, item))
                else:
                    new_list.append(item)
            kwargs[k] = new_list
        elif origin is dict:
            kwargs[k] = v
        elif isinstance(v, dict) and is_dataclass(ftype):
            kwargs[k] = _decode_dataclass(ftype, v)
        elif isinstance(v, str) and issubclass_safe(ftype, Enum):
            kwargs[k] = _enum_decode(ftype, v)
        else:
            kwargs[k] = v
    return cls(**kwargs)


def issubclass_safe(tp, parent):
    try:
        return issubclass(tp, parent)
    except TypeError:
        return False


def _class_hint(obj: Any) -> str:
    """Return a type tag for known param/config dataclasses."""
    cls_name = obj.__class__.__name__
    if cls_name in _PARAMS_CLASS or cls_name in _CONFIG_CLASS:
        return cls_name
    return ""


def _custom_asdict(obj: Any) -> Any:
    """Like dataclasses.asdict but adds a _type tag to known classes."""
    if is_dataclass(obj) and not isinstance(obj, type):
        result = {}
        cls_name = _class_hint(obj)
        if cls_name:
            result["_type"] = cls_name
        for field_info in obj.__dataclass_fields__.values():
            key = field_info.name
            value = getattr(obj, key)
            result[key] = _custom_asdict(value)
        return result
    elif isinstance(obj, list):
        return [_custom_asdict(v) for v in obj]
    elif isinstance(obj, dict):
        return {k: _custom_asdict(v) for k, v in obj.items()}
    elif isinstance(obj, Enum):
        return obj.value
    else:
        return obj


def save_project(project: Project, filepath: str) -> None:
    data = _custom_asdict(project)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _migrate_v1_to_v2(data: dict) -> dict:
    """将 v1 格式 (nodes + Interface.type/params) 迁移到 v2 (devices + bus_configs + DeviceInterface.bus_config_id)。

    迁移步骤:
      1. nodes → devices 字段重命名
      2. 从 v1 接口收集唯一总线类型, 为每种类型创建 BusConfig
      3. Interface → DeviceInterface: 添加 bus_config_id, 移除 type/params
      4. Connection: from_node_id → from_device_id, to_node_id → to_device_id
    """
    # 1. nodes → devices
    if "nodes" in data and "devices" not in data:
        data["devices"] = data.pop("nodes")

    # 2. 从 v1 接口收集唯一总线类型, 创建 BusConfig
    if "bus_configs" not in data:
        bus_configs: dict[str, dict] = {}
        _counter_local = 0
        for dev in data.get("devices", []):
            for iface in dev.get("interfaces", []):
                itype = iface.get("type", "")
                if itype and itype not in bus_configs:
                    _counter_local += 1
                    bus_name = {"ethernet": "以太网总线", "rs422": "RS-422总线",
                                "rs232": "RS-232总线", "can": "CAN总线", "canfd": "CAN FD总线"}.get(itype, f"总线{_counter_local}")
                    frame_config = {}
                    if itype in ("rs422", "rs232"):
                        frame_config = {
                            "_type": "UARTFrameConfig",
                            "start_flag_len": 0, "start_flag_mode": "fixed",
                            "start_flag_value": "", "msg_id_len": 1,
                            "frame_len_len": 1, "data_max_len": 256,
                            "crc_len": 2, "crc_type": "crc16_modbus",
                            "end_flag_len": 0, "end_flag_mode": "fixed",
                            "end_flag_value": "", "endian": "big",
                        }
                    elif itype in ("can", "canfd"):
                        frame_config = {
                            "_type": "CANFrameConfig",
                            "arbitration_id": "0x000", "frame_type": "standard_data",
                            "dlc": 8, "brs": False,
                        }
                    elif itype == "ethernet":
                        frame_config = {
                            "_type": "EthernetFrameConfig",
                            "protocol": "tcp", "header_len": 8, "msg_type_offset": 0,
                            "msg_type_len": 2, "seq_offset": -1, "seq_len": 2,
                            "data_len_offset": -1, "data_len_len": 2, "timestamp_offset": -1,
                            "timestamp_len": 4, "data_offset": 4, "data_max_len": 1472,
                            "crc_type": "none", "crc_offset": -1, "endian": "big",
                        }
                    bus_configs[itype] = {
                        "id": f"bus{_counter_local}",
                        "name": bus_name,
                        "type": itype,
                        "frame_config": frame_config,
                    }
        data["bus_configs"] = list(bus_configs.values())

    # 3. 更新 Interface → DeviceInterface: 添加 bus_config_id, 移除 type/params
    bc_by_type: dict[str, str] = {}
    for bc in data.get("bus_configs", []):
        bc_by_type[bc.get("type", "")] = bc.get("id", "")

    for dev in data.get("devices", []):
        for iface in dev.get("interfaces", []):
            itype = iface.pop("type", "")
            iface.pop("params", None)
            if "bus_config_id" not in iface:
                iface["bus_config_id"] = bc_by_type.get(itype, "")

    # 4. 更新 Connection 字段名: from_node_id → from_device_id, to_node_id → to_device_id
    for conn in data.get("connections", []):
        if "from_node_id" in conn:
            conn["from_device_id"] = conn.pop("from_node_id")
        if "to_node_id" in conn:
            conn["to_device_id"] = conn.pop("to_node_id")

    # 5. 迁移旧 UARTFrameConfig → 新顺序结构格式
    for bc in data.get("bus_configs", []):
        _migrate_uart_config(bc.get("frame_config", {}))
    # 也处理新格式下直接加载的 bus_configs (v2 但旧 UART)
    if data.get("bus_configs"):
        for bc in data["bus_configs"]:
            _migrate_uart_config(bc.get("frame_config", {}))

    return data


def _migrate_uart_config(cfg: dict) -> dict:
    """将旧 UARTFrameConfig (偏移量导向) 迁移到新顺序结构格式。"""
    if not cfg or cfg.get("_type") != "UARTFrameConfig":
        return cfg
    # 检测旧格式: 有 sync_word_len 且没有 start_flag_len
    if "sync_word_len" not in cfg or "start_flag_len" in cfg:
        return cfg
    # 提取旧字段
    sync_word_len = cfg.pop("sync_word_len", 2)
    sync_word = cfg.pop("sync_word", "A55A")
    cfg.pop("msg_id_offset", None)
    msg_id_len = cfg.pop("msg_id_len", 1)
    cfg.pop("src_addr_offset", None)
    cfg.pop("src_addr_len", None)
    cfg.pop("dst_addr_offset", None)
    cfg.pop("dst_addr_len", None)
    cfg.pop("frame_len_offset", None)
    frame_len_len = cfg.pop("frame_len_len", 1)
    cfg.pop("frame_len_meaning", None)
    cfg.pop("data_offset", None)
    data_max_len = cfg.pop("data_max_len", 256)
    crc_type_str = cfg.pop("crc_type", "crc16_modbus")
    cfg.pop("crc_offset", None)
    cfg.pop("crc_range_start", None)
    cfg.pop("crc_range_end", None)
    stop_flag = cfg.pop("stop_flag", "")
    endian_str = cfg.pop("endian", "big")
    # CRC 字节数从类型推断
    try:
        crt = CRCType(crc_type_str)
    except ValueError:
        crt = CRCType.CRC16_MODBUS
    crc_len = CRC_BYTE_SIZES.get(crt, 2)
    # 写入新字段
    cfg["start_flag_len"] = sync_word_len if sync_word else 0
    cfg["start_flag_mode"] = "fixed"
    cfg["start_flag_value"] = sync_word if sync_word else ""
    cfg["msg_id_len"] = msg_id_len
    cfg["frame_len_len"] = frame_len_len
    cfg["data_max_len"] = data_max_len
    cfg["crc_len"] = crc_len
    cfg["crc_type"] = crc_type_str
    cfg["end_flag_len"] = len(stop_flag) // 2 if stop_flag else 0
    cfg["end_flag_mode"] = "fixed"
    cfg["end_flag_value"] = stop_flag if stop_flag else ""
    cfg["endian"] = endian_str
    return cfg


def load_project(filepath: str) -> Project:
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    # v1→v2 迁移
    data = _migrate_v1_to_v2(data)
    # 替换 params 和 frame_config 中的 _type 标记对象
    _reconstruct(data)
    return _decode_dataclass(Project, data)


def _reconstruct(node: Any) -> Any:
    """Walk the raw dict and replace params/frame_config with tagged objects."""
    if isinstance(node, dict):
        _type = node.get("_type", "")
        if _type:
            cls = _PARAMS_CLASS.get(_type) or _CONFIG_CLASS.get(_type)
            if cls:
                del node["_type"]
                for k, v in list(node.items()):
                    node[k] = _reconstruct(v)
                # 使用 _decode_dataclass 以正确转换 enum 字段
                return _decode_dataclass(cls, node)
        for key, val in list(node.items()):
            node[key] = _reconstruct(val)
    elif isinstance(node, list):
        for i, item in enumerate(node):
            node[i] = _reconstruct(item)
    return node
