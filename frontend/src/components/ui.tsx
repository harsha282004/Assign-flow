import { useEffect, useState, type ReactNode } from 'react'
import { errorMessage } from '../api/client'
import type { AssignmentStatus, RequestStatus, ReviewStatus, Timing } from '../api/types'
import { remainingText } from '../lib/time'

export function Notice({
  kind,
  children,
}: {
  kind: 'success' | 'error' | 'info'
  children: ReactNode
}) {
  return (
    <p role={kind === 'error' ? 'alert' : 'status'} className={`notice ${kind}`}>
      {children}
    </p>
  )
}

export function LoadingState({ label = 'Loading…' }: { label?: string }) {
  return (
    <p className="center muted" role="status">
      {label}
    </p>
  )
}

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="empty">
      <strong>{title}</strong>
      {children && <p className="muted">{children}</p>}
    </div>
  )
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  return (
    <div className="empty" role="alert">
      <strong className="bad">Could not load this page</strong>
      <p className="muted">{errorMessage(error)}</p>
      {onRetry && (
        <button className="secondary" onClick={onRetry}>
          Try again
        </button>
      )}
    </div>
  )
}

const STATUS_LABELS: Record<AssignmentStatus, string> = {
  DRAFT: 'Draft',
  PUBLISHED: 'Published',
  ARCHIVED: 'Archived',
}
const TIMING_LABELS: Record<Timing, string> = {
  PENDING: 'Pending',
  ON_TIME: 'On time',
  LATE: 'Late',
  MISSING: 'Missing',
}

export function StatusBadge({ status }: { status: AssignmentStatus }) {
  return <span className={`badge status-${status.toLowerCase()}`}>{STATUS_LABELS[status]}</span>
}

/** `lateApproved` (from the API) turns "Late" into "Late (approved)": it is never shown as on time. */
export function TimingBadge({
  timing,
  lateApproved = false,
}: {
  timing: Timing | null
  lateApproved?: boolean
}) {
  if (!timing) return null
  const label = timing === 'LATE' && lateApproved ? 'Late (approved)' : TIMING_LABELS[timing]
  return <span className={`badge timing-${timing.toLowerCase()}`}>{label}</span>
}

const REVIEW_LABELS: Record<ReviewStatus, string> = {
  NOT_REVIEWED: 'Not reviewed',
  UNDER_REVIEW: 'Under review',
  ACCEPTED: 'Accepted',
  REVISION_REQUESTED: 'Revision requested',
}

export const reviewLabel = (status: ReviewStatus) => REVIEW_LABELS[status]

/** The review dimension, independent of timing: "Late" and "Accepted" can be shown together. */
export function ReviewBadge({ status }: { status: ReviewStatus }) {
  return <span className={`badge review-${status.toLowerCase()}`}>{REVIEW_LABELS[status]}</span>
}

const REQUEST_LABELS: Record<RequestStatus, string> = {
  NONE: 'No request',
  PENDING: 'Request pending',
  APPROVED: 'Request approved',
  REJECTED: 'Request rejected',
  EXPIRED: 'Window expired',
  USED: 'Late upload made',
}

export function RequestBadge({ status }: { status: RequestStatus }) {
  if (status === 'NONE') return null
  return <span className={`badge request-${status.toLowerCase()}`}>{REQUEST_LABELS[status]}</span>
}

/** Live countdown text. Display only: statuses always come from the server. */
export function Countdown({ iso }: { iso: string }) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 30_000)
    return () => clearInterval(timer)
  }, [])
  return <span className="muted">{remainingText(iso, now)}</span>
}
