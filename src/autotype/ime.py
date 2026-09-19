"""使用 Windows IMM API 在键入期间临时关闭输入法。"""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ImeState:
    """记录被挂起输入法的窗口、句柄与开关状态，用于恢复。"""

    hwnd: int
    himc: int
    was_open: bool


class _GuiThreadInfo(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("hwndActive", wintypes.HWND),
        ("hwndFocus", wintypes.HWND),
        ("hwndImeIme", wintypes.HWND),
        ("hwndCaret", wintypes.HWND),
        ("rcCaret", wintypes.RECT),
    ]


def suspend_ime() -> ImeState | None:
    """关闭当前焦点窗口的输入法，返回恢复所需的令牌；无输入法或非 Windows 时返回 None。"""
    if sys.platform != "win32":
        return None

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    imm32 = ctypes.WinDLL("imm32", use_last_error=True)
    user32.GetGUIThreadInfo.argtypes = [wintypes.DWORD, ctypes.POINTER(_GuiThreadInfo)]
    user32.GetGUIThreadInfo.restype = wintypes.BOOL
    user32.GetForegroundWindow.argtypes = []
    user32.GetForegroundWindow.restype = wintypes.HWND
    imm32.ImmGetContext.argtypes = [wintypes.HWND]
    imm32.ImmGetContext.restype = ctypes.c_void_p
    imm32.ImmGetOpenStatus.argtypes = [ctypes.c_void_p]
    imm32.ImmGetOpenStatus.restype = wintypes.BOOL
    imm32.ImmSetOpenStatus.argtypes = [ctypes.c_void_p, wintypes.BOOL]
    imm32.ImmSetOpenStatus.restype = wintypes.BOOL

    info = _GuiThreadInfo()
    info.cbSize = ctypes.sizeof(_GuiThreadInfo)
    hwnd: int | None = info.hwndFocus
    if not hwnd:
        hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return None
    himc = imm32.ImmGetContext(hwnd)
    if not himc:
        return None
    was_open = bool(imm32.ImmGetOpenStatus(himc))
    if was_open:
        imm32.ImmSetOpenStatus(himc, 0)
    return ImeState(int(hwnd), int(himc), was_open)


def restore_ime(token: ImeState | None) -> None:
    """恢复 suspend_ime 挂起的输入法状态，令牌为 None 时忽略。"""
    if token is None or sys.platform != "win32":
        return

    imm32 = ctypes.WinDLL("imm32", use_last_error=True)
    imm32.ImmSetOpenStatus.argtypes = [ctypes.c_void_p, wintypes.BOOL]
    imm32.ImmSetOpenStatus.restype = wintypes.BOOL
    imm32.ImmReleaseContext.argtypes = [wintypes.HWND, ctypes.c_void_p]
    imm32.ImmReleaseContext.restype = wintypes.BOOL
    if token.was_open:
        imm32.ImmSetOpenStatus(token.himc, 1)
    imm32.ImmReleaseContext(token.hwnd, token.himc)
