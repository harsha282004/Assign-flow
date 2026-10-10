import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useFacultyAssignments, useOverview, useOverviewStudents } from '../../api/queries'
import type { Counts, OverviewFilters, ReviewStatus, ScopeFilter, Timing } from '../../api/types'
import { useAuth } from '../../auth/useAuth'
import ScopeFilters from '../../components/ScopeFilters'
import {
  EmptyState,
  ErrorState,
  LoadingState,
  RequestBadge,
  ReviewBadge,
  TimingBadge,
} from '../../components/ui'
import { formatIst } from '../../lib/time'

const TIMINGS: { value: Timing; label: string; key: keyof Counts }[] = [
  { value: 'ON_TIME', label: 'On time', key: 'on_time' },
  { value: 'LATE', label: 'Late', key: 'late' },
  { value: 'PENDING', label: 'Pending', key: 'pending' },
  { value: 'MISSING', label: 'Missing', key: 'missing' },
]

const REVIEWS: { value: ReviewStatus; label: string }[] = [
  { value: 'NOT_REVIEWED', label: 'Not reviewed' },
  { value: 'UNDER_REVIEW', label: 'Under review' },
  { value: 'ACCEPTED', label: 'Accepted' },
  { value: 'REVISION_REQUESTED', label: 'Revision requested' },
]

function Card({
  label,
  value,
  note,
  active,
  onClick,
}: {
  label: string
  value: number
  note?: string
  active?: boolean
  onClick?: () => void
}) {
  const body = (
    <>
      <span className="card-value">{value}</span>
      <span className="card-label">{label}</span>
      {note && <span className="muted small">{note}</span>}
    </>
  )
  return onClick ? (
    <button
      className={`stat clickable ${active ? 'active' : ''}`}
      aria-pressed={active}
      onClick={onClick}
    >
      {body}
    </button>
  ) : (
    <div className="stat">{body}</div>
  )
}

