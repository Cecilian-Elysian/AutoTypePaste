"""配置模块的快速单元测试。"""

import json
from pathlib import Path

import pytest

from autotype.config import AppConfig, ConfigError, load_config


def test_load_config_reads_valid_values(tmp_path: Path) -> None:
    """有效的 JSON 配置应加载为强类型配置对象。"""
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

    assert load_config(config_path) == AppConfig("<ctrl>+<f9>", "<ctrl>+<alt>+q", 0.01, 0.25)


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
