"""AutoTypePaste 的单文件实现：常量、配置、剪贴板、提示音、输入法、注入、历史、热键监听与入口。"""

from __future__ import annotations

import ctypes
import json
import sys
import threading
import time
from collections import deque
from ctypes import wintypes
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path
from typing import Any

__all__ = [
    "main",
    "run",
    "AppConfig",
    "ConfigError",
    "load_config",
    "default_config_path",
    "ClipboardStatus",
    "ReadResult",
    "read_text_detailed",
    "read_text",
    "beep_ok",
    "beep_warn",
    "ImeState",
    "suspend_ime",
    "restore_ime",
    "type_text",
    "HistoryBuffer",
]


CONFIG_FILENAME: str = "config.json"

DEFAULT_HOTKEY: str = "<f9>"
DEFAULT_SLOT2_HOTKEY: str = "<f10>"
DEFAULT_EXIT_HOTKEY: str = "<ctrl>+<alt>+q"
DEFAULT_CHARACTER_INTERVAL: float = 0.01
DEFAULT_START_DELAY: float = 0.25
DEFAULT_HISTORY_SIZE: int = 5
DEFAULT_FEEDBACK: bool = True
DEFAULT_DISABLE_IME: bool = True
DEFAULT_UNICODE_INPUT: bool = True

CF_UNICODETEXT: int = 13
_INPUT_KEYBOARD: int = 1
_KEYEVENTF_UNICODE: int = 0x0004
_KEYEVENTF_KEYUP: int = 0x0002
_MB_OK: int = 0x00000000
_MB_ICONHAND: int = 0x00000010
_OPEN_ATTEMPTS: int = 3
_OPEN_RETRY_INTERVAL: float = 0.02
_BATCH_UNIT_LIMIT: int = 128
_TYPE_PRE_DELAY: float = 0.05
_RELEASE_POLL_INTERVAL: float = 0.01
_DISPLAY_ENTRY_WIDTH: int = 40

ANSI_INFO: str = "\033[36m"
ANSI_ERROR: str = "\033[31m"
ANSI_RESET: str = "\033[0m"
ANSI_CURSOR_UP: str = "\033[{}A"
ANSI_ERASE_DOWN: str = "\033[J"


class ConfigError(ValueError):
    """表示配置文件存在但内容非法。"""


class ClipboardStatus(Enum):
    """剪贴板读取结果的分类状态。"""

    OK = auto()
    EMPTY = auto()
    NOT_TEXT = auto()
    LOCKED = auto()
    OS_ERROR = auto()


@dataclass(frozen=True, slots=True)
class AppConfig:
    """AutoTypePaste 的热键与输入时序配置。"""

    hotkey: str
    exit_hotkey: str
    character_interval: float
    start_delay: float
    slot2_hotkey: str = DEFAULT_SLOT2_HOTKEY
    history_size: int = DEFAULT_HISTORY_SIZE
    feedback: bool = DEFAULT_FEEDBACK
    disable_ime: bool = DEFAULT_DISABLE_IME
    unicode_input: bool = DEFAULT_UNICODE_INPUT


@dataclass(frozen=True, slots=True)
class ReadResult:
    """剪贴板读取结果，状态为 OK 时文本非空。"""

    status: ClipboardStatus
    text: str | None


@dataclass(frozen=True, slots=True)
class ImeState:
    """记录挂起的输入法窗口、句柄与原开关状态，用于恢复。"""

    hwnd: int
    himc: int
    was_open: bool


class _GuiThreadInfo(ctypes.Structure):
    """Windows GUI 线程焦点信息结构，供 GetGUIThreadInfo 使用。"""

    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("hwndActive", wintypes.HWND),
        ("hwndFocus", wintypes.HWND),
        ("hwndImeIme", wintypes.HWND),
        ("hwndCaret", wintypes.HWND),
        ("rcCaret", wintypes.RECT),
    ]


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


_READ_HINTS: dict[ClipboardStatus, str] = {
    ClipboardStatus.EMPTY: "剪贴板为空，请先复制文字。",
    ClipboardStatus.NOT_TEXT: "剪贴板中没有文本，可能是图片或文件。",
    ClipboardStatus.LOCKED: "剪贴板被其它程序占用，请稍后重试。",
    ClipboardStatus.OS_ERROR: "读取剪贴板失败。",
}


