"""Faculty Submission Health Board (architecture §20.2 #13, FR-16). Every number is a SQL aggregation.

One CTE, `grid`, has exactly ONE row per (assignment, student of the section). Both the counts and the student list
are computed from it, so the counts can never disagree with the list, a student with several versions is counted
once, and `on_time + late + pending + missing = expected` holds by construction.

Scope: only PUBLISHED assignments the faculty member created AND teaches (the same rule as everywhere, §8.2).
Timing is the first version against the CURRENT deadline (Q1); the review is the latest review of the latest version.
"""

import uuid
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.models import User
from app.schemas.auth import SectionOut, SubjectOut
from app.schemas.late_requests import AssignmentRef
from app.schemas.overview import (
    AssignmentCounts,
    Counts,
    OverviewResponse,
    OverviewStudentRow,
    OverviewStudents,
)
from app.schemas.submissions import StudentRef
from app.services import scope

_GRID = """
WITH a AS (
  SELECT a.id, a.title, a.deadline, a.subject_id, a.section_id
  FROM assignments a
  JOIN teaching_assignments t
    ON t.subject_id = a.subject_id AND t.section_id = a.section_id AND t.faculty_id = :fid
  WHERE a.created_by = :fid AND a.status = 'PUBLISHED' {scope_filters}
), grid AS (
  SELECT a.id AS assignment_id, a.title, a.deadline, a.subject_id, a.section_id,
         u.id AS student_id, u.login_id, u.full_name,
         COALESCE(s.latest_version_no, 0) AS version_count,
         fv.upload_context::text AS first_ctx,
         CASE WHEN fv.uploaded_at IS NULL THEN (CASE WHEN :now <= a.deadline THEN 'PENDING' ELSE 'MISSING' END)
              WHEN fv.uploaded_at <= a.deadline THEN 'ON_TIME' ELSE 'LATE' END AS timing,
         (SELECT max(v.uploaded_at) FROM submission_versions v WHERE v.submission_id = s.id) AS last_at,
         COALESCE(rv.status::text, 'NOT_REVIEWED') AS review_status,
         CASE WHEN lr.id IS NULL THEN 'NONE'
              WHEN lr.status <> 'APPROVED' THEN lr.status::text
              WHEN EXISTS (SELECT 1 FROM submission_versions x WHERE x.late_request_id = lr.id) THEN 'USED'
              WHEN :now > lr.window_end THEN 'EXPIRED'
              ELSE 'APPROVED' END AS request_status
  FROM a
  JOIN student_profiles sp ON sp.section_id = a.section_id
  JOIN users u ON u.id = sp.user_id
  LEFT JOIN submissions s ON s.assignment_id = a.id AND s.student_id = u.id
  LEFT JOIN submission_versions fv ON fv.submission_id = s.id AND fv.version_no = 1
  LEFT JOIN LATERAL (
      SELECT r.status FROM reviews r
      JOIN submission_versions lv ON lv.id = r.version_id
      WHERE r.submission_id = s.id AND lv.version_no = s.latest_version_no
      ORDER BY r.reviewed_at DESC, r.id DESC LIMIT 1
  ) rv ON true
  LEFT JOIN late_requests lr ON lr.assignment_id = a.id AND lr.student_id = u.id
)
"""

_COUNTS = """
SELECT assignment_id,
  count(*) AS expected,
  count(*) FILTER (WHERE timing = 'ON_TIME') AS on_time,
  count(*) FILTER (WHERE timing = 'LATE') AS late,
  count(*) FILTER (WHERE timing = 'LATE' AND first_ctx = 'LATE_APPROVED') AS late_approved,
  count(*) FILTER (WHERE timing = 'PENDING') AS pending,
  count(*) FILTER (WHERE timing = 'MISSING') AS missing,
  count(*) FILTER (WHERE version_count > 0) AS submitted,
  count(*) FILTER (WHERE version_count > 1) AS resubmitted,
  count(*) FILTER (WHERE review_status = 'UNDER_REVIEW') AS under_review,
  count(*) FILTER (WHERE review_status = 'ACCEPTED') AS accepted,
  count(*) FILTER (WHERE review_status = 'REVISION_REQUESTED') AS revision_requested,
  count(*) FILTER (WHERE version_count > 0 AND review_status = 'NOT_REVIEWED') AS not_reviewed,
  count(*) FILTER (WHERE request_status = 'PENDING') AS requests_pending
FROM grid GROUP BY assignment_id
"""

COUNT_FIELDS = [
    "expected",
    "on_time",
    "late",
    "late_approved",
    "pending",
    "missing",
    "submitted",
    "resubmitted",
    "under_review",
    "accepted",
    "revision_requested",
    "not_reviewed",
    "requests_pending",
]


