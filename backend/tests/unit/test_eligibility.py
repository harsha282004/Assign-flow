"""Upload eligibility table (architecture §16.3), one test per implemented row."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.core.errors import AppError
from app.db.models import ReviewStatus, UploadContext
from app.services.eligibility import LateGrant, evaluate_upload, require_upload_allowed

D = datetime(2026, 10, 11, 12, 0, tzinfo=UTC)
SEC = timedelta(seconds=1)


def test_before_and_exactly_at_deadline_is_regular():
    assert evaluate_upload(D - SEC, D, None).context == UploadContext.REGULAR
    assert evaluate_upload(D, D, None).context == UploadContext.REGULAR


def test_after_deadline_without_a_revision_request_is_blocked():
    decision = evaluate_upload(D + SEC, D, None)
    assert not decision.allowed and decision.blocked_code == "DEADLINE_PASSED"
    assert evaluate_upload(D + SEC, D, ReviewStatus.UNDER_REVIEW).blocked_code == "DEADLINE_PASSED"


def test_accepted_submission_blocks_even_before_the_deadline():
    assert evaluate_upload(D - timedelta(days=1), D, ReviewStatus.ACCEPTED).blocked_code == "SUBMISSION_ACCEPTED"
    assert evaluate_upload(D + SEC, D, ReviewStatus.ACCEPTED).blocked_code == "SUBMISSION_ACCEPTED"


def test_revision_requested_allows_after_deadline_uploads():
    assert evaluate_upload(D + timedelta(days=3), D, ReviewStatus.REVISION_REQUESTED).context == UploadContext.REVISION
    # Before the deadline a revision request does not change the context.
    assert evaluate_upload(D - SEC, D, ReviewStatus.REVISION_REQUESTED).context == UploadContext.REGULAR


WS = D + timedelta(hours=2)
GRANT = LateGrant(request_id=uuid.uuid4(), window_start=WS, window_end=WS + timedelta(hours=24))


def test_approved_window_allows_late_approved_with_inclusive_ends():
    for moment in (GRANT.window_start, GRANT.window_start + SEC, GRANT.window_end):
        decision = evaluate_upload(moment, D, None, grant=GRANT)
        assert decision.context == UploadContext.LATE_APPROVED
        assert decision.late_request_id == GRANT.request_id


def test_outside_the_window_is_blocked():
    assert evaluate_upload(GRANT.window_end + SEC, D, None, grant=GRANT).blocked_code == "DEADLINE_PASSED"
    assert evaluate_upload(GRANT.window_start - SEC, D, None, grant=GRANT).blocked_code == "DEADLINE_PASSED"


def test_no_grant_means_no_late_upload():
    assert evaluate_upload(WS + SEC, D, None, grant=None).blocked_code == "DEADLINE_PASSED"


def test_window_does_not_apply_to_existing_regular_work():
    # Rule 6: a student who already submitted (not through this window) cannot use a late request to replace it.
    decision = evaluate_upload(WS + SEC, D, None, grant=GRANT, first_context=UploadContext.REGULAR)
    assert decision.blocked_code == "DEADLINE_PASSED"
    # Further uploads inside the same window are further LATE_APPROVED versions.
    again = evaluate_upload(WS + SEC, D, None, grant=GRANT, first_context=UploadContext.LATE_APPROVED)
    assert again.context == UploadContext.LATE_APPROVED


def test_rule_order_deadline_then_revision_then_window():
    # Rule 3 before 5: within an extended deadline the upload is REGULAR even inside a window.
    assert evaluate_upload(WS + SEC, WS + timedelta(hours=1), None, grant=GRANT).context == UploadContext.REGULAR
    # Rule 4 before 5.
    assert (
        evaluate_upload(WS + SEC, D, ReviewStatus.REVISION_REQUESTED, grant=GRANT).context == UploadContext.REVISION
    )
    # Rule 2 first of all: ACCEPTED blocks even inside an approved window.
    assert evaluate_upload(WS + SEC, D, ReviewStatus.ACCEPTED, grant=GRANT).blocked_code == "SUBMISSION_ACCEPTED"


@pytest.mark.parametrize(
    "received, review, code",
    [(D + SEC, None, "DEADLINE_PASSED"), (D, ReviewStatus.ACCEPTED, "SUBMISSION_ACCEPTED")],
)
def test_require_raises_409_with_the_code(received, review, code):
    with pytest.raises(AppError) as err:
        require_upload_allowed(received, D, review)
    assert (err.value.http_status, err.value.code) == (409, code)
