"""Windows Service implementation using pywin32."""

from __future__ import annotations

import os
import sys

import servicemanager
import win32event
import win32service
import win32serviceutil

from vcptoolbox_updater.config import load_config
from vcptoolbox_updater.git_ops import GitOperator
from vcptoolbox_updater.update_report import UpdateReport
from vcptoolbox_updater.pm2_ops import Pm2Operator
from vcptoolbox_updater.scheduler import UpdateScheduler
from vcptoolbox_updater.utils import configure_logging, get_logger

logger = get_logger(__name__)


class AutoUpdaterService(win32serviceutil.ServiceFramework):
    _svc_name_ = "VCPToolBoxAutoUpdater"
    _svc_display_name_ = "VCP ToolBox Auto Updater"
    _svc_description_ = "Automatically pulls VCPToolBox updates and restarts PM2 process."
    _exe_name_ = sys.executable
    _exe_args_ = "-m vcptoolbox_updater service"

    def __init__(self, args: list[str]) -> None:
        win32serviceutil.ServiceFramework.__init__(self, args)
        self.stop_event = win32event.CreateEvent(None, 0, 0, None)
        self.scheduler: UpdateScheduler | None = None
        self.config_path = self._resolve_config_path()
        self._running = False

    @staticmethod
    def _resolve_config_path() -> str:
        if env_path := os.environ.get("VCPTOOLBOX_UPDATER_CONFIG"):
            return env_path
        if getattr(sys, "frozen", False):
            base_dir = os.path.dirname(sys.executable)
        else:
            pkg_dir = os.path.dirname(os.path.abspath(__file__))
            parent = os.path.dirname(pkg_dir)
            # Editable install:  src/vcptoolbox_updater/ -> project root
            if os.path.basename(parent) == "src":
                base_dir = os.path.dirname(parent)
            else:
                # Installed wheel: use package directory
                base_dir = pkg_dir
        return os.path.join(base_dir, "config.yaml")

    def SvcStop(self) -> None:
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        win32event.SetEvent(self.stop_event)
        if self.scheduler:
            self.scheduler.shutdown(wait=True)
        self._running = False
        logger.info("service_stop_requested")

    def SvcDoRun(self) -> None:
        servicemanager.LogMsg(
            servicemanager.EVENTLOG_INFORMATION_TYPE,
            servicemanager.PYS_SERVICE_STARTED,
            (self._svc_name_, ""),
        )
        self._running = True
        try:
            self._run_main_loop()
        except Exception as exc:
            logger.exception("service_fatal_error", error=str(exc))
            raise

    def _run_main_loop(self) -> None:
        cfg = load_config(self.config_path)
        configure_logging(cfg.log_level, str(cfg.log_file) if cfg.log_file else None, service_mode=True)

        logger.info(
            "service_started",
            config_path=self.config_path,
            repo_path=str(cfg.repo_path),
            branch=cfg.git.branch,
        )

        git_op = GitOperator(
            repo_path=str(cfg.repo_path),
            remote_name=cfg.git.remote_name,
            branch=cfg.git.branch,
        )
        pm2_op = Pm2Operator(
            pm2_bin=cfg.pm2.pm2_bin,
            pm2_cfg=cfg.pm2,
        )
        from vcptoolbox_updater.notifications import build_notifiers

        notifiers = build_notifiers(cfg.notifications)

        def job() -> None:
            self._execute_update(git_op, pm2_op, notifiers, cfg)

        self.scheduler = UpdateScheduler(interval_hours=cfg.git.check_interval_hours)
        self.scheduler.add_job(job)
        self.scheduler.start()

        job()

        while self._running:
            rc = win32event.WaitForSingleObject(self.stop_event, 5000)
            if rc == win32event.WAIT_OBJECT_0:
                break

        servicemanager.LogMsg(
            servicemanager.EVENTLOG_INFORMATION_TYPE,
            servicemanager.PYS_SERVICE_STOPPED,
            (self._svc_name_, ""),
        )

    def _execute_update(
        self,
        git_op: GitOperator,
        pm2_op: Pm2Operator,
        notifiers: list,
        cfg,
    ) -> None:
        report: UpdateReport | None = None
        try:
            git_result = git_op.pull_and_resolve_conflicts()
            if not git_result.updated:
                logger.info("no_update_needed", local_commit=git_result.local_commit)
                report = UpdateReport(
                    success=True,
                    repo_path=str(cfg.repo_path),
                    branch=cfg.git.branch,
                    from_commit=git_result.local_commit,
                    to_commit=git_result.remote_commit,
                    pm2_process=", ".join(p.name for p in cfg.pm2.processes),
                    pm2_output="No restart needed.",
                    message="No new commits on remote.",
                )
            else:
                pm2_output = pm2_op.restart(cwd=str(cfg.repo_path))
                report = UpdateReport(
                    success=True,
                    repo_path=str(cfg.repo_path),
                    branch=cfg.git.branch,
                    from_commit=git_result.local_commit,
                    to_commit=git_result.remote_commit,
                    pm2_process=", ".join(p.name for p in cfg.pm2.processes),
                    pm2_output=pm2_output,
                    message=git_result.message,
                )
                logger.info("update_and_restart_completed", report=report)
        except Exception as exc:
            logger.exception("update_failed", error=str(exc))
            report = UpdateReport(
                success=False,
                repo_path=str(cfg.repo_path),
                branch=cfg.git.branch,
                from_commit="unknown",
                to_commit="unknown",
                pm2_process=", ".join(p.name for p in cfg.pm2.processes),
                pm2_output="",
                message=f"Error: {exc}",
            )

        for notifier in notifiers:
            try:
                notifier.send(report)
            except Exception as exc:
                logger.error("notification_failed", notifier=notifier.__class__.__name__, error=str(exc))