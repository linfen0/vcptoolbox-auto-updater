"""Pydantic-based configuration with YAML support."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class GitConfig(BaseSettings):
    repo_path: Path = Field(description="本地仓库绝对路径")
    remote_name: str = Field(default="origin", description="远程仓库名称")
    branch: str = Field(default="main", description="目标分支")
    check_interval_hours: float = Field(default=24.0, ge=0.1, description="检查间隔小时数")


class Pm2Config(BaseSettings):
    process_name: str = Field(description="PM2 进程名称")
    pm2_bin: str | None = Field(default=None, description="PM2 可执行文件路径，默认从 PATH 查找")


class FeishuConfig(BaseSettings):
    enabled: bool = False
    app_id: str = ""
    app_secret: str = ""
    receive_id: str = ""
    receive_id_type: str = "open_id"


class WeComConfig(BaseSettings):
    enabled: bool = False
    webhook_url: str = ""


class EmailConfig(BaseSettings):
    enabled: bool = False
    smtp_host: str = ""
    smtp_port: int = 587
    username: str = ""
    password: str = ""
    to_addrs: list[str] = Field(default_factory=list)
    use_tls: bool = True


class NotificationConfig(BaseSettings):
    feishu: FeishuConfig = Field(default_factory=FeishuConfig)
    wecom: WeComConfig = Field(default_factory=WeComConfig)
    email: EmailConfig = Field(default_factory=EmailConfig)


class ServiceConfig(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    service_name: str = "VCPToolBoxAutoUpdater"
    display_name: str = "VCP ToolBox Auto Updater"
    description: str = "Automatically pulls VCPToolBox updates and restarts PM2 process."

    git: GitConfig
    pm2: Pm2Config
    notifications: NotificationConfig = Field(default_factory=NotificationConfig)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_file: Path | None = Field(default=None, description="日志文件路径，为空则只输出到 EventLog")

    @field_validator("log_file", mode="before")
    @classmethod
    def _expand_log_file(cls, v: str | None) -> Path | None:
        return Path(v).expanduser() if v else None


def load_config(path: Path) -> ServiceConfig:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return ServiceConfig(**raw)