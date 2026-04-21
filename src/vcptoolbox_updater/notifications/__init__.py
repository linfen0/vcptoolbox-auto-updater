"""Notification channel factory."""

from __future__ import annotations

from vcptoolbox_updater.config import NotificationConfig
from vcptoolbox_updater.notifications.base import NotificationChannel, UpdateReport


def build_notifiers(cfg: NotificationConfig) -> list[NotificationChannel]:
    channels: list[NotificationChannel] = []
    if cfg.feishu.enabled:
        from vcptoolbox_updater.notifications.feishu import FeishuNotifier

        channels.append(
            FeishuNotifier(
                app_id=cfg.feishu.app_id,
                app_secret=cfg.feishu.app_secret,
                receive_id=cfg.feishu.receive_id,
                receive_id_type=cfg.feishu.receive_id_type,
            )
        )
    if cfg.wecom.enabled:
        from vcptoolbox_updater.notifications.wecom import WeComNotifier

        channels.append(WeComNotifier(webhook_url=cfg.wecom.webhook_url))
    if cfg.email.enabled:
        from vcptoolbox_updater.notifications.email import EmailNotifier

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


def __getattr__(name: str):
    if name == "FeishuNotifier":
        from vcptoolbox_updater.notifications.feishu import FeishuNotifier

        return FeishuNotifier
    if name == "WeComNotifier":
        from vcptoolbox_updater.notifications.wecom import WeComNotifier

        return WeComNotifier
    if name == "EmailNotifier":
        from vcptoolbox_updater.notifications.email import EmailNotifier

        return EmailNotifier
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "NotificationChannel",
    "UpdateReport",
    "build_notifiers",
    "FeishuNotifier",
    "WeComNotifier",
    "EmailNotifier",
]
