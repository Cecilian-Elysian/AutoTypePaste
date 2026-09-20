"""输入法挂起模块的快速单元测试。"""

import sys

import pytest

import autotype.ime as ime_module
from autotype.ime import ImeState, restore_ime, suspend_ime


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


def _install_fakes(
    monkeypatch: pytest.MonkeyPatch, user32: _StubLibrary, imm32: _StubLibrary
) -> None:
    """把输入法模块缓存的外部库替换为伪实现。"""
    monkeypatch.setattr(ime_module, "_USER32", user32)
    monkeypatch.setattr(ime_module, "_IMM32", imm32)


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
    _install_fakes(monkeypatch, user32, imm32)

    token = suspend_ime()

    assert token == ImeState(hwnd=111, himc=222, was_open=True)
    assert set_open_status.calls == [(222, 0)]


@pytest.mark.skipif(sys.platform != "win32", reason="仅支持 Windows")
def test_suspend_ime_returns_none_without_context(monkeypatch: pytest.MonkeyPatch) -> None:
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
    _install_fakes(monkeypatch, user32, imm32)

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
    _install_fakes(monkeypatch, user32, imm32)

    restore_ime(ImeState(hwnd=111, himc=222, was_open=True))

    assert set_open_status.calls == [(222, 1)]
    assert release_context.calls == [(111, 222)]


@pytest.mark.skipif(sys.platform != "win32", reason="仅支持 Windows")
def test_restore_ime_none_token_is_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    """令牌为 None 时恢复应直接忽略。"""
    set_open_status = _RecordingFunction(1)
    imm32 = _StubLibrary({"ImmSetOpenStatus": set_open_status})
    _install_fakes(monkeypatch, _StubLibrary({}), imm32)

    restore_ime(None)

    assert set_open_status.calls == []
