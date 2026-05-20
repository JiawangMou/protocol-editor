from __future__ import annotations
import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from app.models.protocol import Project, Node, Interface, Protocol, ProtocolField, StatusVariable, Connection
from app.models.protocol import (
    EthernetParams, RS422Params, RS232Params, CANParams, CANFDParams,
    UARTFrameConfig, CANFrameConfig, EthernetFrameConfig,
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
        # first pass: convert known enum fields
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


def load_project(filepath: str) -> Project:
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    # Reconstruct params and config objects
    _reconstruct(data)
    return _decode_dataclass(Project, data)


def _reconstruct(node: Any) -> None:
    """Walk the raw dict and replace params/frame_config with tagged objects."""
    if isinstance(node, dict):
        _type = node.get("_type", "")
        if _type:
            cls = _PARAMS_CLASS.get(_type) or _CONFIG_CLASS.get(_type)
            if cls:
                del node["_type"]
                for k, v in list(node.items()):
                    node[k] = _reconstruct(v)
                obj = cls(**node)
                node.clear()
                if isinstance(obj, UARTFrameConfig) or isinstance(obj, CANFrameConfig) or isinstance(obj, EthernetFrameConfig):
                    node["frame_config"] = obj
                elif isinstance(obj, EthernetParams) or isinstance(obj, RS422Params) or isinstance(obj, RS232Params) or isinstance(obj, CANParams) or isinstance(obj, CANFDParams):
                    node["params"] = obj
                return node
        for key, val in list(node.items()):
            node[key] = _reconstruct(val)
    elif isinstance(node, list):
        for i, item in enumerate(node):
            node[i] = _reconstruct(item)
    return node
