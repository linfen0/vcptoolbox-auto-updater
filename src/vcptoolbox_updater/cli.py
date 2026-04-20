"""CLI entry points: run as service, or trigger one-shot manual update."""

from __future__ import annotations

import os
import sys

import click

from vcptoolbox_updater.config import load_config
from vcptoolbox_updater.git_ops import GitOperator
from vcptoolbox_updater.update_report import UpdateReport
from vcptoolbox_updater.pm2_ops import Pm2Operator

from vcptoolbox_updater.utils import configure_logging, get_logger

logger = get_logger(__name__)


def _resolve_config_path(config: str | None) -> str:
    if config:
        return config
    if env_path := os.environ.get("VCPTOOLBOX_UPDATER_CONFIG"):
        return env_path
    return os.path.join(os.getcwd(), "config.yaml")


@click.group()
@click.option("--config", "-c", help="Path to config YAML file.")
@click.pass_context
def cli(ctx: click.Context, config: str | None) -> None:
    ctx.ensure_object(dict)
    ctx.obj["config_path"] = _resolve_config_path(config)


@cli.command()
@click.pass_context
def service(ctx: click.Context) -> None:
    """Run as a Windows service (used by SCM)."""
    from vcptoolbox_updater.service import AutoUpdaterService
    if len(sys.argv) == 1:
        import servicemanager
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(AutoUpdaterService)
        servicemanager.StartServiceCtrlDispatcher()
    else:
        import win32serviceutil
        win32serviceutil.HandleCommandLine(AutoUpdaterService)


@cli.command()
@click.pass_context
def install(ctx: click.Context) -> None:
    """Install the Windows service."""
    from vcptoolbox_updater.service import AutoUpdaterService
    import win32serviceutil
    win32serviceutil.HandleCommandLine(AutoUpdaterService, argv=["", "install"])


@cli.command()
@click.pass_context
def uninstall(ctx: click.Context) -> None:
    """Remove the Windows service."""
    from vcptoolbox_updater.service import AutoUpdaterService
    import win32serviceutil
    win32serviceutil.HandleCommandLine(AutoUpdaterService, argv=["", "remove"])


@cli.command()
@click.pass_context
def start(ctx: click.Context) -> None:
    """Start the Windows service."""
    from vcptoolbox_updater.service import AutoUpdaterService
    import win32serviceutil
    win32serviceutil.HandleCommandLine(AutoUpdaterService, argv=["", "start"])


@cli.command()
@click.pass_context
def stop(ctx: click.Context) -> None:
    """Stop the Windows service."""
    from vcptoolbox_updater.service import AutoUpdaterService
    import win32serviceutil
    win32serviceutil.HandleCommandLine(AutoUpdaterService, argv=["", "stop"])


def execute_update(config_path: str, service_mode: bool = False) -> UpdateReport:
    """Run a single update cycle and return the report."""
    cfg = load_config(config_path)
    configure_logging(cfg.log_level, str(cfg.log_file) if cfg.log_file else None, service_mode=service_mode)

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

    report: UpdateReport | None = None
    try:
        git_op.fetch()
        check_result = git_op.check_update_needed()
        if not check_result.updated:
            report = UpdateReport(
                success=True,
                repo_path=str(cfg.repo_path),
                branch=cfg.git.branch,
                from_commit=check_result.local_commit,
                to_commit=check_result.remote_commit,
                pm2_process=", ".join(p.name for p in cfg.pm2.processes),
                pm2_output="No restart needed.",
                message="No new commits on remote.",
            )
        else:
            pm2_op.kill()
            try:
                sync_result = git_op.pull_and_resolve_conflicts()
                pm2_output = pm2_op.restart(cwd=str(cfg.repo_path))
                report = UpdateReport(
                    success=True,
                    repo_path=str(cfg.repo_path),
                    branch=cfg.git.branch,
                    from_commit=sync_result.local_commit,
                    to_commit=sync_result.remote_commit,
                    pm2_process=", ".join(p.name for p in cfg.pm2.processes),
                    pm2_output=pm2_output,
                    message=sync_result.message,
                )
            except Exception as exc:
                report = UpdateReport(
                    success=False,
                    repo_path=str(cfg.repo_path),
                    branch=cfg.git.branch,
                    from_commit=check_result.local_commit,
                    to_commit=check_result.remote_commit,
                    pm2_process=", ".join(p.name for p in cfg.pm2.processes),
                    pm2_output="PM2 killed but update failed; service not restarted.",
                    message=f"Error after killing PM2: {exc}",
                )
    except Exception as exc:
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
        except Exception:
            pass

    return report


@cli.command()
@click.pass_context
def update(ctx: click.Context) -> None:
    """Manually trigger a single update cycle now."""
    config_path = ctx.obj["config_path"]
    report = execute_update(config_path)
    if report.success:
        if "Error:" in report.message:
            click.echo(report.message)
        else:
            click.echo(f"Update completed. {report.message}")
            click.echo(f"PM2: {report.pm2_output}")
    else:
        click.echo(f"Update failed: {report.message}", err=True)


def main() -> None:
    cli()


if __name__ == "__main__":
    main()