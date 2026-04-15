"""WeCom (Enterprise WeChat) group robot notification via webhook."""

from __future__ import annotations

import json

import requests

from vcptoolbox_updater.notifications.base import NotificationChannel, UpdateReport
from vcptoolbox_updater.utils import get_logger

logger = get_logger(__name__)


class WeComNotifier(NotificationChannel):
    def __init__(self, webhook_url: str) -> None:
        self.webhook_url = webhook_url

    def send(self, report: UpdateReport) -> None:
        status_emoji = "✅" if report.success else "❌"
        content = (
            f"{status_emoji} VCPToolBox 自动更新报告\\n\\n"
            f"仓库路径: {report.repo_path}\\n"
            f"分支: {report.branch}\\n"
            f"代码更新: {report.from_commit} → {report.to_commit}\\n"
            f"PM2 进程: {report.pm2_process}\\n"
            f"结果: {'成功' if report.success else '失败'}\\n"
            f"详情: {report.message}"
        )

        payload = {"msgtype": "text", "text": {"content": content}}
        try:
            resp = requests.post(
                self.webhook_url,
                data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                timeout=30,
            )
            resp.raise_for_status()
            logger.info("wecom_notification_sent", response=resp.json())
        except Exception as exc:
            logger.error("wecom_notification_failed", error=str(exc))