"""键入模块的快速单元测试。"""

from autotype.typer import HistoryBuffer


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
