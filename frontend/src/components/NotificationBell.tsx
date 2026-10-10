import { Bell } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  useMarkAllNotificationsRead,
  useMarkNotificationRead,
  useNotifications,
  useUnreadCount,
} from '../api/queries'
import type { AppNotification } from '../api/types'
import { formatIst } from '../lib/time'
import { ErrorState, LoadingState } from './ui'

function target(n: AppNotification): string | null {
  if (!n.ref_id) return null
  if (n.ref_type === 'SUBMISSION') return `/faculty/submissions/${n.ref_id}`
  if (n.ref_type === 'LATE_REQUEST') return `/faculty/late-requests/${n.ref_id}`
  if (n.ref_type === 'ASSIGNMENT') return `/student/assignments/${n.ref_id}`
  return null
}

/** Bell with the unread count, the computed "Needs attention" alerts and the stored notifications. */
export default function NotificationBell() {
  const [open, setOpen] = useState(false)
  // The badge uses the cheap count endpoint; the full list is fetched only while the panel is open.
  const { data, isPending, isError, error, refetch } = useNotifications(open)
  const markRead = useMarkNotificationRead()
  const markAll = useMarkAllNotificationsRead()
  const unread = useUnreadCount().data ?? 0
  // A new notification while the panel is open refreshes the list as well as the badge.
  useEffect(() => {
    if (open) void refetch()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [unread])

  function open_(n: AppNotification) {
    if (!n.read_at) markRead.mutate(n.id)
    setOpen(false)
  }

  return (
    <div className="bell">
      <button
        className="secondary bell-btn"
        aria-expanded={open}
        aria-controls="notification-panel"
        onClick={() => setOpen((v) => !v)}
      >
        <Bell size={20} aria-hidden="true" />
        <span className="sr-only">Notifications</span>
        {unread > 0 && (
          <span className="nav-count bell-count" aria-label={`${unread} unread notifications`}>
            {unread > 9 ? '9+' : unread}
          </span>
        )}
      </button>
      {open && (
        <div
          id="notification-panel"
          className="bell-panel"
          role="region"
          aria-label="Notifications"
        >
          {isPending && <LoadingState label="Loading notifications…" />}
          {isError && <ErrorState error={error} onRetry={() => void refetch()} />}
          {data && (
            <>
              {data.alerts.length > 0 && (
                <>
                  <h2>Needs attention</h2>
                  <ul className="notes">
                    {data.alerts.map((a) => (
                      <li
                        key={`${a.type}-${a.assignment_id}`}
                        className={`alert-${a.type.toLowerCase()}`}
                      >
                        <Link
                          to={`/student/assignments/${a.assignment_id}`}
                          onClick={() => setOpen(false)}
                        >
                          {a.message}
                        </Link>
                        <span className="muted small">{formatIst(a.at)}</span>
                      </li>
                    ))}
                  </ul>
                </>
              )}
              <div className="note-head">
                <h2>Notifications</h2>
                {unread > 0 && (
                  <button
                    className="secondary compact"
                    disabled={markAll.isPending}
                    onClick={() => markAll.mutate()}
                  >
                    Mark all as read
                  </button>
                )}
              </div>
              {data.items.length === 0 ? (
                <p className="muted">You're all caught up.</p>
              ) : (
                <ul className="notes">
                  {data.items.map((n) => {
                    const to = target(n)
                    return (
                      <li key={n.id} className={n.read_at ? 'read' : 'unread'}>
                        <strong>{n.title}</strong>
                        <span className="plain">{n.body}</span>
                        <span className="muted small">{formatIst(n.created_at)}</span>
                        <span className="note-actions">
                          {to && (
                            <Link to={to} onClick={() => open_(n)}>
                              {n.ref_type === 'SUBMISSION' ? 'Open submission' : 'Open'}
                            </Link>
                          )}
                          {!n.read_at && (
                            <button
                              className="secondary"
                              disabled={markRead.isPending}
                              onClick={() => markRead.mutate(n.id)}
                            >
                              Mark as read
                            </button>
                          )}
                        </span>
                      </li>
                    )
                  })}
                </ul>
              )}
              {markAll.isError && (
                <p className="bad small">Could not mark all as read. Try again.</p>
              )}
              {markRead.isError && (
                <p className="bad small">Could not mark it as read. Try again.</p>
              )}
            </>
          )}
        </div>
      )}
    </div>
  )
}
