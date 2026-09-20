"""使用 Windows API 读取 Unicode 剪贴板文本。"""

from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any

CF_UNICODETEXT: int = 13
_OPEN_ATTEMPTS: int = 3
_OPEN_RETRY_INTERVAL: float = 0.02

_USER32: Any = None
_KERNEL32: Any = None


class ClipboardStatus(Enum):
    """剪贴板读取结果的分类状态。"""

    OK = auto()
    EMPTY = auto()
    NOT_TEXT = auto()
    LOCKED = auto()
    OS_ERROR = auto()


@dataclass(frozen=True, slots=True)
class ReadResult:
    """剪贴板读取结果，status 为 OK 时 text 为非空文本。"""

    status: ClipboardStatus
    text: str | None


def read_text_detailed() -> ReadResult:
    """读取当前剪贴板文本并区分失败原因。

    打开剪贴板被其它进程占用时会短暂重试，重试耗尽仍失败才报告占用状态。

    Returns:
        ReadResult：成功时 status 为 OK 且 text 为剪贴板文本；
        剪贴板为空、非文本、被其它进程占用或系统错误时 text 为 None 并给出对应状态。
    """
    if sys.platform != "win32":
        raise OSError("剪贴板读取仅支持 Windows")

    user32, kernel32 = _libraries()
    opened = False
    for attempt in range(_OPEN_ATTEMPTS):
        if user32.OpenClipboard(None):
            opened = True
            break
        if attempt + 1 < _OPEN_ATTEMPTS:
            time.sleep(_OPEN_RETRY_INTERVAL)
    if not opened:
        return ReadResult(ClipboardStatus.LOCKED, None)
    try:
        if not user32.IsClipboardFormatAvailable(CF_UNICODETEXT):
            if user32.CountClipboardFormats() == 0:
                return ReadResult(ClipboardStatus.EMPTY, None)
            return ReadResult(ClipboardStatus.NOT_TEXT, None)
        handle = user32.GetClipboardData(CF_UNICODETEXT)
        if not handle:
            return ReadResult(ClipboardStatus.EMPTY, None)
        pointer = kernel32.GlobalLock(handle)
        if not pointer:
            return ReadResult(ClipboardStatus.OS_ERROR, None)
        try:
            text = ctypes.wstring_at(pointer).rstrip("\x00")
        finally:
            kernel32.GlobalUnlock(handle)
        if not text:
            return ReadResult(ClipboardStatus.EMPTY, None)
        return ReadResult(ClipboardStatus.OK, text)
    finally:
        user32.CloseClipboard()


def read_text() -> str | None:
    """读取当前剪贴板文本，空内容或非文本内容返回 None。

    Returns:
        剪贴板中的 Unicode 文本；剪贴板为空、非文本或不可访问时返回 None。
    """
    return read_text_detailed().text


def _libraries() -> tuple[Any, Any]:
    """返回缓存的 user32 与 kernel32 库，首次调用时加载并配置函数原型。"""
    global _USER32, _KERNEL32
    if _USER32 is None:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.OpenClipboard.argtypes = [wintypes.HWND]
        user32.OpenClipboard.restype = wintypes.BOOL
        user32.CloseClipboard.argtypes = []
        user32.CloseClipboard.restype = wintypes.BOOL
        user32.IsClipboardFormatAvailable.argtypes = [wintypes.UINT]
        user32.IsClipboardFormatAvailable.restype = wintypes.BOOL
        user32.CountClipboardFormats.argtypes = []
        user32.CountClipboardFormats.restype = wintypes.INT
        user32.GetClipboardData.argtypes = [wintypes.UINT]
        user32.GetClipboardData.restype = ctypes.c_void_p
        _USER32 = user32
    if _KERNEL32 is None:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
        kernel32.GlobalLock.restype = ctypes.c_void_p
        kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
        kernel32.GlobalUnlock.restype = wintypes.BOOL
        _KERNEL32 = kernel32
    return _USER32, _KERNEL32
