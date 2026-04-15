"""APScheduler-based background job scheduler."""

from __future__ import annotations

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from vcptoolbox_updater.utils import get_logger

logger = get_logger(__name__)


class UpdateScheduler:
    def __init__(self, interval_hours: float) -> None:
        self.scheduler = BackgroundScheduler()
        self.trigger = IntervalTrigger(hours=interval_hours)

    def add_job(self, func: callable) -> None:
        self.scheduler.add_job(func, self.trigger, id="auto_update", replace_existing=True)
        logger.info("scheduler_job_added", interval_hours=self.trigger.interval.total_seconds() / 3600)

    def start(self) -> None:
        self.scheduler.start()
        logger.info("scheduler_started")

    def shutdown(self, wait: bool = True) -> None:
        self.scheduler.shutdown(wait=wait)
        logger.info("scheduler_shutdown")
