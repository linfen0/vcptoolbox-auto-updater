# VCPToolBox Auto Updater

7×24 小时自动检测 VCPToolBox 远程仓库更新，冲突时强制以远程版本覆盖本地，并自动重启 PM2 进程的 Windows 服务。

## 功能特性

- **Windows 服务形态**：开机自启，崩溃自动恢复
- **定时检测**：默认每 24 小时检测一次远程提交
- **远程优先合并**：自动将本地更改与远程合并，冲突时以远程版本为准（`git merge -X theirs origin/<branch>`）
- **PM2 自动托管**：更新成功后自动调用 `pm2 startOrRestart`，按配置启动或重启指定仓库内的所有 Node.js 服务
- **多通道通知**：飞书（官方 SDK）、企业微信（Webhook）、邮件（SMTP）
- **手动更新 CLI**：支持命令行手动触发单次更新

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
│       ├── utils.py
│       └── notifications/
│           ├── __init__.py
│           ├── base.py
│           ├── feishu.py
│           ├── wecom.py
│           └── email.py
└── tests/
```

## 快速开始

### 1. 使用UV安装

```powershell
uv sync
```

### 2. 配置

编辑 `config.yaml`，至少修改以下字段：

```yaml
git:
  repo_path: "F:/AI_Study_studio/VCPToolBox"
  remote_name: "origin"
  branch: "main"

pm2:
  processes:
    - name: "vcp-main"
      script: "server.js"
      watch: false
      max_memory_restart: "1500M"
      kill_timeout: 15000

    - name: "vcp-admin"
      script: "adminServer.js"
      watch: false
      max_memory_restart: "512M"
      kill_timeout: 5000
```

### 3. 安装为 Windows 服务

以管理员身份运行 PowerShell：

```powershell
.\\scripts\\install_service.ps1
```

### 4. CLI 命令

```powershell
# 手动触发单次更新
uv run python -m vcptoolbox_updater update

# 服务管理
uv run python -m vcptoolbox_updater start
uv run python -m vcptoolbox_updater stop
uv run python -m vcptoolbox_updater uninstall
```

## 技术栈

| 功能 | 选型 |
|:---|:---|
| Windows 服务 | `pywin32` |
| 定时调度 | `APScheduler` |
| Git 操作 | `subprocess` + 原生 `git` 命令 |
| 配置管理 | `pydantic-settings` + YAML |
| 结构化日志 | `structlog` |
| CLI | `click` |
| 飞书通知 | `lark-oapi` 官方 SDK |
| 企微通知 | `requests` + Webhook |
| 邮件通知 | `smtplib` 标准库 |

## 注意事项

- 冲突解决策略为 **merge preferring remote**，本地未提交的更改会先自动 commit 保留，然后再与远程合并
- 服务运行日志默认写入 Windows EventLog，可在 `config.yaml` 中配置 `log_file`
- 需要系统已安装 `git` 和 `pm2`，且 `pm2` 在系统 PATH 中可用