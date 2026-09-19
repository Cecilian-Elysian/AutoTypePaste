"""使用 Windows 系统音效提供触发反馈。"""

from __future__ import annotations

import ctypes
import sys

_MB_OK: int = 0x00000000
_MB_ICONHAND: int = 0x00000010


def _beep(kind: int) -> None:
    """播放指定类型的系统提示音，非 Windows 或失败时静默忽略。"""
    if sys.platform != "win32":
        return
    try:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.MessageBeep.argtypes = [ctypes.c_uint]
        user32.MessageBeep.restype = ctypes.c_int
        user32.MessageBeep(kind)
    except OSError:
        return


def beep_ok() -> None:
    """播放成功提示音，表示剪贴板文本即将键入。"""
    _beep(_MB_OK)


def beep_warn() -> None:
    """播放警告提示音，表示本次触发未能键入文本。"""
    _beep(_MB_ICONHAND)
