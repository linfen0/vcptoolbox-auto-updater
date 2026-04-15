"""SMTP email notification using Python standard library."""

from __future__ import annotations

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from vcptoolbox_updater.notifications.base import NotificationChannel, UpdateReport
from vcptoolbox_updater.utils import get_logger

logger = get_logger(__name__)


class EmailNotifier(NotificationChannel):
    def __init__(
        self,
        smtp_host: str,
        smtp_port: int,
        username: str,
        password: str,
        to_addrs: list[str],
        use_tls: bool = True,
    ) -> None:
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.username = username
        self.password = password
        self.to_addrs = to_addrs
        self.use_tls = use_tls

    def send(self, report: UpdateReport) -> None:
        subject = f"{'[成功]' if report.success else '[失败]'} VCPToolBox 自动更新报告"
        body_html = f"""\
<html>
<body>
  <h2>{'✅ 更新成功' if report.success else '❌ 更新失败'}</h2>
  <table border="1" cellpadding="8" cellspacing="0">
    <tr><td><b>仓库路径</b></td><td>{report.repo_path}</td></tr>
    <tr><td><b>分支</b></td><td>{report.branch}</td></tr>
    <tr><td><b>代码更新</b></td><td>{report.from_commit} → {report.to_commit}</td></tr>
    <tr><td><b>PM2 进程</b></td><td>{report.pm2_process}</td></tr>
    <tr><td><b>详情</b></td><td>{report.message}</td></tr>
  </table>
</body>
</html>
"""

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self.username
        msg["To"] = ", ".join(self.to_addrs)
        msg.attach(MIMEText(body_html, "html", "utf-8"))

        try:
            with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=30) as server:
                if self.use_tls:
                    server.starttls()
                server.login(self.username, self.password)
                server.sendmail(self.username, self.to_addrs, msg.as_string())
            logger.info("email_notification_sent", to=self.to_addrs)
        except Exception as exc:
            logger.error("email_notification_failed", error=str(exc))