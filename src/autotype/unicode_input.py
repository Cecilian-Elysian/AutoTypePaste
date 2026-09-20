"""以 Unicode 键盘事件注入文本，绕过输入法与键盘布局。"""

from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes
from typing import Any

_INPUT_KEYBOARD: int = 1
_KEYEVENTF_UNICODE: int = 0x0004
_KEYEVENTF_KEYUP: int = 0x0002
_BATCH_UNIT_LIMIT: int = 128

_USER32: Any = None


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_void_p),
    ]


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_void_p),
    ]


class _HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class _INPUTUnion(ctypes.Union):
    _fields_ = [
        ("ki", _KEYBDINPUT),
        ("mi", _MOUSEINPUT),
        ("hi", _HARDWAREINPUT),
    ]


class _INPUT(ctypes.Structure):
    _fields_ = [
        ("type", wintypes.DWORD),
        ("union", _INPUTUnion),
    ]


def type_text(text: str, interval: float) -> None:
    """以 KEYEVENTF_UNICODE 事件注入文本，不受输入法与键盘布局影响。

    Args:
        text: 要注入的文本。
        interval: 字符之间的间隔秒数；正数时逐字符注入并在字符间等待，
            零或负数时按块批量注入以减少系统调用次数。

    Raises:
        OSError: 系统未接受全部注入事件时抛出，常见于目标窗口以更高权限运行。
    """
    if sys.platform != "win32":
        return

    user32 = _user32()
    if interval > 0:
        for character in text:
            _send_units(user32, _code_units(character))
            time.sleep(interval)
        return

    units: list[int] = []
    for character in text:
        units.extend(_code_units(character))
        if len(units) >= _BATCH_UNIT_LIMIT:
            _send_units(user32, units)
            units.clear()
    if units:
        _send_units(user32, units)


def _user32() -> Any:
    """返回缓存的 user32 库，首次调用时加载并配置 SendInput 原型。"""
    global _USER32
    if _USER32 is None:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(_INPUT), ctypes.c_int]
        user32.SendInput.restype = wintypes.UINT
        _USER32 = user32
    return _USER32


def _code_units(character: str) -> list[int]:
    """返回字符对应的 UTF-16 码元序列。"""
    code = ord(character)
    if code <= 0xFFFF:
        return [code]
    code -= 0x10000
    return [0xD800 + (code >> 10), 0xDC00 + (code & 0x3FF)]


def _send_units(user32: Any, units: list[int]) -> None:
    """注入一组 UTF-16 码元的按下与释放事件，注入数量不足时抛出异常。"""
    total = 2 * len(units)
    events = (_INPUT * total)()
    for index, unit in enumerate(units):
        down = events[2 * index]
        down.type = _INPUT_KEYBOARD
        down.union.ki.wScan = unit
        down.union.ki.dwFlags = _KEYEVENTF_UNICODE
        up = events[2 * index + 1]
        up.type = _INPUT_KEYBOARD
        up.union.ki.wScan = unit
        up.union.ki.dwFlags = _KEYEVENTF_UNICODE | _KEYEVENTF_KEYUP
    sent = user32.SendInput(total, events, ctypes.sizeof(_INPUT))
    if sent != total:
        raise OSError(
            ctypes.get_last_error(),
            f"系统只接受了 {sent}/{total} 个键盘注入事件，目标窗口可能以管理员权限运行。",
        )
