"""监听全局热键并将剪贴板文本模拟键入当前窗口。"""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Any

from . import config
from . import unicode_input
from .clipboard import ClipboardStatus, read_text_detailed
from .feedback import beep_ok, beep_warn
from .ime import restore_ime, suspend_ime

ANSI_INFO: str = "\033[36m"
ANSI_ERROR: str = "\033[31m"
ANSI_RESET: str = "\033[0m"

_READ_HINTS: dict[ClipboardStatus, str] = {
    ClipboardStatus.EMPTY: "剪贴板为空，请先复制文字。",
    ClipboardStatus.NOT_TEXT: "剪贴板中没有文本，可能是图片或文件。",
    ClipboardStatus.LOCKED: "剪贴板被其它程序占用，请稍后重试。",
    ClipboardStatus.OS_ERROR: "读取剪贴板失败。",
}


def _message(text: str, color: str = ANSI_INFO) -> None:
    """使用标准 ANSI 转义序列输出状态信息。"""
    print(f"{color}{text}{ANSI_RESET}", flush=True)


class HistoryBuffer:
    """固定容量的剪贴板文本历史缓冲，供多槽位键入使用。"""

    def __init__(self, size: int) -> None:
        """创建指定容量的缓冲，容量至少为 1。"""
        self._items: deque[str] = deque(maxlen=size)
        self._lock = threading.Lock()

    def push(self, text: str) -> None:
        """追加文本；与最新条目相同时忽略。"""
        with self._lock:
            if not self._items or self._items[-1] != text:
                self._items.append(text)

    def snapshot(self, slot: int) -> str | None:
        """返回第 slot 新的条目；slot 从 1 开始，越界或缓冲为空时返回 None。"""
        with self._lock:
            if 1 <= slot <= len(self._items):
                return self._items[-slot]
            return None


def run() -> int:
    """启动常驻监听，返回约定的进程退出码。"""
    try:
        from pynput import keyboard
    except ImportError:
        _message("缺少 pynput 依赖，请先安装 requirements.txt 中的依赖。", ANSI_ERROR)
        return 3

    try:
        app_config = config.load_config()
        slot_hotkeys: list[tuple[frozenset[Any], int]] = [
            (frozenset(keyboard.HotKey.parse(app_config.hotkey)), 1),
            (frozenset(keyboard.HotKey.parse(app_config.slot2_hotkey)), 2),
        ]
        exit_keys = frozenset(keyboard.HotKey.parse(app_config.exit_hotkey))
    except config.ConfigError as error:
        _message(f"配置文件无效：{error}。请检查 config.json。", ANSI_ERROR)
        return 2
    except (KeyError, ValueError) as error:
        _message(f"热键配置无效：{error}。请检查 config.json 中的热键格式。", ANSI_ERROR)
        return 2

    all_trigger_keys: frozenset[Any] = frozenset()
    for keys, _slot in slot_hotkeys:
        all_trigger_keys = all_trigger_keys | keys

    history = HistoryBuffer(app_config.history_size)
    pressed: set[object] = set()
    state_lock = threading.Lock()
    typing_lock = threading.Lock()
    trigger_armed = True
    stopping = threading.Event()

    def type_slot(slot: int) -> None:
        """等待修饰键释放后，将剪贴板或历史缓冲指定槽位的文本键入焦点窗口。"""
        if not typing_lock.acquire(blocking=False):
            return
        try:
            while True:
                with state_lock:
                    hotkey_held = bool(pressed.intersection(all_trigger_keys))
                if not hotkey_held:
                    break
                time.sleep(0.01)
            time.sleep(app_config.start_delay)

            result = read_text_detailed()
            current: str | None = result.text if result.status is ClipboardStatus.OK else None
            if current:
                history.push(current)
            elif slot == 1:
                if app_config.feedback:
                    beep_warn()
                hint = _READ_HINTS.get(result.status, "读取剪贴板失败。")
                _message(f"未键入：{hint}", ANSI_ERROR)
                return
            text = current if slot == 1 else history.snapshot(2 if current else 1)
            if text is None:
                if app_config.feedback:
                    beep_warn()
                _message("未键入：暂无上一次的剪贴板内容，请先用第一热键键入一次。", ANSI_ERROR)
                return

            if app_config.feedback:
                beep_ok()
            _message(f"开始键入第 {slot} 槽位的 {len(text)} 个字符。")
            ime_token = suspend_ime() if app_config.disable_ime else None
            try:
                time.sleep(0.05)
                if app_config.unicode_input:
                    unicode_input.type_text(text, app_config.character_interval)
                else:
                    controller = keyboard.Controller()
                    for character in text:
                        controller.type(character)
                        time.sleep(app_config.character_interval)
            finally:
                restore_ime(ime_token)
            _message("键入完成。")
        except OSError as error:
            if app_config.feedback:
                beep_warn()
            _message(f"读取剪贴板失败：{error}。请确认当前系统为 Windows。", ANSI_ERROR)
        finally:
            typing_lock.release()

    def on_press(key: object) -> None:
        """记录按下键，并检测退出或输入组合。"""
        nonlocal trigger_armed
        canonical = listener.canonical(key)
        with state_lock:
            pressed.add(canonical)
            is_exit = exit_keys.issubset(pressed)
            slot = 0
            if trigger_armed:
                for keys, value in slot_hotkeys:
                    if keys.issubset(pressed):
                        slot = value
                        trigger_armed = False
                        break
        if is_exit:
            stopping.set()
            listener.stop()
        elif slot:
            threading.Thread(target=type_slot, args=(slot,), daemon=True).start()

    def on_release(key: object) -> None:
        """记录释放键，并在触发组合完全释放后重新武装。"""
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
