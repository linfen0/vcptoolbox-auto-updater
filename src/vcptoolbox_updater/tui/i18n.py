"""Lightweight i18n for TUI (Chinese localization)."""

from __future__ import annotations

_TRANSLATIONS: dict[str, str] = {
    # App / Common
    "app_name": "VCPToolBox Auto Updater",
    "footer_keys": "快捷键：Q=退出 │ D=切换主题 │ Esc=返回",
    "back": "⬅️ 返回",
    "status_ready": "就绪",
    "status_running": "执行中...",
    "status_done": "完成",
    "status_error": "错误",
    # Main Menu
    "menu_title": "📋 VCPToolBox 自动更新器",
    "menu_desc": "自动检测远程仓库更新，冲突时以远程为准，并自动重启本地 PM2 服务。",
    "menu_repo": "监控仓库",
    "menu_logs": "📜 查看运行日志",
    "menu_service": "⚙️ Windows 服务管理",
    "menu_update": "🚀 立即检查更新",
    "menu_quit": "❌ 退出程序",
    "workflow_title": "这个工具以 Windows 服务形态在后台运行",
    "workflow_step1": "① 定时检测 VCPToolBox 远程仓库更新（默认 24h）",
    "workflow_step2": "② 自动拉取合并远程更改，冲突时以远程版本为准",
    "workflow_step3": "③ 按 ecosystem 最佳实践自动重启 PM2 托管的 Node.js 服务",
    "workflow_step4": "④ 更新成功后发送通知（飞书 / 企微 / 邮件）",
    "hint_logs": "查看后台服务的运行日志",
    "hint_service": "安装、卸载、启动或停止 Windows 后台服务",
    "hint_update": "立即手动触发一次远程仓库检测与同步",
    "hint_quit": "关闭本终端界面",
    # Log Viewer
    "log_title": "📜 运行日志",
    "log_no_config": "[config.yaml 中未配置 log_file]",
    "log_not_found": "[日志文件不存在: {path}]",
    # Service Manager
    "service_title": "⚙️ Windows 服务管理",
    "service_install": "⬇️ 安装服务",
    "service_uninstall": "🗑️ 卸载服务",
    "service_start": "▶️ 启动服务",
    "service_stop": "⏹️ 停止服务",
    "service_result": "{action}: {output}",
    "service_succeeded": "{action} 成功",
    "service_failed": "{action} 失败",
    # Manual Update
    "update_title": "🚀 立即检查更新",
    "update_run": "▶️ 开始检查并更新",
    "update_hint": '点击"开始检查并更新"立即执行一次远程检测与同步。',
    "update_starting": "开始检查远程仓库并更新...",
    "update_success": "✅ 成功: {message}",
    "update_fail": "❌ 失败: {message}",
    # Feature introductions (from README)
    "feat_service": "🖥️ Windows 服务形态：开机自启，崩溃自动恢复",
    "feat_schedule": "⏰ 定时检测：默认每 24 小时检测一次远程提交",
    "feat_merge": "🔀 远程优先合并：冲突时以远程版本为准",
    "feat_pm2": "🚀 PM2 自动托管：按 ecosystem 最佳实践管理 Node.js 服务",
    "feat_notify": "📢 多通道通知：飞书、企业微信、邮件",
    "feat_cli": "⌨️ 手动更新 CLI / TUI：支持命令行与终端界面手动触发",
}


def _(key: str, **kwargs) -> str:
    text = _TRANSLATIONS.get(key, key)
    if kwargs:
        try:
            return text.format(**kwargs)
        except KeyError:
            pass
    return text
