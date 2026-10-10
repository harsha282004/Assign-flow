import { Bell, CalendarClock, CheckCircle2, MessageSquare, Upload, XCircle } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { Link } from 'react-router-dom'
import { useNotifications } from '../../api/queries'
import type { AppNotification } from '../../api/types'
import { relativeIst } from '../../lib/time'
import { ErrorState } from '../ui'

// Stored types: LATE_REQUEST_CREATED, LATE_REQUEST_DECIDED (title says approved / rejected), REVIEW_RECORDED, DEADLINE_CHANGED.
function iconFor(n: AppNotification): { icon: LucideIcon; tone: string } {
  const t = n.type.toUpperCase()
  if (t === 'LATE_REQUEST_DECIDED')
    return /reject/i.test(n.title)
      ? { icon: XCircle, tone: 'red' }
      : { icon: CheckCircle2, tone: 'blue' }
  if (t === 'LATE_REQUEST_CREATED') return { icon: Upload, tone: 'green' }
  if (t === 'REVIEW_RECORDED') return { icon: MessageSquare, tone: 'lavender' }
  if (t === 'DEADLINE_CHANGED') return { icon: CalendarClock, tone: 'yellow' }
  return { icon: Bell, tone: 'blue' }
}

function target(n: AppNotification, faculty: boolean): string | null {
  if (!n.ref_id) return null
  if (n.ref_type === 'LATE_REQUEST') return `/faculty/late-requests/${n.ref_id}`
  if (n.ref_type === 'ASSIGNMENT')
    return faculty ? `/faculty/assignments/${n.ref_id}` : `/student/assignments/${n.ref_id}`
  return null
}

/** Recent activity = the user's own stored notifications (GET /notifications), newest first. Nothing is invented. */
export default function ActivityPanel({
  faculty,
  viewAllTo,
  limit = 4,
  note,
}: {
  faculty: boolean
  viewAllTo?: string
  limit?: number
  note?: string
}) {
  const { data, isPending, isError, error, refetch } = useNotifications()
  return (
    <section className="dash-card" aria-labelledby="activity-h">
      <div className="dash-card-head">
        <h2 id="activity-h">Recent activity</h2>
        {viewAllTo && (
          <Link className="link-arrow" to={viewAllTo}>
            View all →
          </Link>
        )}
      </div>
      {note && <p className="muted small">{note}</p>}
      {isPending && <SkeletonRows rows={3} label="Loading activity…" />}
      {isError && <ErrorState error={error} onRetry={() => void refetch()} />}
      {data && data.items.length === 0 && (
        <div className="empty-soft">
          <Bell size={28} aria-hidden="true" />
          <strong>No activity yet</strong>
          <p className="muted small">
            Uploads, reviews, late-request decisions and deadline changes will show up here.
          </p>
        </div>
      )}
      {data && data.items.length > 0 && (
        <ul className="activity">
          {data.items.slice(0, limit).map((n) => {
            const { icon: Icon, tone } = iconFor(n)
            const to = target(n, faculty)
            return (
              <li key={n.id} className={n.read_at ? '' : 'unread'}>
                <span className={`activity-icon tone-${tone}`} aria-hidden="true">
                  <Icon size={18} />
                </span>
                <div>
                  <p className="activity-title">{to ? <Link to={to}>{n.title}</Link> : n.title}</p>
                  <p className="muted small plain">{n.body}</p>
                </div>
                <time className="muted small" dateTime={n.created_at}>
                  {relativeIst(n.created_at)}
                </time>
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}

export function SkeletonRows({ rows, label }: { rows: number; label: string }) {
  return (
    <div role="status" aria-label={label} className="skeleton-rows">
      {Array.from({ length: rows }, (_, i) => (
        <span key={i} className="skeleton skeleton-row" />
      ))}
    </div>
  )
}
