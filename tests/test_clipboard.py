"""Windows 剪贴板集成测试。"""

import sys

import pytest

from autotype.clipboard import read_text


@pytest.mark.integration
@pytest.mark.skipif(sys.platform != "win32", reason="仅支持 Windows")
def test_read_text_from_real_clipboard() -> None:
    """读取当前真实 Windows 剪贴板且不修改其内容。"""
    read_text()
