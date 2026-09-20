"""键入模块的快速单元测试。"""

from autotype.typer import HistoryBuffer, _conflicting_hotkey_pair, _resolve_slot_text


def test_snapshot_orders_from_newest() -> None:
    """snapshot 应按新到旧的顺序返回条目。"""
    buffer = HistoryBuffer(3)
    buffer.push("一")
    buffer.push("二")

    assert buffer.snapshot(1) == "二"
    assert buffer.snapshot(2) == "一"
    assert buffer.snapshot(3) is None


def test_push_ignores_consecutive_duplicates() -> None:
    """连续推送相同文本时只保留一条。"""
    buffer = HistoryBuffer(3)
    buffer.push("一")
    buffer.push("一")
    buffer.push("二")
    buffer.push("二")

    assert buffer.snapshot(1) == "二"
    assert buffer.snapshot(2) == "一"
    assert buffer.snapshot(3) is None


def test_capacity_evicts_oldest() -> None:
    """超出容量时最旧条目应被淘汰。"""
    buffer = HistoryBuffer(2)
    buffer.push("一")
    buffer.push("二")
    buffer.push("三")

    assert buffer.snapshot(1) == "三"
    assert buffer.snapshot(2) == "二"
    assert buffer.snapshot(3) is None


def test_snapshot_empty_buffer_returns_none() -> None:
    """空缓冲的任意槽位都应返回 None。"""
    assert HistoryBuffer(3).snapshot(1) is None


def test_resolve_slot_one_returns_latest() -> None:
    """第一槽位应键入最新条目。"""
    buffer = HistoryBuffer(3)
    buffer.push("一")
    buffer.push("二")

    assert _resolve_slot_text(buffer, 1) == "二"


def test_resolve_slot_two_requires_previous() -> None:
    """第二槽位应严格取上一条历史，不足两条时返回 None 而不回退到最新。"""
    buffer = HistoryBuffer(3)
    buffer.push("一")

    assert _resolve_slot_text(buffer, 2) is None

    buffer.push("二")

    assert _resolve_slot_text(buffer, 2) == "一"


def test_conflicting_hotkey_pair_returns_first_duplicate() -> None:
    """存在键集合相同的热键时应返回其下标对。"""
    key_sets = [frozenset({"a"}), frozenset({"b"}), frozenset({"a"})]

    assert _conflicting_hotkey_pair(key_sets) == (0, 2)


def test_conflicting_hotkey_pair_none_when_distinct() -> None:
    """热键互不相同时应返回 None。"""
    key_sets = [frozenset({"a"}), frozenset({"b"}), frozenset({"c"})]

    assert _conflicting_hotkey_pair(key_sets) is None
