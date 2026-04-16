# VCPToolBox Auto Updater — Agent 知识库

> 本文档面向 AI Coding Agent。阅读前请勿假设任何未记录的信息。

## 项目概览

VCPToolBox Auto Updater 是一个基于 Python 的 Windows 后台服务，用于 7×24 小时自动检测 VCPToolBox 远程 Git 仓库的更新。当检测到新提交时，它会自动将本地更改与远程合并，冲突时以远程版本为准（`git merge -X theirs origin/<branch>`），并在更新成功后自动重启指定的 PM2 进程。

- **名称**：`vcptoolbox-updater`（PyPI/包名）
- **版本**：1.0.0
- **Python 要求**：>= 3.14
- **操作系统**：Windows（依赖 `pywin32` 实现 Windows Service）

## 技术栈

| 功能 | 依赖 |
|:---|:---|
| Windows 服务 | `pywin32>=308` |
| 定时调度 | `APScheduler>=3.11.0` |
| 配置校验与解析 | `pydantic>=2.10.0`, `pydantic-settings>=2.7.0`, `pyyaml>=6.0.2` |
| 结构化日志 | `structlog>=24.4.0` |
| CLI | `click>=8.1.0` |
| 飞书通知 | `lark-oapi>=1.4.0` |
| 企业微信通知 | `requests>=2.32.0` |
| 邮件通知 | `smtplib`（标准库） |
| 构建后端 | `hatchling` |

## 代码组织

**注意：当前文件系统布局与导入声明存在不一致，详见下方【已知问题与不一致】。**

```
vcptoolbox-auto-updater/
├── pyproject.toml          # 项目元数据、依赖、构建系统、CLI entry point
├── config.yaml             # 运行时配置文件（YAML）
├── README.md               # 面向人类的中文文档
├── scripts/
│   └── install_service.ps1 # 以管理员身份安装 Windows 服务的 PowerShell 脚本
├── src/                    # Python 源码实际存放目录
│   ├── __init__.py
│   ├── __main__.py         # python -m vcptoolbox_updater 入口
│   ├── cli.py              # click CLI：service / install / uninstall / start / stop / update
│   ├── config.py           # Pydantic 配置模型与 YAML 加载
│   ├── git_ops.py          # GitOperator：fetch、rev-parse、hard-reset
│   ├── pm2_ops.py          # Pm2Operator：restart、save
│   ├── scheduler.py        # UpdateScheduler：APScheduler BackgroundScheduler 封装
│   ├── service.py          # AutoUpdaterService：pywin32 Windows Service 实现
│   ├── utils.py            # structlog 初始化与日志处理器（文件 / EventLog）
│   └── notifications/      # 通知通道实现
│       ├── __init__.py     # 工厂函数 build_notifiers
│       ├── base.py         # NotificationChannel ABC + UpdateReport dataclass
│       ├── feishu.py       # 飞书 Lark 官方 SDK
│       ├── wecom.py        # 企业微信 Webhook
│       └── email.py        # SMTP 邮件
└── tests/                  # pytest 单元测试
    ├── __init__.py
    ├── test_config.py      # 配置加载测试
    └── test_git_ops.py     # GitOperator Mock 测试
```

### 模块职责

| 文件 | 职责 |
|:---|:---|
| `cli.py` | CLI 入口。`service` 命令供 SCM 调用；`update` 命令支持手动触发单次更新周期。 |
| `service.py` | Windows Service 生命周期管理：`SvcDoRun` 加载配置、启动 scheduler、立即执行一次 job，随后进入等待循环；`SvcStop` 优雅停止 scheduler 并设置 stop event。 |
| `git_ops.py` | 封装原生 `git` 子进程调用。核心策略：**merge preferring remote**（`git merge -X theirs`）。本地有未提交更改时会先自动 `git commit` 保留，然后再执行 merge；若存在结构性冲突，则执行 `git checkout --theirs .` 强制以远程为准。 |
| `pm2_ops.py` | 封装 `pm2` 子进程调用，自动在 PATH 中查找 `pm2` 可执行文件。 |
| `scheduler.py` | 基于 `IntervalTrigger(hours=...)` 的后台定时任务封装。 |
| `config.py` | 使用 `pydantic_settings.BaseSettings` 定义分层配置模型，支持从 YAML 反序列化。 |
| `utils.py` | `configure_logging` 区分 CLI 模式（控制台彩色输出）与服务模式（RotatingFileHandler + NTEventLogHandler）。 |

## 构建、测试与运行命令

### 安装依赖
```powershell
cd F:\AI_Study_studio\VCPToolBox\vcptoolbox-auto-updater
uv sync
```

### 运行测试
当前测试基于 `pytest`，测试文件位于 `tests/`：
```powershell
uv run pytest
```
测试覆盖：
- `test_config.py`：验证 YAML 配置加载与 Pydantic 模型转换。
- `test_git_ops.py`：通过 `unittest.mock` 模拟 `subprocess` 行为，验证 `GitOperator` 的分支比较逻辑。

