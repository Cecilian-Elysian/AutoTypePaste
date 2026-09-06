# AGENTS.md

AutoTypePaste 的工程契约。

## 编码风格

1. 不使用 emoji。
2. 公开 API 使用中文 docstring。
3. 函数签名完整标注类型。
4. CLI 输出不是本项目功能；运行状态信息使用标准库 ANSI 输出。
5. 保持依赖最小化：运行时仅依赖 `pynput`，剪贴板读取使用 Windows ctypes。

## 测试

1. 默认运行 `pytest -m "not integration"`。
2. 真实 Windows 剪贴板测试使用 `@pytest.mark.integration`，手动运行 `pytest -m integration`。
3. 使用 `mypy src/autotype` 检查源码。

## 退出码

| 码 | 含义 |
|---|---|
| 0 | 正常退出 |
| 2 | 配置文件无效或键盘监听初始化失败 |
| 3 | pynput 依赖缺失 |
