"""使用 Windows API 读取 Unicode 剪贴板文本。"""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

CF_UNICODETEXT: int = 13


def read_text() -> str | None:
    """读取当前剪贴板文本，空内容或非文本内容返回 None。

    Returns:
        剪贴板中的 Unicode 文本；剪贴板为空、非文本或不可访问时返回 None。
    """
    if sys.platform != "win32":
        raise OSError("剪贴板读取仅支持 Windows")

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.OpenClipboard.restype = wintypes.BOOL
    user32.CloseClipboard.argtypes = []
    user32.CloseClipboard.restype = wintypes.BOOL
    user32.IsClipboardFormatAvailable.argtypes = [wintypes.UINT]
    user32.IsClipboardFormatAvailable.restype = wintypes.BOOL
    user32.GetClipboardData.argtypes = [wintypes.UINT]
    user32.GetClipboardData.restype = ctypes.c_void_p
    kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
    kernel32.GlobalUnlock.restype = wintypes.BOOL

    if not user32.OpenClipboard(None):
        return None
    try:
        if not user32.IsClipboardFormatAvailable(CF_UNICODETEXT):
            return None
        handle = user32.GetClipboardData(CF_UNICODETEXT)
        if not handle:
            return None
        pointer = kernel32.GlobalLock(handle)
        if not pointer:
            return None
        try:
            return ctypes.wstring_at(pointer).rstrip("\x00") or None
        finally:
            kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()
