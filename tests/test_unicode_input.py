"""Unicode 注入模块的快速单元测试。"""

import ctypes
import sys

import pytest

import autotype.unicode_input as unicode_input_module
from autotype.unicode_input import _INPUT, _code_units, type_text


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


class _StubLibrary:
    """以属性形式暴露伪外部函数的伪动态库。"""

    def __init__(self, functions: dict[str, _RecordingFunction]) -> None:
        self._functions = functions

    def __getattr__(self, name: str) -> _RecordingFunction:
        return self._functions[name]


def _install_user32(monkeypatch: pytest.MonkeyPatch, send_input: _RecordingFunction) -> None:
    """把注入模块缓存的 user32 库替换为伪实现。"""
    monkeypatch.setattr(
        unicode_input_module, "_USER32", _StubLibrary({"SendInput": send_input})
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
def test_type_text_batches_events_without_interval(monkeypatch: pytest.MonkeyPatch) -> None:
    """零间隔时应把多个字符合并为一次批量注入。"""
    send_input = _RecordingFunction(4)
    _install_user32(monkeypatch, send_input)

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
def test_type_text_with_interval_sends_per_character(monkeypatch: pytest.MonkeyPatch) -> None:
    """正间隔时应逐字符注入，每次调用包含一个字符的按下与释放事件。"""
    send_input = _RecordingFunction(2)
    _install_user32(monkeypatch, send_input)
    monkeypatch.setattr(unicode_input_module.time, "sleep", lambda _seconds: None)

    type_text("ab", 0.01)

    assert len(send_input.calls) == 2
    for call_args in send_input.calls:
        count, events_ptr, size = call_args
        assert count == 2
        assert size == ctypes.sizeof(_INPUT)
        events = ctypes.cast(events_ptr, ctypes.POINTER(_INPUT))
        assert events[1].union.ki.dwFlags == 0x0004 | 0x0002


@pytest.mark.skipif(sys.platform != "win32", reason="仅支持 Windows")
def test_type_text_sends_surrogate_pair_in_order(monkeypatch: pytest.MonkeyPatch) -> None:
    """增补平面字符的两个码元应按顺序注入。"""
    send_input = _RecordingFunction(4)
    _install_user32(monkeypatch, send_input)

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
def test_type_text_raises_when_system_rejects_events(monkeypatch: pytest.MonkeyPatch) -> None:
    """系统未接受全部注入事件时应抛出 OSError。"""
    send_input = _RecordingFunction(0)
    _install_user32(monkeypatch, send_input)

    with pytest.raises(OSError):
        type_text("a", 0)


@pytest.mark.skipif(sys.platform != "win32", reason="仅支持 Windows")
def test_type_text_raises_on_partially_accepted_events(monkeypatch: pytest.MonkeyPatch) -> None:
    """批量注入只被部分接受时也应抛出 OSError。"""
    send_input = _RecordingFunction(3)
    _install_user32(monkeypatch, send_input)

    with pytest.raises(OSError):
        type_text("ab", 0)
