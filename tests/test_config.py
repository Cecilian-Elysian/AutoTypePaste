"""配置模块的快速单元测试。"""

import json
from pathlib import Path

import pytest

from autotype.config import (
    DEFAULT_DISABLE_IME,
    DEFAULT_FEEDBACK,
    DEFAULT_HISTORY_SIZE,
    DEFAULT_SLOT2_HOTKEY,
    DEFAULT_UNICODE_INPUT,
    AppConfig,
    ConfigError,
    load_config,
)


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

    assert load_config(config_path) == AppConfig(
        "<ctrl>+<f9>",
        "<ctrl>+<alt>+q",
        0.01,
        0.25,
        DEFAULT_SLOT2_HOTKEY,
        DEFAULT_HISTORY_SIZE,
        DEFAULT_FEEDBACK,
        DEFAULT_DISABLE_IME,
        DEFAULT_UNICODE_INPUT,
    )


def test_load_config_reads_all_fields(tmp_path: Path) -> None:
    """包含新增字段的完整配置应全部生效。"""
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
        "<ctrl>+<f9>", "<ctrl>+<alt>+q", 0.02, 0.3, "<ctrl>+<f11>", 3, False, False, False
    )


def test_load_config_tolerates_utf8_bom(tmp_path: Path) -> None:
    """带 BOM 的 UTF-8 配置（如记事本保存）应正常加载。"""
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
