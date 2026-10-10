import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useRoster } from '../api/queries'
import type { Timing } from '../api/types'
import { formatIst } from '../lib/time'
import { EmptyState, ErrorState, LoadingState, RequestBadge, ReviewBadge, TimingBadge } from './ui'

const FILTERS: { value: Timing | 'ALL'; label: string }[] = [
  { value: 'ALL', label: 'All' },
  { value: 'PENDING', label: 'Pending' },
  { value: 'ON_TIME', label: 'On time' },
  { value: 'LATE', label: 'Late' },
  { value: 'MISSING', label: 'Missing' },
]

/** Faculty view of the real submission records: one row per student expected for the assignment. */
export default function Roster({ assignmentId }: { assignmentId: string }) {
  const { data, isPending, isError, error, refetch } = useRoster(assignmentId, true)
  const [filter, setFilter] = useState<Timing | 'ALL'>('ALL')

  const rows = (data ?? []).filter((r) => filter === 'ALL' || r.timing === filter)
  const count = (t: Timing) => (data ?? []).filter((r) => r.timing === t).length

  return (
    <section className="card-item" aria-labelledby="roster-heading">
      <div className="row">
        <h2 id="roster-heading">Submissions</h2>
        {data && (
          <p className="muted small">
            {data.length} students · {count('ON_TIME')} on time · {count('LATE')} late ·{' '}
            {count('PENDING')} pending · {count('MISSING')} missing
          </p>
        )}
      </div>
      {isPending && <LoadingState label="Loading submissions…" />}
      {isError && <ErrorState error={error} onRetry={() => void refetch()} />}
      {data && (
        <>
          <label className="inline">
            Show
            <select value={filter} onChange={(e) => setFilter(e.target.value as Timing | 'ALL')}>
              {FILTERS.map((f) => (
                <option key={f.value} value={f.value}>
                  {f.label}
                </option>
              ))}
            </select>
          </label>
          {rows.length === 0 ? (
            <EmptyState title="No students match this filter" />
          ) : (
            <ul className="list roster">
              {rows.map((r) => (
                <li key={r.student.id}>
                  <span>
                    <Link to={`/faculty/assignments/${assignmentId}/students/${r.student.id}`}>
                      {r.student.full_name}
                    </Link>{' '}
                    <span className="muted">{r.student.login_id}</span>
                  </span>
                  <span className="roster-meta">
                    <TimingBadge timing={r.timing} lateApproved={r.late_approved} />
                    <RequestBadge status={r.request_status} />
                    {r.review_status !== 'NOT_REVIEWED' && <ReviewBadge status={r.review_status} />}
                    {r.is_resubmitted && <span className="badge status-draft">Resubmitted</span>}
                    <span className="muted small">
                      {r.version_count > 0
                        ? `${r.version_count} version${r.version_count === 1 ? '' : 's'} · ${formatIst(r.latest_uploaded_at!)}`
                        : 'No file'}
                    </span>
                  </span>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </section>
  )
}
