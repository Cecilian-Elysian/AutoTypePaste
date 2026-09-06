"""监听全局热键并将剪贴板文本模拟键入当前窗口。"""

from __future__ import annotations

import threading
import time
from typing import Any

from . import config
from .clipboard import read_text

ANSI_INFO: str = "\033[36m"
ANSI_ERROR: str = "\033[31m"
ANSI_RESET: str = "\033[0m"


def _message(text: str, color: str = ANSI_INFO) -> None:
    """使用标准 ANSI 转义序列输出状态信息。"""
    print(f"{color}{text}{ANSI_RESET}", flush=True)


def run() -> int:
    """启动常驻监听，返回约定的进程退出码。"""
    try:
        from pynput import keyboard
    except ImportError:
        _message("缺少 pynput 依赖，请先安装 requirements.txt 中的依赖。", ANSI_ERROR)
        return 3

    try:
        app_config = config.load_config()
        trigger_keys = frozenset(keyboard.HotKey.parse(app_config.hotkey))
        exit_keys = frozenset(keyboard.HotKey.parse(app_config.exit_hotkey))
    except config.ConfigError as error:
        _message(f"配置文件无效：{error}。请检查 config.json。", ANSI_ERROR)
        return 2
    except (KeyError, ValueError) as error:
        _message(f"热键配置无效：{error}。请检查 config.json 中的热键格式。", ANSI_ERROR)
        return 2

    pressed: set[object] = set()
    state_lock = threading.Lock()
    typing_lock = threading.Lock()
    trigger_armed = True
    stopping = threading.Event()

    def type_clipboard() -> None:
        """等待修饰键释放后，将剪贴板内容键入当前焦点窗口。"""
        if not typing_lock.acquire(blocking=False):
            return
        try:
            while True:
                with state_lock:
                    hotkey_held = bool(pressed.intersection(trigger_keys))
                if not hotkey_held:
                    break
                time.sleep(0.01)
            time.sleep(app_config.start_delay)
            text = read_text()
            if not text:
                _message("剪贴板为空或非文本，请先复制文字。", ANSI_ERROR)
                return
            controller = keyboard.Controller()
            for character in text:
                controller.type(character)
                time.sleep(app_config.character_interval)
        except OSError as error:
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
            is_trigger = trigger_armed and trigger_keys.issubset(pressed)
            if is_trigger:
                trigger_armed = False
        if is_exit:
            stopping.set()
            listener.stop()
        elif is_trigger:
            threading.Thread(target=type_clipboard, daemon=True).start()

    def on_release(key: object) -> None:
        """记录释放键，并在触发组合完全释放后重新武装。"""
        nonlocal trigger_armed
        canonical = listener.canonical(key)
        with state_lock:
            pressed.discard(canonical)
            if not pressed.intersection(trigger_keys):
                trigger_armed = True

    listener: Any
    try:
        listener = keyboard.Listener(on_press=on_press, on_release=on_release)
        listener.start()
        _message(f"AutoTypePaste 已启动，输入热键 {app_config.hotkey}，退出热键 {app_config.exit_hotkey}。")
        listener.join()
    except (OSError, RuntimeError) as error:
        _message(f"键盘监听启动失败：{error}。请检查权限或关闭占用键盘监听的软件。", ANSI_ERROR)
        return 2
    finally:
        stopping.set()
    return 0
