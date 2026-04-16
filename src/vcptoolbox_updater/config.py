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


class Pm2ProcessConfig(BaseSettings):
    name: str = Field(description="PM2 进程名称")
    script: str = Field(description="启动脚本路径")
    watch: bool = Field(default=False, description="是否启用 watch 模式")
    max_memory_restart: str | None = Field(default=None, description="最大内存限制")
    kill_timeout: int | None = Field(default=None, description="终止超时时间（毫秒）")
    cwd: str | None = Field(default=None, description="工作目录，默认使用 repo_path")
    args: list[str] | None = Field(default=None, description="传递给脚本的额外参数")
    env: dict[str, str] | None = Field(default=None, description="环境变量")
    instances: int | str | None = Field(default=None, description="实例数")
    exec_mode: str | None = Field(default=None, description="执行模式，如 cluster/fork")
    log_file: str | None = Field(default=None, description="日志文件路径")
    error_file: str | None = Field(default=None, description="错误日志文件路径")
    out_file: str | None = Field(default=None, description="标准输出日志文件路径")
    merge_logs: bool | None = Field(default=None, description="是否合并日志")
    autorestart: bool | None = Field(default=None, description="是否自动重启")
    min_uptime: str | None = Field(default=None, description="最小运行时间")
    max_restarts: int | None = Field(default=None, description="最大重启次数")
    restart_delay: int | None = Field(default=None, description="重启延迟（毫秒）")

    def to_ecosystem_dict(self) -> dict:
        """Convert this process config to a PM2 ecosystem app dict."""
        data = self.model_dump(exclude_none=True)
        if self.args:
            data["args"] = " ".join(self.args)
        return data


class Pm2Config(BaseSettings):
    pm2_bin: str | None = Field(default=None, description="PM2 可执行文件路径，默认从 PATH 查找")
    processes: list[Pm2ProcessConfig] = Field(description="PM2 进程配置列表")

    def to_ecosystem_dict(self) -> dict:
        """Convert all process configs to a single PM2 ecosystem dict."""
        return {"apps": [proc.to_ecosystem_dict() for proc in self.processes]}


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