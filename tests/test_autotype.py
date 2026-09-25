"""AutoTypePaste 的单文件测试集：覆盖配置、剪贴板、输入法、Unicode 注入、历史与热键辅助。"""

from __future__ import annotations

import ctypes
import json
import sys
from pathlib import Path

import pytest

import autotype.__main__ as main_module
from autotype.__main__ import (
    AppConfig,
    ClipboardStatus,
    ConfigError,
    HistoryBuffer,
    ImeState,
    ReadResult,
    _INPUT,
    _code_units,
    _conflicting_hotkey_pair,
    default_config_path,
    load_config,
    read_text,
    read_text_detailed,
    restore_ime,
    suspend_ime,
    type_text,
)


# ---------- 配置 ----------

def test_load_config_uses_defaults_when_file_missing(tmp_path: Path) -> None:
    """配置文件不存在时应直接返回内置默认值而不报错。"""
    missing = tmp_path / "absent.json"

    config = load_config(missing)

    assert config == AppConfig(
        hotkey="<f9>",
        exit_hotkey="<ctrl>+<alt>+q",
        character_interval=0.01,
        start_delay=0.25,
    )


def test_load_config_reads_valid_values(tmp_path: Path) -> None:
    """有效的 JSON 配置应加载为强类型配置对象，缺省字段使用默认。"""
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "hotkey": "<ctrl>+<f9>",
                "exit_hotkey": "<ctrl>+<alt>+q",
                "character_interval": 0.01,
                "start_delay": 0.25,
            }
        ),
        encoding="utf-8",
    )

    assert load_config(config_path) == AppConfig(
        hotkey="<ctrl>+<f9>",
        exit_hotkey="<ctrl>+<alt>+q",
        character_interval=0.01,
        start_delay=0.25,
    )


def test_load_config_reads_all_fields(tmp_path: Path) -> None:
    """包含所有字段的完整配置应全部生效。"""
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "hotkey": "<ctrl>+<f9>",
                "slot2_hotkey": "<ctrl>+<f11>",
                "exit_hotkey": "<ctrl>+<alt>+q",
                "character_interval": 0.02,
                "start_delay": 0.3,
                "history_size": 3,
                "feedback": False,
                "disable_ime": False,
                "unicode_input": False,
            }
        ),
        encoding="utf-8",
    )

    assert load_config(config_path) == AppConfig(
        hotkey="<ctrl>+<f9>",
        exit_hotkey="<ctrl>+<alt>+q",
        character_interval=0.02,
        start_delay=0.3,
        slot2_hotkey="<ctrl>+<f11>",
        history_size=3,
        feedback=False,
        disable_ime=False,
        unicode_input=False,
    )


def test_load_config_tolerates_utf8_bom(tmp_path: Path) -> None:
    """带 BOM 的 UTF-8 配置应正常加载。"""
    config_path = tmp_path / "config.json"
    config_path.write_text(
        '{"hotkey":"<ctrl>+<f9>","exit_hotkey":"<ctrl>+<alt>+q",'
        '"character_interval":0.01,"start_delay":0.25}',
        encoding="utf-8-sig",
    )

    assert load_config(config_path).hotkey == "<ctrl>+<f9>"


def test_load_config_rejects_invalid_interval(tmp_path: Path) -> None:
    """字符间隔为零时应给出明确配置错误。"""
    config_path = tmp_path / "config.json"
    config_path.write_text(
        '{"hotkey":"<ctrl>+<f9>","exit_hotkey":"<ctrl>+<alt>+q",'
        '"character_interval":0,"start_delay":0.25}',
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="character_interval"):
        load_config(config_path)


@pytest.mark.parametrize(
    ("overrides", "match"),
    [
        ({"slot2_hotkey": ""}, "slot2_hotkey"),
        ({"slot2_hotkey": 5}, "slot2_hotkey"),
        ({"history_size": 0}, "history_size"),
        ({"history_size": 1.5}, "history_size"),
        ({"feedback": "yes"}, "feedback"),
        ({"disable_ime": 1}, "disable_ime"),
        ({"unicode_input": 1}, "unicode_input"),
    ],
)
def test_load_config_rejects_invalid_new_fields(
    tmp_path: Path, overrides: dict[str, object], match: str
) -> None:
    """新增字段的非法取值应给出对应配置错误。"""
    values: dict[str, object] = {
        "hotkey": "<ctrl>+<f9>",
        "exit_hotkey": "<ctrl>+<alt>+q",
        "character_interval": 0.01,
        "start_delay": 0.25,
    }
    values.update(overrides)
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(values), encoding="utf-8")

    with pytest.raises(ConfigError, match=match):
        load_config(config_path)


