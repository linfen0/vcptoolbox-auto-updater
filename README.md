# VCPToolBox Auto Updater

7×24 小时自动检测 VCPToolBox 远程 Git 仓库更新，强制以远程版本同步本地，并自动重启 PM2 进程的 Windows 服务。

## 功能特性

- **Windows 服务形态**：开机自启，崩溃自动恢复
- **定时检测**：默认每 24 小时检测一次远程提交
- **远程优先同步**：采用 `stash → reset --hard → reconcile` 策略，冲突时以远程版本为准，仅保留 stash 中新增的文件
- **PM2 自动托管**：通过 `pm2 startOrRestart` 重启服务，由 `config.yaml` 自动生成临时 ecosystem 文件管理多进程
- **多通道通知**：飞书（官方 SDK）、企业微信（Webhook）、邮件（SMTP）
- **手动更新 CLI / TUI**：支持命令行与终端界面手动触发更新

## 项目结构

```
vcptoolbox-auto-updater/
├── pyproject.toml
├── config.yaml
├── README.md
├── scripts/
│   └── install_service.ps1
├── src/
│   └── vcptoolbox_updater/
│       ├── __init__.py
│       ├── __main__.py
│       ├── cli.py
│       ├── config.py
│       ├── git_ops.py
│       ├── pm2_ops.py
│       ├── scheduler.py
│       ├── service.py
│       ├── update_report.py
│       ├── utils.py
│       ├── notifications/
│       │   ├── __init__.py
│       │   ├── base.py
│       │   ├── feishu.py
│       │   ├── wecom.py
│       │   └── email.py
│       └── tui/
│           ├── __init__.py
│           ├── app.py
│           ├── i18n.py
│           └── screens/
│               ├── main_menu.py
│               ├── log_viewer.py
│               ├── service_manager.py
│               └── manual_update.py
└── tests/
    ├── __init__.py
    ├── test_cli.py
    ├── test_config.py
    ├── test_git_ops.py
    ├── test_notifications.py
    ├── test_pm2_ops.py
    ├── test_scheduler.py
    ├── test_utils.py
    └── test_tui/
```

## 快速开始

### 1. 安装依赖

```powershell
uv sync
```

### 2. 配置

编辑 `config.yaml`，至少修改以下字段：

```yaml
service_name: "VCPToolBoxAutoUpdater"
display_name: "VCP ToolBox Auto Updater"
description: "自动检测更新并重启服务的 Windows 后台服务"
log_level: INFO
log_file: "F:/Logs/vcptoolbox-updater.log"

git:
  repo_path: "F:/AI_Study_studio/VCPToolBox"
  remote_name: "origin"
  branch: "main"
  check_interval_hours: 24.0

pm2:
  pm2_bin: null           # 可选，默认自动从 PATH 查找
  processes:
    - name: "vcp-main"
      script: "server.js"
      watch: false
      max_memory_restart: "1500M"
    - name: "vcp-admin"
      script: "adminServer.js"
      watch: false
      max_memory_restart: "512M"

notifications:
  feishu: { enabled: false, app_id: "", app_secret: "", receiver_id: "" }
  wecom:  { enabled: false, webhook_url: "" }
  email:  { enabled: false, smtp_host: "", smtp_port: 587, user: "", password: "", to: "" }
```

- `repo_path` 必须指向已初始化的 Git 仓库（本地已有对应远程）。
- `pm2.processes` 为进程列表，每个进程至少需 `name` 与 `script`；未指定 `cwd` 时默认使用 `repo_path`。

### 3. 安装为 Windows 服务

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

### 4. CLI 命令

```powershell
# 手动触发单次更新
uv run python -m vcptoolbox_updater update

# 服务管理
uv run python -m vcptoolbox_updater install
uv run python -m vcptoolbox_updater start
uv run python -m vcptoolbox_updater stop
uv run python -m vcptoolbox_updater uninstall

# 启动 TUI 终端界面
uv run python -m vcptoolbox_updater.tui
# 或安装后直接运行
vcptoolbox-updater-tui
```

## 技术栈

| 功能 | 依赖 |
|:---|:---|
| Windows 服务 | `pywin32>=308` |
| 定时调度 | `APScheduler>=3.11.0` |
| Git 操作 | `subprocess` + 原生 `git` 命令 |
| 配置校验与解析 | `pydantic>=2.10.0`, `pydantic-settings>=2.7.0`, `pyyaml>=6.0.2` |
| 结构化日志 | `structlog>=24.4.0` |
| CLI | `click>=8.1.0` |
| TUI 终端界面 | `textual>=8.2.3` |
| 飞书通知 | `lark-oapi>=1.4.0` 官方 SDK |
| 企微通知 | `requests>=2.32.0` + Webhook |
| 邮件通知 | `smtplib` 标准库 |

## 注意事项

- **同步策略**：采用 `stash + reset --hard + reconcile` 的远程优先策略。本地 tracked 修改先 `git stash push`，然后 `git reset --hard` 硬同步到远程；若 reset 因 untracked 文件冲突而失败，则解析 stderr 冲突列表、删除冲突文件后重试一次。Apply stash 后，对 stash 中所有 **modified/deleted** 文件执行 `git checkout HEAD --` 回退到远程版本，仅保留 stash 中 **added** 的新文件。
- **日志**：CLI 模式下输出彩色控制台日志；Windows 服务模式下同时输出 JSON 格式文件日志（`RotatingFileHandler`）和 Windows EventLog（`NTEventLogHandler`）。
- **环境要求**：需要系统已安装 `git` 和 `pm2`，且 `pm2` 在系统 PATH 中可用。
- **权限**：Windows 服务安装与运行需要管理员权限。
- **敏感信息**：`config.yaml` 包含 `app_secret`、`password`、`webhook_url` 等敏感信息，请勿将其提交到版本控制。
