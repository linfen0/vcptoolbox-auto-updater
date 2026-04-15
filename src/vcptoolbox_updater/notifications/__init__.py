"""Notification channel factory."""

from __future__ import annotations

from vcptoolbox_updater.config import NotificationConfig
from vcptoolbox_updater.notifications.base import NotificationChannel, UpdateReport
from vcptoolbox_updater.notifications.email import EmailNotifier
from vcptoolbox_updater.notifications.feishu import FeishuNotifier
from vcptoolbox_updater.notifications.wecom import WeComNotifier


def build_notifiers(cfg: NotificationConfig) -> list[NotificationChannel]:
    channels: list[NotificationChannel] = []
    if cfg.feishu.enabled:
        channels.append(
            FeishuNotifier(
                app_id=cfg.feishu.app_id,
                app_secret=cfg.feishu.app_secret,
                receive_id=cfg.feishu.receive_id,
                receive_id_type=cfg.feishu.receive_id_type,
            )
        )
    if cfg.wecom.enabled:
        channels.append(WeComNotifier(webhook_url=cfg.wecom.webhook_url))
    if cfg.email.enabled:
        channels.append(
            EmailNotifier(
                smtp_host=cfg.email.smtp_host,
                smtp_port=cfg.email.smtp_port,
                username=cfg.email.username,
                password=cfg.email.password,
                to_addrs=cfg.email.to_addrs,
                use_tls=cfg.email.use_tls,
            )
        )
    return channels


__all__ = [
    "NotificationChannel",
    "UpdateReport",
    "build_notifiers",
    "FeishuNotifier",
    "WeComNotifier",
    "EmailNotifier",
]