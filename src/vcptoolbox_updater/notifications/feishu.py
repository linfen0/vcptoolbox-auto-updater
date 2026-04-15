"""Feishu (Lark) notification via official lark-oapi SDK."""

from __future__ import annotations

import json

import lark_oapi as lark
from lark_oapi.api.im.v1 import CreateMessageRequest, CreateMessageRequestBody, CreateMessageResponse

from vcptoolbox_updater.notifications.base import NotificationChannel, UpdateReport
from vcptoolbox_updater.utils import get_logger

logger = get_logger(__name__)


class FeishuNotifier(NotificationChannel):
    def __init__(self, app_id: str, app_secret: str, receive_id: str, receive_id_type: str = "open_id") -> None:
        self.client = (
            lark.Client.builder()
            .app_id(app_id)
            .app_secret(app_secret)
            .log_level(lark.LogLevel.INFO)
            .build()
        )
        self.receive_id = receive_id
        self.receive_id_type = receive_id_type

    def send(self, report: UpdateReport) -> None:
        status_emoji = "✅" if report.success else "❌"
        content = {
            "text": (
                f"{status_emoji} **VCPToolBox 自动更新报告**\\n\\n"
                f"• 仓库路径: `{report.repo_path}`\\n"
                f"• 分支: `{report.branch}`\\n"
                f"• 代码更新: `{report.from_commit}` → `{report.to_commit}`\\n"
                f"• PM2 进程: `{report.pm2_process}`\\n"
                f"• 结果: {'成功' if report.success else '失败'}\\n"
                f"• 详情: {report.message}"
            )
        }

        request = (
            CreateMessageRequest.builder()
            .receive_id_type(self.receive_id_type)
            .request_body(
                CreateMessageRequestBody.builder()
                .receive_id(self.receive_id)
                .msg_type("text")
                .content(json.dumps(content))
                .build()
            )
            .build()
        )

        response: CreateMessageResponse = self.client.im.v1.message.create(request)
        if not response.success():
            logger.error(
                "feishu_notification_failed",
                code=response.code,
                msg=response.msg,
                log_id=response.get_log_id(),
            )
        else:
            logger.info("feishu_notification_sent", message_id=response.data.message_id)