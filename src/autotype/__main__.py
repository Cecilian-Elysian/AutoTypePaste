"""AutoTypePaste 的模块入口。"""

from autotype.typer import run


def main() -> None:
    """启动 AutoTypePaste 并处理控制台中断。"""
    try:
        raise SystemExit(run())
    except KeyboardInterrupt:
        raise SystemExit(0) from None


if __name__ == "__main__":
    main()
