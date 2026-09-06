# AutoTypePaste

Windows 小工具,适用于文本无法 CTRL + V 粘贴输入的情况


## 使用

方法一(普通用户):
双击`AutoTypePaste.exe`快速使用

方法二(项目测试):
使用`Start-AutoTypePaste.bat`快捷调用(桌面创建指定快捷方式)

方法三(项目测试):
进入项目根目录
```
启动程序
.venv\Scripts\python.exe -m autotype

修改配置
src/autotype/config.py
```

>复制要输入的文字,点击目标输入框，使其获得焦点,按 Ctrl+F9，程序会等待约 0.25 秒，然后逐字符输入剪贴板内容,使用 Ctrl+Alt+Q 退出程序；也可以在 PowerShell 中按 Ctrl+C

默认配置(可修改配置)：

| 配置 | 默认值 | 作用 |
|---|---|---|
| `HOTKEY` | `<ctrl>+<f9>` | 读取并键入剪贴板文本 |
| `EXIT_HOTKEY` | `<ctrl>+<alt>+q` | 停止常驻程序 |
| `CHARACTER_INTERVAL` | `0.01` | 字符之间的间隔（秒） |
| `START_DELAY` | `0.25` | 等待触发热键释放后的延迟（秒） |

编辑 `src/autotype/config.py` 顶部常量即可修改配置,程序目前没有 CLI 或 GUI


## 开发检查

```text
pytest -m "not integration"
pytest -m integration
mypy src/autotype
```

## 文件结构
开发板
```
AutoTypePaste/
├─ .git/                       # 本地 Git 仓库
├─ .gitignore                  # 忽略 .venv、缓存、构建产物
├─ .venv/                      # Python 3.12 虚拟环境，不分发
├─ .mypy_cache/                # mypy 缓存，不分发
├─ .pytest_cache/              # pytest 缓存，不分发
├─ AGENTS.md                   # 工程契约
├─ README.md                   # 使用、限制、检查命令
├─ requirements.txt            # 运行依赖：pynput
├─ pyproject.toml              # 包元数据、pytest/mypy、dev 依赖
├─ Start-AutoTypePaste.bat     # 源码版快捷启动脚本
├─ src/
│  └─ autotype/
│     ├─ __init__.py           # 包版本与说明
│     ├─ __main__.py           # `python -m autotype` 入口
│     ├─ config.py             # 热键、字符间隔、启动延迟配置
│     ├─ clipboard.py          # Windows ctypes 读取 CF_UNICODETEXT
│     └─ typer.py              # pynput 热键监听与逐字符键入
└─ tests/
   ├─ test_config.py           # 默认配置单测
   └─ test_clipboard.py        # Windows 剪贴板集成测试
```

分发版
```
AutoTypePaste/
├─ AutoTypePaste.exe
├─ config.json                 # 外部可编辑配置
└─ README.txt
```
## 注意事项

- Windows 10/11，64 位
- EXE 版通常不需要安装 Python 或额外运行库.可直接使用
- 必须运行于有交互桌面的登录会话中，不支持 Windows 服务、纯后台 Session
- 输入框若以管理员权限运行，AutoTypePaste 也必须以管理员权限运行，否则 Windows 的权限隔离会拦截键盘注入
- RDP、某些游戏反作弊、安全软件、沙盒应用或特殊输入框可能拦截全局热键或模拟输入(未测试)
- Windows Defender/企业安全策略可能对自打包 EXE 产生提示；代码签名可降低此问题，但不是功能必需(未测试)
- 程序不会修改剪贴板内容
- 输入期间不要切换焦点窗口，否则文本可能被键入到新的焦点窗口

最后修改日期: 2026.9.6 15:15