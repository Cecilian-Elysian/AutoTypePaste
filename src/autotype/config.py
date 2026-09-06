"""读取和校验 AutoTypePaste 的外部运行配置。"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CONFIG_FILENAME: str = "config.json"


class ConfigError(ValueError):
    """表示配置文件缺失或内容不合法。"""


@dataclass(frozen=True, slots=True)
class AppConfig:
    """AutoTypePaste 的热键和输入时序配置。"""

    hotkey: str
    exit_hotkey: str
    character_interval: float
    start_delay: float


def default_config_path() -> Path:
    """返回当前运行方式对应的外部配置文件路径。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / CONFIG_FILENAME
    return Path.cwd() / CONFIG_FILENAME


def load_config(path: Path | None = None) -> AppConfig:
    """从 JSON 文件读取并校验运行配置。

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
    return AppConfig(hotkey, exit_hotkey, character_interval, start_delay)


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
