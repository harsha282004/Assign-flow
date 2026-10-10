import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useLateRequests } from '../../api/queries'
import type { RequestState } from '../../api/types'
import LateDecisionForm from '../../components/LateDecisionForm'
import { EmptyState, ErrorState, LoadingState, RequestBadge } from '../../components/ui'
import { formatIst } from '../../lib/time'

const FILTERS: { value: RequestState | 'ALL'; label: string }[] = [
  { value: 'PENDING', label: 'Pending' },
  { value: 'APPROVED', label: 'Approved (window open)' },
  { value: 'USED', label: 'Approved and used' },
  { value: 'EXPIRED', label: 'Window expired' },
  { value: 'REJECTED', label: 'Rejected' },
  { value: 'ALL', label: 'All' },
]

export default function LateRequests() {
  const [filter, setFilter] = useState<RequestState | 'ALL'>('PENDING')
  const { data, isPending, isError, error, refetch } = useLateRequests(filter, true)

  return (
    <>
      <h1>Late submission requests</h1>
      <p className="muted">
        Requests from students who missed a deadline on your assignments. Approving opens a limited
        submission window; the upload is still recorded as late.
      </p>
      <label className="inline">
        Show
        <select value={filter} onChange={(e) => setFilter(e.target.value as RequestState | 'ALL')}>
          {FILTERS.map((f) => (
            <option key={f.value} value={f.value}>
              {f.label}
            </option>
          ))}
        </select>
      </label>

      {isPending && <LoadingState label="Loading requests…" />}
      {isError && <ErrorState error={error} onRetry={() => void refetch()} />}
      {data && data.length === 0 && (
        <EmptyState title={filter === 'PENDING' ? 'No pending requests' : 'No requests here'}>
          {filter === 'PENDING'
            ? 'New late-submission requests from your students will appear here.'
            : 'Try another filter.'}
        </EmptyState>
      )}
      {data && data.length > 0 && (
        <ul className="cards">
          {data.map((r) => (
            <li key={r.id} className="card-item">
              <div className="row">
                <Link className="title" to={`/faculty/late-requests/${r.id}`}>
                  {r.student.full_name}
                </Link>
                <RequestBadge status={r.state} />
              </div>
              <p className="muted">
                {r.student.login_id} · {r.assignment.title} · {r.assignment.subject.code}{' '}
                {r.assignment.section.label}
              </p>
              <p className="muted small">
                Requested {formatIst(r.requested_at)} · deadline {formatIst(r.current_deadline)}
              </p>
              <p className="plain">{r.reason}</p>
              <LateDecisionForm request={r} />
            </li>
          ))}
        </ul>
      )}
    </>
  )
}
