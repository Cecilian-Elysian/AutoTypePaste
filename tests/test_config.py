"""配置模块的快速单元测试。"""

from autotype import config


def test_default_config() -> None:
    """默认热键和时间参数应符合约定。"""
    assert config.HOTKEY == "<ctrl>+<f9>"
    assert config.EXIT_HOTKEY == "<ctrl>+<alt>+q"
    assert config.CHARACTER_INTERVAL > 0
    assert config.START_DELAY >= 0