> **注意**：`test_git_ops.py` 导入了 `pytest` 但未使用其 fixture，断言完全基于标准 `assert`。

### CLI 使用
```powershell
# 手动触发单次更新
uv run python -m vcptoolbox_updater update

# Windows 服务管理（也可直接用 uv run python -m vcptoolbox_updater <cmd>）
uv run python -m vcptoolbox_updater install
uv run python -m vcptoolbox_updater start
uv run python -m vcptoolbox_updater stop
uv run python -m vcptoolbox_updater uninstall
```

### 安装为 Windows 服务（推荐）
以管理员身份运行 PowerShell：
```powershell
.\scripts\install_service.ps1
```
该脚本会：
1. 自动运行 `uv sync` 创建 `.venv` 并安装依赖
2. 安装服务
3. 设置系统环境变量 `VCPTOOLBOX_UPDATER_CONFIG` 指向项目根目录的 `config.yaml`
4. 配置服务为自动启动、失败时自动恢复
5. 启动服务

## 运行时架构

1. **服务启动**（`service.py`）：
   - 解析 `config.yaml`（优先读取 `VCPTOOLBOX_UPDATER_CONFIG` 环境变量）。
   - 初始化 `structlog`（服务模式输出 JSON 到文件 + Windows EventLog）。
   - 构造 `GitOperator`、`Pm2Operator`、通知通道列表。
   - 启动 `UpdateScheduler`，注册定时任务。
   - **立即执行一次更新**（`job()`），随后按间隔循环。
   - 主线程进入 `WaitForSingleObject` 循环，等待服务停止信号。

2. **更新周期**（`job()` / `cli.py update`）：
   - `git fetch`
   - 比较 `HEAD` 与 `origin/<branch>`
   - 如有更新：自动 commit 本地更改 → `git merge -X theirs origin/<branch>`（冲突时强制以远程为准） → `pm2 restart <process_name>`
   - 发送通知报告（成功/失败）

## 配置说明

关键配置在 `config.yaml`：

```yaml
service_name: "VCPToolBoxAutoUpdater"
display_name: "VCP ToolBox Auto Updater"
description: "..."
log_level: INFO
log_file: "C:/Logs/vcptoolbox-updater.log"

git:
  repo_path: "F:/AI_Study_studio/VCPToolBox"
  remote_name: "origin"
  branch: "main"
  check_interval_hours: 24.0

pm2:
  process_name: "vcptoolbox"
  # pm2_bin: "C:/.../pm2.cmd"  # 可选，默认自动从 PATH 查找

notifications:
  feishu: { enabled: false, ... }
  wecom:  { enabled: false, ... }
  email:  { enabled: false, ... }
```

- `repo_path` 必须指向已初始化的 Git 仓库（本地已有 `origin` 远程）。
- `pm2.process_name` 必须是 PM2 中已保存的进程名。

## 安全与风险提醒

- **Merge Preferring Remote 策略**：`git_ops.py` 使用 `git merge -X theirs origin/<branch>` 合并远程更改；若存在结构性冲突，则执行 `git checkout --theirs .` 强制以远程为准。本地有未提交更改时会先自动 `git commit` 保留，使其作为独立 commit 参与 merge。
- **子进程执行**：Git 与 PM2 操作均通过 `subprocess.run(..., check=True)` 调用外部命令。输入参数来自配置文件，未对用户输入做转义过滤（当前场景下可控）。
- **敏感信息**：`config.yaml` 包含 `app_secret`、`password`、`webhook_url`。请勿将其提交到版本控制。
- **权限**：Windows 服务安装与运行需要管理员权限。`install_service.ps1` 顶部包含 `#Requires -RunAsAdministrator`。
- **pywin32 依赖**：非 Windows 环境无法直接运行服务代码（`service.py`、`cli.py` 中的 `service` 命令会导入失败）。

## 代码风格与约定

- **类型注解**：所有公共函数/方法均带 `from __future__ import annotations` 与类型提示。
- **日志**：统一使用 `structlog` 结构化日志，通过 `utils.get_logger(__name__)` 获取 logger。避免直接使用 `logging` 或 `print`。
- **配置**：所有运行时参数通过 `pydantic_settings` 模型校验，禁止在业务代码中直接读取环境变量或 YAML。
- **异常处理**：服务主循环中的异常会被捕获并记录到 EventLog，随后抛出以触发 Windows Service 的故障恢复机制。

## 已知问题与不一致（Agent 必读）

**源码目录结构**：
- Python 源码已统一放置在 `src/vcptoolbox_updater/` 目录下。
- `pyproject.toml` 中已配置 `tool.hatch.build.targets.wheel.packages = ["src/vcptoolbox_updater"]`，安装后可正常通过包名 `vcptoolbox_updater` 导入。
- 开发和测试均通过 `uv` 管理，使用 `uv run` 执行命令。
