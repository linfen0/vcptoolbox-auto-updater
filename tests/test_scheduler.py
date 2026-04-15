"""Unit tests for scheduler."""

from unittest.mock import MagicMock, patch

from vcptoolbox_updater.scheduler import UpdateScheduler


def test_scheduler_add_job():
    with patch("vcptoolbox_updater.scheduler.BackgroundScheduler") as mock_scheduler_cls:
        mock_scheduler = MagicMock()
        mock_scheduler_cls.return_value = mock_scheduler
        scheduler = UpdateScheduler(interval_hours=2.5)
        dummy_func = MagicMock()
        scheduler.add_job(dummy_func)
        mock_scheduler.add_job.assert_called_once_with(
            dummy_func, scheduler.trigger, id="auto_update", replace_existing=True
        )


def test_scheduler_start_shutdown():
    with patch("vcptoolbox_updater.scheduler.BackgroundScheduler") as mock_scheduler_cls:
        mock_scheduler = MagicMock()
        mock_scheduler_cls.return_value = mock_scheduler
        scheduler = UpdateScheduler(interval_hours=1.0)
        scheduler.start()
        mock_scheduler.start.assert_called_once()
        scheduler.shutdown(wait=True)
        mock_scheduler.shutdown.assert_called_once_with(wait=True)
