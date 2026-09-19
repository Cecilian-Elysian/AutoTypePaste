"""读取和校验 AutoTypePaste 的外部运行配置。"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CONFIG_FILENAME: str = "config.json"

DEFAULT_SLOT2_HOTKEY: str = "<ctrl>+<f10>"
DEFAULT_HISTORY_SIZE: int = 5
DEFAULT_FEEDBACK: bool = True
DEFAULT_DISABLE_IME: bool = True
DEFAULT_UNICODE_INPUT: bool = True


class ConfigError(ValueError):
    """表示配置文件缺失或内容不合法。"""


@dataclass(frozen=True, slots=True)
class AppConfig:
    """AutoTypePaste 的热键和输入时序配置。"""

    hotkey: str
    exit_hotkey: str
    character_interval: float
    start_delay: float
    slot2_hotkey: str = DEFAULT_SLOT2_HOTKEY
    history_size: int = DEFAULT_HISTORY_SIZE
    feedback: bool = DEFAULT_FEEDBACK
    disable_ime: bool = DEFAULT_DISABLE_IME
    unicode_input: bool = DEFAULT_UNICODE_INPUT


def default_config_path() -> Path:
    """返回当前运行方式对应的外部配置文件路径。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / CONFIG_FILENAME
    return Path.cwd() / CONFIG_FILENAME


def load_config(path: Path | None = None) -> AppConfig:
    """从 JSON 文件读取并校验运行配置，可选字段缺省时使用内置默认值。

    Args:
        path: 要读取的配置路径；省略时使用当前运行方式的默认路径。

    Returns:
        校验通过的运行配置。

    Raises:
        ConfigError: 配置文件不存在、不是 JSON 对象或字段值不合法。
    """
    config_path = path or default_config_path()
    try:
        raw: Any = json.loads(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ConfigError(f"未找到配置文件：{config_path}") from error
    except json.JSONDecodeError as error:
        raise ConfigError(f"配置文件不是有效 JSON：第 {error.lineno} 行第 {error.colno} 列") from error

    if not isinstance(raw, dict):
        raise ConfigError("配置文件根节点必须是 JSON 对象")

    hotkey = _required_string(raw, "hotkey")
    exit_hotkey = _required_string(raw, "exit_hotkey")
    character_interval = _required_nonnegative_number(raw, "character_interval", allow_zero=False)
    start_delay = _required_nonnegative_number(raw, "start_delay", allow_zero=True)
    slot2_hotkey = _optional_string(raw, "slot2_hotkey", DEFAULT_SLOT2_HOTKEY)
    history_size = _optional_int(raw, "history_size", DEFAULT_HISTORY_SIZE, minimum=1)
    feedback = _optional_bool(raw, "feedback", DEFAULT_FEEDBACK)
    disable_ime = _optional_bool(raw, "disable_ime", DEFAULT_DISABLE_IME)
    unicode_input = _optional_bool(raw, "unicode_input", DEFAULT_UNICODE_INPUT)
    return AppConfig(
        hotkey,
        exit_hotkey,
        character_interval,
        start_delay,
        slot2_hotkey,
        history_size,
        feedback,
        disable_ime,
        unicode_input,
    )


def _required_string(values: dict[str, Any], name: str) -> str:
    """读取必填非空字符串字段。"""
    value = values.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"配置项 {name} 必须是非空字符串")
    return value


def _required_nonnegative_number(values: dict[str, Any], name: str, *, allow_zero: bool) -> float:
    """读取必填非负数值字段。"""
    value = values.get(name)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"配置项 {name} 必须是数字")
    number = float(value)
    if number < 0 or (number == 0 and not allow_zero):
        minimum = "大于 0" if not allow_zero else "大于或等于 0"
        raise ConfigError(f"配置项 {name} 必须{minimum}")
    return number


def _optional_string(values: dict[str, Any], name: str, default: str) -> str:
    """读取可选非空字符串字段，缺省时返回默认值。"""
    value = values.get(name)
    if value is None:
        return default
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"配置项 {name} 必须是非空字符串")
    return value


def _optional_int(values: dict[str, Any], name: str, default: int, minimum: int) -> int:
    """读取可选整数字段，缺省时返回默认值。"""
    value = values.get(name)
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"配置项 {name} 必须是整数")
    if value < minimum:
        raise ConfigError(f"配置项 {name} 必须大于或等于 {minimum}")
    return value


def _optional_bool(values: dict[str, Any], name: str, default: bool) -> bool:
    """读取可选布尔字段，缺省时返回默认值。"""
    value = values.get(name)
    if value is None:
        return default
    if not isinstance(value, bool):
        raise ConfigError(f"配置项 {name} 必须是布尔值")
    return value
