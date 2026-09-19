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
    """以 KEYEVENTF_UNICODE 事件逐字符注入文本，不受输入法与键盘布局影响。

    Args:
        text: 要注入的文本。
        interval: 字符之间的间隔秒数，零或负数表示不等待。
    """
    if sys.platform != "win32":
        return

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(_INPUT), ctypes.c_int]
    user32.SendInput.restype = wintypes.UINT
    for character in text:
        for unit in _code_units(character):
            _send_unit(user32, unit)
        if interval > 0:
            time.sleep(interval)


def _code_units(character: str) -> list[int]:
    """返回字符对应的 UTF-16 码元序列。"""
    code = ord(character)
    if code <= 0xFFFF:
        return [code]
    code -= 0x10000
    return [0xD800 + (code >> 10), 0xDC00 + (code & 0x3FF)]


def _send_unit(user32: Any, unit: int) -> None:
    """注入单个 UTF-16 码元的按下与释放事件。"""
    events = (_INPUT * 2)()
    events[0].type = _INPUT_KEYBOARD
    events[0].union.ki.wScan = unit
    events[0].union.ki.dwFlags = _KEYEVENTF_UNICODE
    events[1].type = _INPUT_KEYBOARD
    events[1].union.ki.wScan = unit
    events[1].union.ki.dwFlags = _KEYEVENTF_UNICODE | _KEYEVENTF_KEYUP
    user32.SendInput(2, events, ctypes.sizeof(_INPUT))