def _message(text: str, color: str = ANSI_INFO) -> None:
    """使用 ANSI 颜色在控制台输出状态信息。"""
    print(f"{color}{text}{ANSI_RESET}", flush=True)


def default_config_path() -> Path:
    """返回当前运行方式对应的外部配置文件路径。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / CONFIG_FILENAME
    return Path.cwd() / CONFIG_FILENAME


def load_config(path: Path | None = None) -> AppConfig:
    """从 JSON 文件加载并校验运行配置；文件缺失时使用内置默认值。

    Args:
        path: 要读取的配置文件路径；省略时使用 ``default_config_path()``。

    Returns:
        校验通过的运行配置。

    Raises:
        ConfigError: 配置文件存在但内容非法时抛出；文件不存在时返回默认配置而不抛错。
    """
    config_path = path or default_config_path()
    if not config_path.exists():
        return _default_config()
    try:
        raw: Any = json.loads(config_path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as error:
        raise ConfigError(f"配置文件不是有效 JSON：第 {error.lineno} 行第 {error.colno} 列") from error
    if not isinstance(raw, dict):
        raise ConfigError("配置文件根节点必须是 JSON 对象")
    return AppConfig(
        hotkey=_required_string(raw, "hotkey"),
        exit_hotkey=_required_string(raw, "exit_hotkey"),
        character_interval=_required_positive_number(raw, "character_interval"),
        start_delay=_required_nonnegative_number(raw, "start_delay"),
        slot2_hotkey=_optional_string(raw, "slot2_hotkey", DEFAULT_SLOT2_HOTKEY),
        history_size=_optional_int(raw, "history_size", DEFAULT_HISTORY_SIZE, minimum=1),
        feedback=_optional_bool(raw, "feedback", DEFAULT_FEEDBACK),
        disable_ime=_optional_bool(raw, "disable_ime", DEFAULT_DISABLE_IME),
        unicode_input=_optional_bool(raw, "unicode_input", DEFAULT_UNICODE_INPUT),
    )


def _default_config() -> AppConfig:
    """返回全部内置默认值的配置对象。"""
    return AppConfig(
        hotkey=DEFAULT_HOTKEY,
        exit_hotkey=DEFAULT_EXIT_HOTKEY,
        character_interval=DEFAULT_CHARACTER_INTERVAL,
        start_delay=DEFAULT_START_DELAY,
    )


def _required_string(values: dict[str, Any], name: str) -> str:
    """读取必填非空字符串字段。"""
    value = values.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"配置项 {name} 必须是非空字符串")
    return value


def _required_positive_number(values: dict[str, Any], name: str) -> float:
    """读取必填且大于 0 的数值字段。"""
    value = values.get(name)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"配置项 {name} 必须是数字")
    number = float(value)
    if number <= 0:
        raise ConfigError(f"配置项 {name} 必须大于 0")
    return number


def _required_nonnegative_number(values: dict[str, Any], name: str) -> float:
    """读取必填且大于等于 0 的数值字段。"""
    value = values.get(name)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"配置项 {name} 必须是数字")
    number = float(value)
    if number < 0:
        raise ConfigError(f"配置项 {name} 必须大于或等于 0")
    return number


def _optional_string(values: dict[str, Any], name: str, default: str) -> str:
    """读取可选非空字符串字段，缺失或为空时返回默认值。"""
    if name not in values:
        return default
    value = values[name]
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"配置项 {name} 必须是非空字符串")
    return value


def _optional_int(values: dict[str, Any], name: str, default: int, *, minimum: int) -> int:
    """读取可选整数字段，缺失时返回默认值。"""
    if name not in values:
        return default
    value = values[name]
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"配置项 {name} 必须是整数")
    if value < minimum:
        raise ConfigError(f"配置项 {name} 必须大于或等于 {minimum}")
    return value


def _optional_bool(values: dict[str, Any], name: str, default: bool) -> bool:
    """读取可选布尔字段，缺失时返回默认值。"""
    if name not in values:
        return default
    value = values[name]
    if not isinstance(value, bool):
        raise ConfigError(f"配置项 {name} 必须是布尔值")
    return value


_user32_clip: Any = None
_kernel32: Any = None


def _clip_libraries() -> tuple[Any, Any]:
    """返回缓存的 user32 与 kernel32 库，首次调用时配置函数原型。"""
    global _user32_clip, _kernel32
    if _user32_clip is None:
        lib = ctypes.WinDLL("user32", use_last_error=True)
        lib.OpenClipboard.argtypes = [wintypes.HWND]
        lib.OpenClipboard.restype = wintypes.BOOL
        lib.CloseClipboard.argtypes = []
        lib.CloseClipboard.restype = wintypes.BOOL
        lib.IsClipboardFormatAvailable.argtypes = [wintypes.UINT]
        lib.IsClipboardFormatAvailable.restype = wintypes.BOOL
        lib.CountClipboardFormats.argtypes = []
        lib.CountClipboardFormats.restype = wintypes.INT
        lib.GetClipboardData.argtypes = [wintypes.UINT]
        lib.GetClipboardData.restype = ctypes.c_void_p
        _user32_clip = lib
    if _kernel32 is None:
        lib = ctypes.WinDLL("kernel32", use_last_error=True)
        lib.GlobalLock.argtypes = [ctypes.c_void_p]
        lib.GlobalLock.restype = ctypes.c_void_p
        lib.GlobalUnlock.argtypes = [ctypes.c_void_p]
        lib.GlobalUnlock.restype = wintypes.BOOL
        _kernel32 = lib
    return _user32_clip, _kernel32


def read_text_detailed() -> ReadResult:
    """读取剪贴板文本并区分失败原因；被占用时会短暂重试。

    Returns:
        ReadResult：成功时状态为 OK 且文本非空；剪贴板为空、非文本、被其它进程占用或系统错误时返回对应状态与 None 文本。
    """
    if sys.platform != "win32":
        raise OSError("剪贴板读取仅支持 Windows")

    user32, kernel32 = _clip_libraries()
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
    """读取剪贴板文本，空内容或非文本内容返回 None。"""
    return read_text_detailed().text


_user32_beep: Any = None


def _beep(kind: int) -> None:
    """播放指定类型的系统提示音，非 Windows 或调用失败时静默忽略。"""
    global _user32_beep
    if sys.platform != "win32":
        return
    try:
        if _user32_beep is None:
            lib = ctypes.WinDLL("user32", use_last_error=True)
            lib.MessageBeep.argtypes = [ctypes.c_uint]
            lib.MessageBeep.restype = ctypes.c_int
            _user32_beep = lib
        _user32_beep.MessageBeep(kind)
    except OSError:
        return


def beep_ok() -> None:
    """播放成功提示音，表示即将键入文本。"""
    _beep(_MB_OK)


def beep_warn() -> None:
    """播放警告提示音，表示本次触发未能键入文本。"""
    _beep(_MB_ICONHAND)


_user32_ime: Any = None
_imm32: Any = None


def _ime_libraries() -> tuple[Any, Any]:
    """返回缓存的 user32 与 imm32 库，首次调用时配置函数原型。"""
    global _user32_ime, _imm32
    if _user32_ime is None:
        lib = ctypes.WinDLL("user32", use_last_error=True)
        lib.GetGUIThreadInfo.argtypes = [wintypes.DWORD, ctypes.POINTER(_GuiThreadInfo)]
        lib.GetGUIThreadInfo.restype = wintypes.BOOL
        lib.GetForegroundWindow.argtypes = []
        lib.GetForegroundWindow.restype = wintypes.HWND
        _user32_ime = lib
    if _imm32 is None:
        lib = ctypes.WinDLL("imm32", use_last_error=True)
        lib.ImmGetContext.argtypes = [wintypes.HWND]
        lib.ImmGetContext.restype = ctypes.c_void_p
        lib.ImmGetOpenStatus.argtypes = [ctypes.c_void_p]
        lib.ImmGetOpenStatus.restype = wintypes.BOOL
        lib.ImmSetOpenStatus.argtypes = [ctypes.c_void_p, wintypes.BOOL]
        lib.ImmSetOpenStatus.restype = wintypes.BOOL
        lib.ImmReleaseContext.argtypes = [wintypes.HWND, ctypes.c_void_p]
        lib.ImmReleaseContext.restype = wintypes.BOOL
        _imm32 = lib
    return _user32_ime, _imm32


def suspend_ime() -> ImeState | None:
    """关闭焦点窗口的输入法并返回恢复令牌；无上下文或非 Windows 时返回 None。"""
    if sys.platform != "win32":
        return None

    user32, imm32 = _ime_libraries()
    info = _GuiThreadInfo()
    info.cbSize = ctypes.sizeof(_GuiThreadInfo)
    hwnd: int = info.hwndFocus or 0
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

    _user32_ime, imm32 = _ime_libraries()
    if token.was_open:
        imm32.ImmSetOpenStatus(token.himc, 1)
    imm32.ImmReleaseContext(token.hwnd, token.himc)


_user32_input: Any = None


def _input_user32() -> Any:
    """返回缓存的 user32 库，首次调用时配置 SendInput 原型。"""
    global _user32_input
    if _user32_input is None:
        lib = ctypes.WinDLL("user32", use_last_error=True)
        lib.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(_INPUT), ctypes.c_int]
        lib.SendInput.restype = wintypes.UINT
        _user32_input = lib
    return _user32_input


def _code_units(character: str) -> list[int]:
    """返回字符对应的 UTF-16 码元序列。"""
    code = ord(character)
    if code <= 0xFFFF:
        return [code]
    code -= 0x10000
    return [0xD800 + (code >> 10), 0xDC00 + (code & 0x3FF)]


def _send_units(user32: Any, units: list[int]) -> None:
    """注入一组 UTF-16 码元的按下与释放事件；注入数量不足时抛出 OSError。"""
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


def type_text(text: str, interval: float) -> None:
    """以 KEYEVENTF_UNICODE 事件注入文本，不受输入法与键盘布局影响。

    Args:
        text: 要注入的文本。
        interval: 字符之间的间隔秒数；正数时逐字符注入并在字符间等待，零或负数时按块批量注入以减少系统调用次数。

    Raises:
        OSError: 系统未接受全部注入事件时抛出。
    """
    if sys.platform != "win32":
        return

    user32 = _input_user32()
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


class HistoryBuffer:
    """固定容量的剪贴板文本历史缓冲，提供最新到最旧的访问。"""

    def __init__(self, size: int) -> None:
        """创建容量为 size 的缓冲；容量至少 1。"""
        if size < 1:
            raise ValueError("size 必须 >= 1")
        self._items: deque[str] = deque(maxlen=size)
        self._lock = threading.Lock()

    def push(self, text: str) -> None:
        """追加文本；与最新条目相同时忽略。"""
        with self._lock:
            if not self._items or self._items[-1] != text:
                self._items.append(text)

    def __len__(self) -> int:
        """返回当前条目数。"""
        with self._lock:
            return len(self._items)

    def newest(self) -> list[str]:
        """返回从最新到最旧的条目副本。"""
        with self._lock:
            return list(reversed(self._items))


def _conflicting_hotkey_pair(key_sets: list[frozenset[Any]]) -> tuple[int, int] | None:
    """返回第一对键集合完全相同的热键下标对；全部互不相同时返回 None。"""
    for first in range(len(key_sets) - 1):
        for second in range(first + 1, len(key_sets)):
            if key_sets[first] == key_sets[second]:
                return (first, second)
    return None


def _truncate(text: str, width: int = _DISPLAY_ENTRY_WIDTH) -> str:
    """返回适合终端显示的截断文本。"""
    if len(text) <= width:
        return text
    return text[: width - 1] + "…"


def _render_history(
    entries: list[str], selected_index: int, last_height: int
) -> int:
    """使用 ANSI 控制符原地重绘历史选择列表；返回本次占用的行数。"""
    if last_height > 0:
        sys.stdout.write(ANSI_CURSOR_UP.format(last_height))
    sys.stdout.write(ANSI_ERASE_DOWN)
    sys.stdout.write("历史记录（↑↓ 移动，F10 确认，Esc 取消）：\n")
    for index, entry in enumerate(entries):
        marker = "> " if index == selected_index else "  "
        sys.stdout.write(f"{marker}{index + 1}. {_truncate(entry)}\n")
    sys.stdout.flush()
    return 1 + len(entries)


def _erase_history(height: int) -> None:
    """原地清除选择列表所占的 N 行。"""
    if height <= 0:
        return
    sys.stdout.write(ANSI_CURSOR_UP.format(height))
    sys.stdout.write(ANSI_ERASE_DOWN)
    sys.stdout.flush()


def run() -> int:
    """启动常驻监听，返回约定的进程退出码。"""
    try:
        from pynput import keyboard
    except ImportError:
        _message("缺少 pynput 依赖，请先安装 requirements.txt 中的依赖。", ANSI_ERROR)
        return 3

    try:
        app_config = load_config()
    except ConfigError as error:
        _message(f"配置文件无效：{error}。请检查 config.json。", ANSI_ERROR)
        return 2

    try:
        F9_keys = frozenset(keyboard.HotKey.parse(app_config.hotkey))
        F10_keys = frozenset(keyboard.HotKey.parse(app_config.slot2_hotkey))
        exit_keys = frozenset(keyboard.HotKey.parse(app_config.exit_hotkey))
        up_keys = frozenset(keyboard.HotKey.parse("<up>"))
        down_keys = frozenset(keyboard.HotKey.parse("<down>"))
        esc_keys = frozenset(keyboard.HotKey.parse("<esc>"))
    except (KeyError, ValueError) as error:
        _message(f"热键配置无效：{error}。请检查 config.json 中的热键格式。", ANSI_ERROR)
        return 2

    conflict = _conflicting_hotkey_pair([F9_keys, F10_keys, exit_keys])
    if conflict is not None:
        first, second = conflict
        labels = ("第一热键", "第二热键", "退出热键")
        _message(
            f"热键配置无效：{labels[first]}与{labels[second]}重复。请检查 config.json。",
            ANSI_ERROR,
        )
        return 2

    slot_hotkeys: list[tuple[frozenset[Any], int]] = [(F9_keys, 1), (F10_keys, 2)]
    all_trigger_keys: frozenset[Any] = F9_keys | F10_keys

    history = HistoryBuffer(app_config.history_size)
    pressed: set[object] = set()
    state_lock = threading.Lock()
    typing_lock = threading.Lock()
    stopping = threading.Event()

    selecting = False
    selection_index = 0
    selection_height = 0
    trigger_armed = True

    def wait_for_release() -> None:
        """等待触发热键完全释放。"""
        while True:
            with state_lock:
                held = bool(pressed.intersection(all_trigger_keys))
            if not held:
                return
            time.sleep(_RELEASE_POLL_INTERVAL)

    def type_with_ime(text: str) -> None:
        """在已持有 typing_lock 后挂起输入法并键入文本。"""
        token = suspend_ime() if app_config.disable_ime else None
        try:
            time.sleep(_TYPE_PRE_DELAY)
            if app_config.unicode_input:
                type_text(text, app_config.character_interval)
            else:
                controller = keyboard.Controller()
                for character in text:
                    controller.type(character)
                    time.sleep(app_config.character_interval)
        finally:
            restore_ime(token)

    def type_clipboard() -> None:
        """第一热键：读取剪贴板并键入。"""
        if not typing_lock.acquire(blocking=False):
            return
        try:
            wait_for_release()
            time.sleep(app_config.start_delay)
            try:
                result = read_text_detailed()
                text = result.text if result.status is ClipboardStatus.OK else None
                if not text:
                    if app_config.feedback:
                        beep_warn()
                    hint = _READ_HINTS.get(result.status, "读取剪贴板失败。")
                    _message(f"未键入：{hint}", ANSI_ERROR)
                    return
                history.push(text)
                if app_config.feedback:
                    beep_ok()
                _message(f"开始键入 {len(text)} 个字符。")
            except OSError as error:
                if app_config.feedback:
                    beep_warn()
                _message(f"读取剪贴板失败：{error}。请确认当前系统为 Windows。", ANSI_ERROR)
                return
            try:
                type_with_ime(text)
            except OSError as error:
                if app_config.feedback:
                    beep_warn()
                _message(f"键入失败：{error}。", ANSI_ERROR)
                return
            _message("键入完成。")
        finally:
            typing_lock.release()

    def type_selected(text: str) -> None:
        """从历史选择触发的键入流程。"""
        if not typing_lock.acquire(blocking=False):
            return
        try:
            wait_for_release()
            time.sleep(app_config.start_delay)
            if app_config.feedback:
                beep_ok()
            _message(f"开始键入 {len(text)} 个字符。")
            try:
                type_with_ime(text)
            except OSError as error:
                if app_config.feedback:
                    beep_warn()
                _message(f"键入失败：{error}。", ANSI_ERROR)
                return
            _message("键入完成。")
        finally:
            typing_lock.release()

    def open_selection() -> None:
        """第二热键：打开历史选择模式。"""
        nonlocal selecting, selection_index, selection_height
        wait_for_release()
        with state_lock:
            entries = history.newest()
            if not entries:
                empty = True
            else:
                empty = False
                selecting = True
                selection_index = 0
                cur_entries = entries
        if empty:
            if app_config.feedback:
                beep_warn()
            _message("未键入：暂无历史内容，请先用第一热键键入一次。", ANSI_ERROR)
            return
        selection_height = _render_history(cur_entries, 0, 0)

    def handle_selection(kind: str) -> None:
        """选择模式下的按键处理：confirm / up / down / cancel。"""
        nonlocal selecting, selection_index, selection_height
        text_to_type: str | None = None
        erase_height = 0
        with state_lock:
            if not selecting:
                return
            entries = history.newest()
            if kind == "cancel":
                selecting = False
                erase_height = selection_height
                selection_height = 0
            elif kind == "confirm":
                text_to_type = (
                    entries[selection_index]
                    if 0 <= selection_index < len(entries)
                    else None
                )
                selecting = False
                erase_height = selection_height
                selection_height = 0
            elif kind == "up":
                if selection_index < len(entries) - 1:
                    selection_index += 1
                selection_height = _render_history(entries, selection_index, selection_height)
                return
            elif kind == "down":
                if selection_index > 0:
                    selection_index -= 1
                selection_height = _render_history(entries, selection_index, selection_height)
                return
        _erase_history(erase_height)
        if kind != "confirm":
            return
        if text_to_type is None:
            if app_config.feedback:
                beep_warn()
            _message("未键入：所选历史不存在。", ANSI_ERROR)
            return
        type_selected(text_to_type)

    def on_press(key: object) -> None:
        """按下事件：派发退出、键入或选择动作。"""
        nonlocal trigger_armed
        canonical = listener.canonical(key)
        with state_lock:
            before = set(pressed)
            pressed.add(canonical)
            is_exit = exit_keys.issubset(pressed)
            action: tuple[Any, ...] | None = None
            if is_exit:
                action = ("exit",)
            elif selecting:
                if F10_keys.issubset(pressed) and F10_keys.isdisjoint(before):
                    action = ("confirm",)
                elif up_keys.issubset(pressed) and up_keys.isdisjoint(before):
                    action = ("up",)
                elif down_keys.issubset(pressed) and down_keys.isdisjoint(before):
                    action = ("down",)
                elif esc_keys.issubset(pressed) and esc_keys.isdisjoint(before):
                    action = ("cancel",)
            elif trigger_armed:
                for keys, slot in slot_hotkeys:
                    if keys.issubset(pressed):
                        trigger_armed = False
                        action = ("type", slot)
                        break
        if action is None:
            return
        kind = action[0]
        if kind == "exit":
            stopping.set()
            listener.stop()
        elif kind == "type":
            slot = int(action[1])
            if slot == 1:
                threading.Thread(target=type_clipboard, daemon=True).start()
            else:
                threading.Thread(target=open_selection, daemon=True).start()
        else:
            handle_selection(kind)

    def on_release(key: object) -> None:
        """释放事件：记录释放并在所有触发键释放后重新武装。"""
        nonlocal trigger_armed
        canonical = listener.canonical(key)
        with state_lock:
            pressed.discard(canonical)
            if not pressed.intersection(all_trigger_keys):
                trigger_armed = True

    listener: Any
    try:
        listener = keyboard.Listener(on_press=on_press, on_release=on_release)
        listener.start()
        _message(
            f"AutoTypePaste 已启动，第一热键 {app_config.hotkey}，"
            f"第二热键 {app_config.slot2_hotkey}，退出热键 {app_config.exit_hotkey}。"
        )
        listener.join()
    except (OSError, RuntimeError) as error:
        _message(f"键盘监听启动失败：{error}。请检查权限或关闭占用键盘监听的软件。", ANSI_ERROR)
        return 2
    finally:
        stopping.set()
    return 0


def main() -> None:
    """启动 AutoTypePaste 并处理控制台中断。"""
    try:
        raise SystemExit(run())
    except KeyboardInterrupt:
        raise SystemExit(0) from None


if __name__ == "__main__":
    main()