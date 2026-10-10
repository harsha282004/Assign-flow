from datetime import UTC, datetime, timedelta

from app.services.status import (
    Timing,
    is_resubmitted,
    no_submission_timing,
    submission_timing,
    version_timing,
)

D = datetime(2026, 10, 11, 12, 0, tzinfo=UTC)
SEC = timedelta(seconds=1)


def test_no_submission_is_pending_until_the_deadline_inclusive():
    assert no_submission_timing(D, D - SEC) == Timing.PENDING
    assert no_submission_timing(D, D) == Timing.PENDING  # exactly at the deadline
    assert no_submission_timing(D, D + SEC) == Timing.MISSING


def test_version_timing_boundaries():
    assert version_timing(D - SEC, D) == Timing.ON_TIME
    assert version_timing(D, D) == Timing.ON_TIME  # exactly at the deadline is on time
    assert version_timing(D + SEC, D) == Timing.LATE


def test_submission_timing_is_the_first_versions_timing():
    now = D + timedelta(days=5)
    assert submission_timing(D - timedelta(hours=1), D, now) == Timing.ON_TIME  # now is long past D, irrelevant
    assert submission_timing(D + timedelta(hours=1), D, now) == Timing.LATE
    assert submission_timing(None, D, D) == Timing.PENDING
    assert submission_timing(None, D, D + SEC) == Timing.MISSING


def test_extending_the_deadline_recomputes_against_the_current_deadline():
    first = D + timedelta(hours=1)  # uploaded after D (e.g. an approved late upload in a later phase)
    assert submission_timing(first, D, first) == Timing.LATE
    assert submission_timing(first, D + timedelta(hours=2), first) == Timing.ON_TIME


def test_resubmitted_flag():
    assert not is_resubmitted(0) and not is_resubmitted(1)
    assert is_resubmitted(2)
