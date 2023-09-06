"""
Watchdog script.

It checks for failed scripts, and send alerts in case issues are detected. Optionally it can clone
failed scripts, typically workflow managers and other standalone scripts. Scripts handled by workflow managers
should not be retried here.

Spiders are handled by crawl managers, so they are not handled here.

Script configurable attributes:

MONITORED_SCRIPTS - A tuple containing all scripts to check (each one in the format "py:scriptname.py")
CLONE_SCRIPTS - A tuple containing all scripts that must be cloned in case of failed. This tuple must be
                a subset of MONITORED_SCRIPTS.


"""

import time
import abc
import logging
from typing import List, Tuple

from shub_workflow.script import JobKey, Outcome
from shub_workflow.utils.clone_job import BaseClonner


WATCHDOG_CHECKED_TAG = "WATCHDOG_CHECKED=True"
LOGGER = logging.getLogger(__name__)
LOGGER.setLevel(logging.INFO)


class WatchdogBaseScript(BaseClonner):

    MONITORED_SCRIPTS: Tuple[str, ...] = ()
    CLONE_SCRIPTS: Tuple[str, ...] = ()

    def __init__(self) -> None:
        super().__init__()
        self.failed_jobs: List[Tuple[str, JobKey, Outcome]] = []
        self.__notification_lines: List[str] = []

    def add_argparser_options(self):
        super().add_argparser_options()
        self.argparser.add_argument("period", help="How much go to past to check (in seconds)", type=int)

    def append_notification_line(self, line: str):
        self.__notification_lines.append(line)

    def get_notification_lines(self) -> List[str]:
        return self.__notification_lines

    def run(self) -> None:
        self.check_failed_scripts()
        self.close()

    def check_failed_scripts(self) -> None:
        now = time.time()
        for script in self.MONITORED_SCRIPTS:
            count = 0
            for job in self.get_jobs(
                spider=script,
                state=["finished"],
                meta=["finished_time", "close_reason"],
                lacks_tag=WATCHDOG_CHECKED_TAG,
            ):
                age = now - job["finished_time"] / 1000
                if age > self.args.period:
                    break
                count += 1
                if job["close_reason"] != "finished":
                    msg = (
                        f"Failed task: {script} (job: https://app.zyte.com/p/{job['key']}) "
                        f"(Reason: {job['close_reason']})"
                    )
                    LOGGER.error(msg)
                    new_job = None
                    if script in self.CLONE_SCRIPTS:
                        new_job = self.clone_job(job["key"])
                    if new_job is None:
                        self.append_notification_line(msg)
                self.add_job_tags(job["key"], tags=[WATCHDOG_CHECKED_TAG])
            LOGGER.info(f"Checked {count} {script} jobs")

    def close(self) -> None:
        if self.__notification_lines:
            self.send_alert()

    @abc.abstractmethod
    def send_alert(self):
        ...
