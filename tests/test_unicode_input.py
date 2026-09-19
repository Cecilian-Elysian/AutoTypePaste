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
def test_type_text_sends_unicode_events(monkeypatch: pytest.MonkeyPatch) -> None:
    """每个字符应注入按下与释放两个 Unicode 键盘事件。"""
    send_input = _RecordingFunction(2)
    def fake_win_dll(name: str, use_last_error: bool = False) -> _StubLibrary:
        return _StubLibrary({"SendInput": send_input})

    monkeypatch.setattr(unicode_input_module.ctypes, "WinDLL", fake_win_dll)

    type_text("ab", 0)

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
    send_input = _RecordingFunction(2)

    def fake_win_dll(name: str, use_last_error: bool = False) -> _StubLibrary:
        return _StubLibrary({"SendInput": send_input})

    monkeypatch.setattr(unicode_input_module.ctypes, "WinDLL", fake_win_dll)

    type_text("\U0001F600", 0)

    assert len(send_input.calls) == 2
    first = ctypes.cast(send_input.calls[0][1], ctypes.POINTER(_INPUT))
    second = ctypes.cast(send_input.calls[1][1], ctypes.POINTER(_INPUT))
    assert first[0].union.ki.wScan == 0xD83D
    assert first[0].union.ki.dwFlags == 0x0004
    assert first[1].union.ki.wScan == 0xD83D
    assert first[1].union.ki.dwFlags == 0x0004 | 0x0002
    assert second[0].union.ki.wScan == 0xDE00
    assert second[1].union.ki.wScan == 0xDE00
