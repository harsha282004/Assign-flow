"""Pure timing functions (no I/O). Architecture §15.2.

Let D be the assignment's *current* deadline.
* No submission: PENDING while now <= D (exactly at D is still PENDING), otherwise MISSING.
* A version uploaded at or before D is ON_TIME (exactly at D counts as ON_TIME), after D it is LATE.
* Submission-level timing (rosters, lists, counts) is the timing of the FIRST version [Q1]: later
  versions never change it. The RESUBMITTED flag is shown when more than one version exists.
"""

from datetime import datetime
from enum import StrEnum


class Timing(StrEnum):
    PENDING = "PENDING"
    ON_TIME = "ON_TIME"
    LATE = "LATE"
    MISSING = "MISSING"


def no_submission_timing(deadline: datetime, now: datetime) -> Timing:
    return Timing.PENDING if now <= deadline else Timing.MISSING


def version_timing(uploaded_at: datetime, deadline: datetime) -> Timing:
    """Timing of one version against a given deadline (the current one, or the snapshot at upload)."""
    return Timing.ON_TIME if uploaded_at <= deadline else Timing.LATE


def submission_timing(first_uploaded_at: datetime | None, deadline: datetime, now: datetime) -> Timing:
    """Submission-level timing: first version if there is one, otherwise PENDING / MISSING."""
    if first_uploaded_at is None:
        return no_submission_timing(deadline, now)
    return version_timing(first_uploaded_at, deadline)


def is_resubmitted(latest_version_no: int) -> bool:
    return latest_version_no > 1