def test_load_config_rejects_non_dict_root(tmp_path: Path) -> None:
    """根节点不是对象时应报错。"""
    config_path = tmp_path / "config.json"
    config_path.write_text("[1,2,3]", encoding="utf-8")

    with pytest.raises(ConfigError, match="JSON 对象"):
        load_config(config_path)


def test_default_config_path_prefers_executable_dir_when_frozen(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """冻结运行时默认配置路径应在可执行文件同目录。"""
    monkeypatch.setattr(main_module.sys, "frozen", True, raising=False)
    monkeypatch.setattr(main_module.sys, "executable", "C:/Tools/AutoTypePaste.exe")

    assert default_config_path() == Path("C:/Tools/config.json")


# ---------- 剪贴板 ----------

class _StubFunction:
    """返回固定值并接受签名属性的伪外部函数。"""

    def __init__(self, result: object = 0) -> None:
        self.result = result
        self.argtypes: list[object] = []
        self.restype: object = None

    def __call__(self, *_args: object) -> object:
        return self.result


class _SequentialFunction:
    """按预设序列依次返回结果的伪外部函数，序列耗尽后重复最后一项。"""

    def __init__(self, results: list[object]) -> None:
        self.results = results
        self.calls: int = 0

    def __call__(self, *_args: object) -> object:
        index = min(self.calls, len(self.results) - 1)
        self.calls += 1
        return self.results[index]


class _StubLibrary:
    """以属性形式暴露伪外部函数的伪动态库。"""

    def __init__(self, functions: dict[str, object]) -> None:
        self._functions = functions

    def __getattr__(self, name: str) -> object:
        return self._functions[name]


def _install_clip_fakes(
    monkeypatch: pytest.MonkeyPatch, user32: object, kernel32: object
) -> None:
    """把剪贴板模块缓存的外部库替换为伪实现，并屏蔽重试等待。"""
    monkeypatch.setattr(main_module, "_user32_clip", user32)
    monkeypatch.setattr(main_module, "_kernel32", kernel32)
    monkeypatch.setattr(main_module.time, "sleep", lambda _seconds: None)


def _user32_clip_lib(
    *,
    open_result: int = 1,
    available_result: int = 1,
    count_result: int = 5,
    data_result: int = 1,
) -> _StubLibrary:
    """构造剪贴板侧伪 API 集合。"""
    return _StubLibrary(
        {
            "OpenClipboard": _StubFunction(open_result),
            "CloseClipboard": _StubFunction(1),
            "IsClipboardFormatAvailable": _StubFunction(available_result),
            "CountClipboardFormats": _StubFunction(count_result),
            "GetClipboardData": _StubFunction(data_result),
        }
    )


def _kernel32_lib(*, lock_result: object = 1) -> _StubLibrary:
    """构造全局内存侧伪 API 集合。"""
    return _StubLibrary(
        {
            "GlobalLock": _StubFunction(lock_result),
            "GlobalUnlock": _StubFunction(1),
        }
    )


@pytest.mark.skipif(sys.platform != "win32", reason="仅支持 Windows")
def test_read_text_detailed_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    """成功读取时应返回 OK 状态与剪贴板文本。"""
    buffer = ctypes.create_unicode_buffer("剪贴板文本")
    _install_clip_fakes(
        monkeypatch,
        _user32_clip_lib(data_result=4321),
        _kernel32_lib(lock_result=ctypes.addressof(buffer)),
    )

    assert read_text_detailed() == ReadResult(ClipboardStatus.OK, "剪贴板文本")


@pytest.mark.skipif(sys.platform != "win32", reason="仅支持 Windows")
def test_read_text_detailed_locked(monkeypatch: pytest.MonkeyPatch) -> None:
    """打开剪贴板失败时应报告占用状态。"""
    _install_clip_fakes(
        monkeypatch, _user32_clip_lib(open_result=0), _kernel32_lib()
    )

    assert read_text_detailed() == ReadResult(ClipboardStatus.LOCKED, None)


@pytest.mark.skipif(sys.platform != "win32", reason="仅支持 Windows")
def test_read_text_detailed_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    """剪贴板没有任何格式时应报告为空。"""
    _install_clip_fakes(
        monkeypatch,
        _user32_clip_lib(available_result=0, count_result=0),
        _kernel32_lib(),
    )

    assert read_text_detailed() == ReadResult(ClipboardStatus.EMPTY, None)


@pytest.mark.skipif(sys.platform != "win32", reason="仅支持 Windows")
def test_read_text_detailed_not_text(monkeypatch: pytest.MonkeyPatch) -> None:
    """剪贴板有内容但没有文本格式时应报告非文本。"""
    _install_clip_fakes(
        monkeypatch,
        _user32_clip_lib(available_result=0, count_result=3),
        _kernel32_lib(),
    )

    assert read_text_detailed() == ReadResult(ClipboardStatus.NOT_TEXT, None)


@pytest.mark.skipif(sys.platform != "win32", reason="仅支持 Windows")
def test_read_text_detailed_os_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """全局内存锁失败时应报告系统错误。"""
    _install_clip_fakes(
        monkeypatch,
        _user32_clip_lib(data_result=123),
        _kernel32_lib(lock_result=0),
    )

    assert read_text_detailed() == ReadResult(ClipboardStatus.OS_ERROR, None)


@pytest.mark.skipif(sys.platform != "win32", reason="仅支持 Windows")
def test_read_text_returns_none_when_locked(monkeypatch: pytest.MonkeyPatch) -> None:
    """read_text 在剪贴板被占用时返回 None。"""
    _install_clip_fakes(
        monkeypatch, _user32_clip_lib(open_result=0), _kernel32_lib()
    )

    assert read_text() is None


@pytest.mark.skipif(sys.platform != "win32", reason="仅支持 Windows")
def test_read_text_detailed_retries_until_unlocked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """剪贴板被占用时应短暂重试，解锁后成功读取。"""
    buffer = ctypes.create_unicode_buffer("重试文本")
    open_clipboard = _SequentialFunction([0, 0, 1])
    user32 = _StubLibrary(
        {
            "OpenClipboard": open_clipboard,
            "CloseClipboard": _StubFunction(1),
            "IsClipboardFormatAvailable": _StubFunction(1),
            "CountClipboardFormats": _StubFunction(5),
            "GetClipboardData": _StubFunction(4321),
        }
    )
    _install_clip_fakes(
        monkeypatch, user32, _kernel32_lib(lock_result=ctypes.addressof(buffer))
    )

    assert read_text_detailed() == ReadResult(ClipboardStatus.OK, "重试文本")
    assert open_clipboard.calls == 3


@pytest.mark.skipif(sys.platform != "win32", reason="仅支持 Windows")
def test_read_text_detailed_locked_after_exhausting_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """重试次数耗尽后仍被占用时应报告占用状态。"""
    open_clipboard = _SequentialFunction([0])
    user32 = _StubLibrary(
        {
            "OpenClipboard": open_clipboard,
            "CloseClipboard": _StubFunction(1),
            "IsClipboardFormatAvailable": _StubFunction(1),
            "CountClipboardFormats": _StubFunction(5),
            "GetClipboardData": _StubFunction(4321),
        }
    )
    _install_clip_fakes(monkeypatch, user32, _kernel32_lib())

    assert read_text_detailed() == ReadResult(ClipboardStatus.LOCKED, None)
    assert open_clipboard.calls == 3


@pytest.mark.integration
@pytest.mark.skipif(sys.platform != "win32", reason="仅支持 Windows")
def test_read_text_from_real_clipboard() -> None:
    """读取当前真实 Windows 剪贴板且不修改其内容。"""
    read_text()


# ---------- 输入法 ----------

class _RecordingFunction:
    """记录调用参数并返回固定值的伪外部函数。"""

    def __init__(self, result: object = 1) -> None:
        self.result = result
        self.calls: list[tuple[object, ...]] = []
        self.argtypes: list[object] = []
        self.restype: object = None

    def __call__(self, *args: object) -> object:
        self.calls.append(args)
        return self.result


def _install_ime_fakes(
    monkeypatch: pytest.MonkeyPatch, user32: object, imm32: object
) -> None:
    """把输入法模块缓存的外部库替换为伪实现。"""
    monkeypatch.setattr(main_module, "_user32_ime", user32)
    monkeypatch.setattr(main_module, "_imm32", imm32)


@pytest.mark.skipif(sys.platform != "win32", reason="仅支持 Windows")
def test_suspend_ime_closes_open_ime(monkeypatch: pytest.MonkeyPatch) -> None:
    """输入法开启时应关闭它并返回完整令牌。"""
    user32 = _StubLibrary(
        {
            "GetGUIThreadInfo": _RecordingFunction(0),
            "GetForegroundWindow": _RecordingFunction(111),
        }
    )
    set_open_status = _RecordingFunction(1)
    imm32 = _StubLibrary(
        {
            "ImmGetContext": _RecordingFunction(222),
            "ImmGetOpenStatus": _RecordingFunction(1),
            "ImmSetOpenStatus": set_open_status,
        }
    )
    _install_ime_fakes(monkeypatch, user32, imm32)

    token = suspend_ime()

    assert token == ImeState(hwnd=111, himc=222, was_open=True)
    assert set_open_status.calls == [(222, 0)]


@pytest.mark.skipif(sys.platform != "win32", reason="仅支持 Windows")
def test_suspend_ime_returns_none_without_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """焦点窗口没有输入法上下文时应返回 None 且不改状态。"""
    user32 = _StubLibrary(
        {
            "GetGUIThreadInfo": _RecordingFunction(0),
            "GetForegroundWindow": _RecordingFunction(111),
        }
    )
    set_open_status = _RecordingFunction(1)
    imm32 = _StubLibrary(
        {
            "ImmGetContext": _RecordingFunction(0),
            "ImmGetOpenStatus": _RecordingFunction(1),
            "ImmSetOpenStatus": set_open_status,
        }
    )
    _install_ime_fakes(monkeypatch, user32, imm32)

    assert suspend_ime() is None
    assert set_open_status.calls == []


@pytest.mark.skipif(sys.platform != "win32", reason="仅支持 Windows")
def test_restore_ime_reopens_and_releases(monkeypatch: pytest.MonkeyPatch) -> None:
    """恢复时应重新打开输入法并释放上下文。"""
    set_open_status = _RecordingFunction(1)
    release_context = _RecordingFunction(1)
    imm32 = _StubLibrary(
        {
            "ImmSetOpenStatus": set_open_status,
            "ImmReleaseContext": release_context,
        }
    )
    user32 = _StubLibrary({})
    _install_ime_fakes(monkeypatch, user32, imm32)

    restore_ime(ImeState(hwnd=111, himc=222, was_open=True))

    assert set_open_status.calls == [(222, 1)]
    assert release_context.calls == [(111, 222)]


@pytest.mark.skipif(sys.platform != "win32", reason="仅支持 Windows")
def test_restore_ime_none_token_is_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    """令牌为 None 时恢复应直接忽略。"""
    set_open_status = _RecordingFunction(1)
    imm32 = _StubLibrary({"ImmSetOpenStatus": set_open_status})
    _install_ime_fakes(monkeypatch, _StubLibrary({}), imm32)

    restore_ime(None)

    assert set_open_status.calls == []


# ---------- Unicode 注入 ----------

def _install_input_fakes(monkeypatch: pytest.MonkeyPatch, send_input: object) -> None:
    """把注入模块缓存的 user32 库替换为伪实现。"""
    monkeypatch.setattr(
        main_module, "_user32_input", _StubLibrary({"SendInput": send_input})
    )


@pytest.mark.parametrize(
    ("character", "expected"),
    [
        ("a", [0x61]),
        ("中", [0x4E2D]),
        ("\U0001F600", [0xD83D, 0xDE00]),
    ],
)
def test_code_units(character: str, expected: list[int]) -> None:
    """字符应正确转换为 UTF-16 码元序列。"""
    assert _code_units(character) == expected


@pytest.mark.skipif(sys.platform != "win32", reason="仅支持 Windows")
def test_type_text_batches_events_without_interval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """零间隔时应把多个字符合并为一次批量注入。"""
    send_input = _RecordingFunction(4)
    _install_input_fakes(monkeypatch, send_input)

    type_text("ab", 0)

    assert len(send_input.calls) == 1
    count, events_ptr, size = send_input.calls[0]
    assert count == 4
    assert size == ctypes.sizeof(_INPUT)
    events = ctypes.cast(events_ptr, ctypes.POINTER(_INPUT))
    assert events[0].union.ki.wScan == 0x61
    assert events[0].union.ki.dwFlags == 0x0004
    assert events[1].union.ki.wScan == 0x61
    assert events[1].union.ki.dwFlags == 0x0004 | 0x0002
    assert events[2].union.ki.wScan == 0x62
    assert events[2].union.ki.dwFlags == 0x0004
    assert events[3].union.ki.wScan == 0x62
    assert events[3].union.ki.dwFlags == 0x0004 | 0x0002


@pytest.mark.skipif(sys.platform != "win32", reason="仅支持 Windows")
def test_type_text_with_interval_sends_per_character(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """正间隔时应逐字符注入，每次调用包含一个字符的按下与释放事件。"""
    send_input = _RecordingFunction(2)
    _install_input_fakes(monkeypatch, send_input)
    monkeypatch.setattr(main_module.time, "sleep", lambda _seconds: None)

    type_text("ab", 0.01)

    assert len(send_input.calls) == 2
    for call_args in send_input.calls:
        count, events_ptr, size = call_args
        assert count == 2
        assert size == ctypes.sizeof(_INPUT)
        events = ctypes.cast(events_ptr, ctypes.POINTER(_INPUT))
        assert events[1].union.ki.dwFlags == 0x0004 | 0x0002


@pytest.mark.skipif(sys.platform != "win32", reason="仅支持 Windows")
def test_type_text_sends_surrogate_pair_in_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """增补平面字符的两个码元应按顺序注入。"""
    send_input = _RecordingFunction(4)
    _install_input_fakes(monkeypatch, send_input)

    type_text("\U0001F600", 0)

    assert len(send_input.calls) == 1
    events = ctypes.cast(send_input.calls[0][1], ctypes.POINTER(_INPUT))
    assert events[0].union.ki.wScan == 0xD83D
    assert events[0].union.ki.dwFlags == 0x0004
    assert events[1].union.ki.wScan == 0xD83D
    assert events[1].union.ki.dwFlags == 0x0004 | 0x0002
    assert events[2].union.ki.wScan == 0xDE00
    assert events[2].union.ki.dwFlags == 0x0004
    assert events[3].union.ki.wScan == 0xDE00
    assert events[3].union.ki.dwFlags == 0x0004 | 0x0002


@pytest.mark.skipif(sys.platform != "win32", reason="仅支持 Windows")
def test_type_text_raises_when_system_rejects_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """系统未接受全部注入事件时应抛出 OSError。"""
    send_input = _RecordingFunction(0)
    _install_input_fakes(monkeypatch, send_input)

    with pytest.raises(OSError):
        type_text("a", 0)


@pytest.mark.skipif(sys.platform != "win32", reason="仅支持 Windows")
def test_type_text_raises_on_partially_accepted_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """批量注入只被部分接受时也应抛出 OSError。"""
    send_input = _RecordingFunction(3)
    _install_input_fakes(monkeypatch, send_input)

    with pytest.raises(OSError):
        type_text("ab", 0)


# ---------- 历史缓冲 ----------

def test_history_newest_orders_from_newest() -> None:
    """newest 应按新到旧的顺序返回条目副本。"""
    buffer = HistoryBuffer(3)
    buffer.push("一")
    buffer.push("二")

    assert buffer.newest() == ["二", "一"]
    assert len(buffer) == 2


def test_history_push_ignores_consecutive_duplicates() -> None:
    """连续推送相同文本时只保留一条。"""
    buffer = HistoryBuffer(3)
    buffer.push("一")
    buffer.push("一")
    buffer.push("二")
    buffer.push("二")

    assert buffer.newest() == ["二", "一"]
    assert len(buffer) == 2


def test_history_capacity_evicts_oldest() -> None:
    """超出容量时最旧条目应被淘汰。"""
    buffer = HistoryBuffer(2)
    buffer.push("一")
    buffer.push("二")
    buffer.push("三")

    assert buffer.newest() == ["三", "二"]


def test_history_newest_returns_copy() -> None:
    """返回的列表不应受后续 push 影响。"""
    buffer = HistoryBuffer(3)
    buffer.push("一")
    snapshot = buffer.newest()

    buffer.push("二")

    assert snapshot == ["一"]


def test_history_rejects_invalid_size() -> None:
    """容量小于 1 时构造应抛出 ValueError。"""
    with pytest.raises(ValueError):
        HistoryBuffer(0)


# ---------- 热键辅助 ----------

def test_conflicting_hotkey_pair_returns_first_duplicate() -> None:
    """存在键集合相同的热键时应返回其下标对。"""
    key_sets = [frozenset({"a"}), frozenset({"b"}), frozenset({"a"})]

    assert _conflicting_hotkey_pair(key_sets) == (0, 2)


def test_conflicting_hotkey_pair_none_when_distinct() -> None:
    """热键互不相同时应返回 None。"""
    key_sets = [frozenset({"a"}), frozenset({"b"}), frozenset({"c"})]

    assert _conflicting_hotkey_pair(key_sets) is None