def _scope_filters(
    faculty: User,
    now: datetime,
    assignment_id: uuid.UUID | None,
    subject_id: uuid.UUID | None,
    section_id: uuid.UUID | None,
) -> tuple[str, dict]:
    params: dict = {"fid": faculty.id, "now": now}
    clause = ""
    for column, value, name in (
        ("a.id", assignment_id, "assignment_id"),
        ("a.subject_id", subject_id, "subject_id"),
        ("a.section_id", section_id, "section_id"),
    ):
        if value is not None:
            clause += f" AND {column} = :{name}"
            params[name] = value
    return clause, params


def _check_assignment(
    db: Session,
    faculty: User,
    assignment_id: uuid.UUID | None,
    subject_id: uuid.UUID | None = None,
    section_id: uuid.UUID | None = None,
) -> None:
    if assignment_id is not None:
        scope.get_faculty_assignment_or_404(db, faculty, assignment_id)  # 404 outside the faculty member's scope
    scope.require_filter_scope(db, faculty, subject_id, section_id)  # 403 for a subject / section I do not teach


def _with_reviewed(values: dict) -> Counts:
    return Counts(**values, reviewed=values["accepted"] + values["revision_requested"])


def _ref(row, prefix: str = "") -> AssignmentRef:
    return AssignmentRef(
        id=row[f"{prefix}id"],
        title=row["title"],
        subject=SubjectOut(id=row["sid"], code=row["code"], name=row["sname"]),
        section=SectionOut(id=row["cid"], label=row["label"], semester=row["semester"], name=row["cname"]),
    )


def overview(
    db: Session,
    faculty: User,
    now: datetime,
    assignment_id: uuid.UUID | None = None,
    subject_id: uuid.UUID | None = None,
    section_id: uuid.UUID | None = None,
) -> OverviewResponse:
    _check_assignment(db, faculty, assignment_id, subject_id, section_id)
    clause, params = _scope_filters(faculty, now, assignment_id, subject_id, section_id)
    rows = db.execute(text(_GRID.format(scope_filters=clause) + _COUNTS), params).mappings().all()
    counts = {r["assignment_id"]: {f: int(r[f]) for f in COUNT_FIELDS} for r in rows}
    if not counts:
        return OverviewResponse(totals=_with_reviewed({f: 0 for f in COUNT_FIELDS}), assignments=[])

    meta = (
        db.execute(
            text(
                "SELECT a.id, a.title, a.deadline, s.id AS sid, s.code, s.name AS sname, "
                "c.id AS cid, c.label, c.semester, c.name AS cname "
                "FROM assignments a JOIN subjects s ON s.id = a.subject_id JOIN sections c ON c.id = a.section_id "
                "WHERE a.id = ANY(:ids) ORDER BY a.deadline, a.id"
            ),
            {"ids": list(counts)},
        )
        .mappings()
        .all()
    )
    assignments = [
        AssignmentCounts(
            assignment=_ref(m), deadline=m["deadline"], **_with_reviewed(counts[m["id"]]).model_dump()
        )
        for m in meta
    ]
    totals = _with_reviewed({f: sum(c[f] for c in counts.values()) for f in COUNT_FIELDS})
    return OverviewResponse(totals=totals, assignments=assignments)


def students(
    db: Session,
    faculty: User,
    now: datetime,
    assignment_id: uuid.UUID | None = None,
    subject_id: uuid.UUID | None = None,
    section_id: uuid.UUID | None = None,
    timing: str | None = None,
    review_status: str | None = None,
    limit: int = 200,
) -> OverviewStudents:
    _check_assignment(db, faculty, assignment_id, subject_id, section_id)
    clause, params = _scope_filters(faculty, now, assignment_id, subject_id, section_id)
    where = "WHERE true"
    if timing:
        where += " AND g.timing = :timing"
        params["timing"] = timing
    if review_status:
        where += " AND g.review_status = :review_status"
        params["review_status"] = review_status
    base = _GRID.format(scope_filters=clause)
    total = db.execute(text(base + f"SELECT count(*) FROM grid g {where}"), params).scalar_one()
    rows = (
        db.execute(
            text(
                base
                + "SELECT g.*, g.assignment_id AS id, s.id AS sid, s.code, s.name AS sname, "
                "c.id AS cid, c.label, c.semester, c.name AS cname "
                f"FROM grid g JOIN subjects s ON s.id = g.subject_id JOIN sections c ON c.id = g.section_id {where} "
                "ORDER BY g.deadline, g.assignment_id, g.login_id LIMIT :limit"
            ),
            {**params, "limit": limit},
        )
        .mappings()
        .all()
    )
    items = [
        OverviewStudentRow(
            assignment=_ref(r),
            deadline=r["deadline"],
            student=StudentRef(id=r["student_id"], login_id=r["login_id"], full_name=r["full_name"]),
            timing=r["timing"],
            late_approved=r["timing"] == "LATE" and r["first_ctx"] == "LATE_APPROVED",
            is_resubmitted=r["version_count"] > 1,
            version_count=r["version_count"],
            latest_uploaded_at=r["last_at"],
            review_status=r["review_status"],
            request_status=r["request_status"],
        )
        for r in rows
    ]
    return OverviewStudents(total=total, items=items, truncated=total > len(items))
