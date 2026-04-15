"""Unit tests for notification channels."""

from unittest.mock import MagicMock, patch

from vcptoolbox_updater.config import EmailConfig, FeishuConfig, NotificationConfig, WeComConfig
from vcptoolbox_updater.notifications import (
    EmailNotifier,
    FeishuNotifier,
    UpdateReport,
    WeComNotifier,
    build_notifiers,
)


def test_build_notifiers_empty():
    cfg = NotificationConfig()
    assert build_notifiers(cfg) == []


def test_build_notifiers_feishu():
    cfg = NotificationConfig(
        feishu=FeishuConfig(enabled=True, app_id="id", app_secret="sec", receive_id="rid")
    )
    notifiers = build_notifiers(cfg)
    assert len(notifiers) == 1
    assert isinstance(notifiers[0], FeishuNotifier)


def test_build_notifiers_wecom():
    cfg = NotificationConfig(
        wecom=WeComConfig(enabled=True, webhook_url="http://example.com/webhook")
    )
    notifiers = build_notifiers(cfg)
    assert len(notifiers) == 1
    assert isinstance(notifiers[0], WeComNotifier)


def test_build_notifiers_email():
    cfg = NotificationConfig(
        email=EmailConfig(
            enabled=True,
            smtp_host="smtp.example.com",
            smtp_port=587,
            username="bot@example.com",
            password="pass",
            to_addrs=["admin@example.com"],
        )
    )
    notifiers = build_notifiers(cfg)
    assert len(notifiers) == 1
    assert isinstance(notifiers[0], EmailNotifier)


def test_wecom_notifier_send_success():
    notifier = WeComNotifier("http://example.com/webhook")
    report = UpdateReport(
        success=True,
        repo_path="/tmp/repo",
        branch="main",
        from_commit="a",
        to_commit="b",
        pm2_process="app",
        pm2_output="ok",
        message="done",
    )
    with patch("vcptoolbox_updater.notifications.wecom.requests.post") as mock_post:
        mock_post.return_value = MagicMock(json=MagicMock(return_value={"errcode": 0}))
        notifier.send(report)
        mock_post.assert_called_once()


def test_wecom_notifier_send_failure():
    notifier = WeComNotifier("http://example.com/webhook")
    report = UpdateReport(
        success=False,
        repo_path="/tmp/repo",
        branch="main",
        from_commit="a",
        to_commit="b",
        pm2_process="app",
        pm2_output="",
        message="error",
    )
    with patch("vcptoolbox_updater.notifications.wecom.requests.post") as mock_post:
        mock_post.side_effect = RuntimeError("connection failed")
        notifier.send(report)
        mock_post.assert_called_once()


def test_email_notifier_send_success():
    notifier = EmailNotifier(
        smtp_host="smtp.example.com",
        smtp_port=587,
        username="bot@example.com",
        password="pass",
        to_addrs=["admin@example.com"],
    )
    report = UpdateReport(
        success=True,
        repo_path="/tmp/repo",
        branch="main",
        from_commit="a",
        to_commit="b",
        pm2_process="app",
        pm2_output="ok",
        message="done",
    )
    with patch("vcptoolbox_updater.notifications.email.smtplib.SMTP") as mock_smtp_cls:
        mock_server = MagicMock()
        mock_smtp_cls.return_value.__enter__ = MagicMock(return_value=mock_server)
        mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)
        notifier.send(report)
        mock_smtp_cls.assert_called_once_with("smtp.example.com", 587, timeout=30)
        mock_server.starttls.assert_called_once()
        mock_server.login.assert_called_once_with("bot@example.com", "pass")
        mock_server.sendmail.assert_called_once()


def test_email_notifier_send_failure():
    notifier = EmailNotifier(
        smtp_host="smtp.example.com",
        smtp_port=587,
        username="bot@example.com",
        password="pass",
        to_addrs=["admin@example.com"],
    )
    report = UpdateReport(
        success=False,
        repo_path="/tmp/repo",
        branch="main",
        from_commit="a",
        to_commit="b",
        pm2_process="app",
        pm2_output="",
        message="error",
    )
    with patch("vcptoolbox_updater.notifications.email.smtplib.SMTP") as mock_smtp_cls:
        mock_smtp_cls.side_effect = RuntimeError("SMTP error")
        notifier.send(report)


def test_feishu_notifier_send_success():
    notifier = FeishuNotifier("app_id", "app_secret", "receive_id")
    report = UpdateReport(
        success=True,
        repo_path="/tmp/repo",
        branch="main",
        from_commit="a",
        to_commit="b",
        pm2_process="app",
        pm2_output="ok",
        message="done",
    )
    mock_response = MagicMock()
    mock_response.success.return_value = True
    mock_response.data.message_id = "msg_123"
    with patch.object(notifier.client.im.v1.message, "create", return_value=mock_response):
        notifier.send(report)


def test_feishu_notifier_send_failure():
    notifier = FeishuNotifier("app_id", "app_secret", "receive_id")
    report = UpdateReport(
        success=False,
        repo_path="/tmp/repo",
        branch="main",
        from_commit="a",
        to_commit="b",
        pm2_process="app",
        pm2_output="",
        message="error",
    )
    mock_response = MagicMock()
    mock_response.success.return_value = False
    mock_response.code = 400
    mock_response.msg = "bad request"
    mock_response.get_log_id.return_value = "log_123"
    with patch.object(notifier.client.im.v1.message, "create", return_value=mock_response):
        notifier.send(report)
