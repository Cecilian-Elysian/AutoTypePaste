"""剪贴板读取状态单元测试与 Windows 集成测试。"""

import ctypes
import sys

import pytest

import autotype.clipboard as clipboard_module
from autotype.clipboard import ClipboardStatus, ReadResult, read_text, read_text_detailed


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


def _install_fakes(
    monkeypatch: pytest.MonkeyPatch, user32: object, kernel32: object
) -> None:
    """把剪贴板模块缓存的外部库替换为伪实现，并屏蔽重试等待。"""
    monkeypatch.setattr(clipboard_module, "_USER32", user32)
    monkeypatch.setattr(clipboard_module, "_KERNEL32", kernel32)
    monkeypatch.setattr(clipboard_module.time, "sleep", lambda _seconds: None)


def _user32_library(
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


def _kernel32_library(*, lock_result: object = 1) -> _StubLibrary:
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
    _install_fakes(
        monkeypatch,
        _user32_library(data_result=4321),
        _kernel32_library(lock_result=ctypes.addressof(buffer)),
    )

    assert read_text_detailed() == ReadResult(ClipboardStatus.OK, "剪贴板文本")


@pytest.mark.skipif(sys.platform != "win32", reason="仅支持 Windows")
def test_read_text_detailed_locked(monkeypatch: pytest.MonkeyPatch) -> None:
    """打开剪贴板失败时应报告占用状态。"""
    _install_fakes(monkeypatch, _user32_library(open_result=0), _kernel32_library())

    assert read_text_detailed() == ReadResult(ClipboardStatus.LOCKED, None)


@pytest.mark.skipif(sys.platform != "win32", reason="仅支持 Windows")
def test_read_text_detailed_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    """剪贴板没有任何格式时应报告为空。"""
    _install_fakes(
        monkeypatch,
        _user32_library(available_result=0, count_result=0),
        _kernel32_library(),
    )

    assert read_text_detailed() == ReadResult(ClipboardStatus.EMPTY, None)


@pytest.mark.skipif(sys.platform != "win32", reason="仅支持 Windows")
def test_read_text_detailed_not_text(monkeypatch: pytest.MonkeyPatch) -> None:
    """剪贴板有内容但没有文本格式时应报告非文本。"""
    _install_fakes(
        monkeypatch,
        _user32_library(available_result=0, count_result=3),
        _kernel32_library(),
    )

    assert read_text_detailed() == ReadResult(ClipboardStatus.NOT_TEXT, None)


@pytest.mark.skipif(sys.platform != "win32", reason="仅支持 Windows")
def test_read_text_detailed_os_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """全局内存锁失败时应报告系统错误。"""
    _install_fakes(
        monkeypatch, _user32_library(data_result=123), _kernel32_library(lock_result=0)
    )

    assert read_text_detailed() == ReadResult(ClipboardStatus.OS_ERROR, None)


@pytest.mark.skipif(sys.platform != "win32", reason="仅支持 Windows")
def test_read_text_returns_none_when_locked(monkeypatch: pytest.MonkeyPatch) -> None:
    """旧接口在剪贴板被占用时仍应返回 None。"""
    _install_fakes(monkeypatch, _user32_library(open_result=0), _kernel32_library())

    assert read_text() is None


@pytest.mark.skipif(sys.platform != "win32", reason="仅支持 Windows")
def test_read_text_detailed_retries_until_unlocked(monkeypatch: pytest.MonkeyPatch) -> None:
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
    _install_fakes(
        monkeypatch, user32, _kernel32_library(lock_result=ctypes.addressof(buffer))
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
    _install_fakes(monkeypatch, user32, _kernel32_library())

    assert read_text_detailed() == ReadResult(ClipboardStatus.LOCKED, None)
    assert open_clipboard.calls == 3


@pytest.mark.integration
@pytest.mark.skipif(sys.platform != "win32", reason="仅支持 Windows")
def test_read_text_from_real_clipboard() -> None:
    """读取当前真实 Windows 剪贴板且不修改其内容。"""
    read_text()