/** Faculty Submission Health Board: every number comes from SQL aggregation on the server. */
export default function HealthBoard() {
  const [assignmentId, setAssignmentId] = useState('')
  const [filter, setFilter] = useState<ScopeFilter>({})
  const { state } = useAuth()
  const [timing, setTiming] = useState<Timing | ''>('')
  const [review, setReview] = useState<ReviewStatus | ''>('')

  const assignments = useFacultyAssignments()
  const published = useMemo(
    () =>
      (assignments.data ?? []).filter(
        (a) =>
          a.status === 'PUBLISHED' &&
          (!filter.subject_id || a.subject.id === filter.subject_id) &&
          (!filter.section_id || a.section.id === filter.section_id),
      ),
    [assignments.data, filter.subject_id, filter.section_id],
  )
  // An assignment chosen earlier that no longer matches the subject / section filter is ignored.
  const activeAssignment = published.some((a) => a.id === assignmentId) ? assignmentId : ''

  const scope: OverviewFilters = {
    ...(activeAssignment ? { assignment_id: activeAssignment } : {}),
    ...(filter.subject_id ? { subject_id: filter.subject_id } : {}),
    ...(filter.section_id ? { section_id: filter.section_id } : {}),
  }
  const listFilters: OverviewFilters = {
    ...scope,
    ...(timing ? { timing } : {}),
    ...(review ? { review_status: review } : {}),
  }

  const overview = useOverview(scope)
  const students = useOverviewStudents(listFilters)

  const ov = overview.data
  const totals = ov?.totals

  return (
    <>
      <h1>Submission health board</h1>
      <p className="muted">
        Counts are per student (never per file) for your published assignments. A student is in
        exactly one of on time, late, pending or missing.
      </p>

      <ScopeFilters
        teaching={state.status === 'authenticated' ? (state.me.teaching ?? []) : []}
        filter={filter}
        onChange={setFilter}
      >
        <label>
          Assignment
          <select value={activeAssignment} onChange={(e) => setAssignmentId(e.target.value)}>
            <option value="">All assignments</option>
            {published.map((a) => (
              <option key={a.id} value={a.id}>
                {a.title}
              </option>
            ))}
          </select>
        </label>
        <label>
          Review
          <select value={review} onChange={(e) => setReview(e.target.value as ReviewStatus | '')}>
            <option value="">Any review status</option>
            {REVIEWS.map((r) => (
              <option key={r.value} value={r.value}>
                {r.label}
              </option>
            ))}
          </select>
        </label>
      </ScopeFilters>

      {overview.isPending && <LoadingState label="Loading counts…" />}
      {overview.isError && (
        <ErrorState error={overview.error} onRetry={() => void overview.refetch()} />
      )}
      {ov && ov.assignments.length === 0 && (
        <EmptyState title="Nothing to count yet">
          Publish an assignment, or loosen the filters, to see submission counts here.
        </EmptyState>
      )}

      {ov && totals && ov.assignments.length > 0 && (
        <>
          <div className="stats" aria-label="Totals">
            <Card label="Students expected" value={totals.expected} />
            {TIMINGS.map((t) => (
              <Card
                key={t.value}
                label={t.label}
                value={totals[t.key]}
                note={t.value === 'LATE' ? `${totals.late_approved} approved` : undefined}
                active={timing === t.value}
                onClick={() => setTiming(timing === t.value ? '' : t.value)}
              />
            ))}
            <Card label="Resubmitted" value={totals.resubmitted} />
            <Card label="Requests awaiting decision" value={totals.requests_pending} />
            <Card
              label="Reviewed"
              value={totals.reviewed}
              note={`${totals.accepted} accepted · ${totals.revision_requested} revision`}
            />
            <Card label="Under review" value={totals.under_review} />
            <Card label="Awaiting review" value={totals.not_reviewed} />
          </div>

          <section className="card-item" aria-labelledby="by-assignment">
            <h2 id="by-assignment">By assignment</h2>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Assignment</th>
                    <th>Expected</th>
                    <th>On time</th>
                    <th>Late</th>
                    <th>Pending</th>
                    <th>Missing</th>
                    <th>Requests</th>
                  </tr>
                </thead>
                <tbody>
                  {ov.assignments.map((a) => (
                    <tr key={a.assignment.id}>
                      <td>
                        <Link to={`/faculty/assignments/${a.assignment.id}`}>
                          {a.assignment.title}
                        </Link>
                        <br />
                        <span className="muted small">
                          {a.assignment.subject.code} {a.assignment.section.label} · due{' '}
                          {formatIst(a.deadline)}
                        </span>
                      </td>
                      <td>{a.expected}</td>
                      <td>{a.on_time}</td>
                      <td>
                        {a.late}
                        {a.late_approved > 0 && (
                          <span className="muted small"> ({a.late_approved} approved)</span>
                        )}
                      </td>
                      <td>{a.pending}</td>
                      <td>{a.missing}</td>
                      <td>{a.requests_pending}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}

      <section className="card-item" aria-labelledby="students-heading">
        <div className="row">
          <h2 id="students-heading">Students</h2>
          <label className="inline">
            Timing
            <select value={timing} onChange={(e) => setTiming(e.target.value as Timing | '')}>
              <option value="">Any</option>
              {TIMINGS.map((t) => (
                <option key={t.value} value={t.value}>
                  {t.label}
                </option>
              ))}
            </select>
          </label>
        </div>
        {students.isPending && <LoadingState label="Loading students…" />}
        {students.isError && (
          <ErrorState error={students.error} onRetry={() => void students.refetch()} />
        )}
        {students.data && students.data.items.length === 0 && (
          <EmptyState title="No students match these filters" />
        )}
        {students.data && students.data.items.length > 0 && (
          <>
            <p className="muted small">
              {students.data.total} student{students.data.total === 1 ? '' : 's'}
              {students.data.truncated ? ` (showing the first ${students.data.items.length})` : ''}
            </p>
            <ul className="list roster">
              {students.data.items.map((r) => (
                <li key={`${r.assignment.id}-${r.student.id}`}>
                  <span>
                    <Link to={`/faculty/assignments/${r.assignment.id}/students/${r.student.id}`}>
                      {r.student.full_name}
                    </Link>{' '}
                    <span className="muted">
                      {r.student.login_id} · {r.assignment.title}
                    </span>
                  </span>
                  <span className="roster-meta">
                    <TimingBadge timing={r.timing} lateApproved={r.late_approved} />
                    <RequestBadge status={r.request_status} />
                    {r.review_status !== 'NOT_REVIEWED' && <ReviewBadge status={r.review_status} />}
                    {r.is_resubmitted && <span className="badge status-draft">Resubmitted</span>}
                  </span>
                </li>
              ))}
            </ul>
          </>
        )}
      </section>
    </>
  )
}
