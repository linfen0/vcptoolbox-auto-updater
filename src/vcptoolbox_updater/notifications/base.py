"""Abstract notification channel."""

from __future__ import annotations

from abc import ABC, abstractmethod

from vcptoolbox_updater.update_report import UpdateReport


class NotificationChannel(ABC):
    @abstractmethod
    def send(self, report: UpdateReport) -> None:
        raise NotImplementedError