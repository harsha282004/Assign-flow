import { Link } from 'react-router-dom'
import { useNotifications, useStudentArchived, useStudentAssignments } from '../../api/queries'
import type { StudentAssignmentItem } from '../../api/types'
import { SkeletonRows } from '../../components/dash/ActivityPanel'
import { EmptyState, ErrorState } from '../../components/ui'
import { formatIst } from '../../lib/time'
import { AssignmentRows } from './Dashboard'

export type CollectionMode = 'assignments' | 'submissions' | 'late-requests'

const CONFIG: Record<
  CollectionMode,
  {
    title: string
    subtitle: string
    empty: string
    emptyBody: string
    filter: (a: StudentAssignmentItem) => boolean
  }
> = {
  assignments: {
    title: 'My assignments',
    subtitle: 'Everything published for your class.',
    empty: 'No assignments yet',
    emptyBody: 'Assignments from your teachers will appear here once they are published.',
    filter: () => true,
  },
  submissions: {
    title: 'My submissions',
    subtitle: 'Assignments you have uploaded work for. Open one to see every version.',
    empty: 'No submissions yet',
    emptyBody: 'Upload work from an assignment page and it will be listed here.',
    filter: (a) => a.timing === 'ON_TIME' || a.timing === 'LATE',
  },
  'late-requests': {
    title: 'My late requests',
    subtitle: 'Assignments for which you asked to submit late, with the decision so far.',
    empty: 'No late requests',
    emptyBody: 'If you miss a deadline you can request to submit late from the assignment page.',
    filter: (a) => a.request_status !== 'NONE',
  },
}

/** Assignments, Submissions and Late requests are three views of GET /student/assignments. */
export function StudentCollection({ mode }: { mode: CollectionMode }) {
  const cfg = CONFIG[mode]
  const { data, isPending, isError, error, refetch } = useStudentAssignments()
  const archived = useStudentArchived()
  // Archived assignments leave the active list, but the student's own submissions and late requests stay visible.
  const items = [...(data ?? []), ...(mode === 'assignments' ? [] : (archived.data ?? []))].filter(
    cfg.filter,
  )
  const archivedItems = mode === 'assignments' ? (archived.data ?? []) : []

  return (
    <div className="dashboard">
      <div className="dash-head">
        <div>
          <h1>{cfg.title}</h1>
          <p className="muted">{cfg.subtitle}</p>
        </div>
      </div>
      <section className="dash-card">
        {isPending && <SkeletonRows rows={5} label="Loading…" />}
        {isError && <ErrorState error={error} onRetry={() => void refetch()} />}
        {data && items.length === 0 && <EmptyState title={cfg.empty}>{cfg.emptyBody}</EmptyState>}
        {items.length > 0 && <AssignmentRows items={items} />}
      </section>
      {archivedItems.length > 0 && (
        <section className="dash-card" aria-labelledby="archived-h">
          <div className="dash-card-head">
            <h2 id="archived-h">Archived assignments</h2>
          </div>
          <p className="muted small">
            Your teacher archived these. They no longer accept work, but your submissions, feedback
            and files are kept and can still be opened.
          </p>
          <AssignmentRows items={archivedItems} />
        </section>
      )}
    </div>
  )
}

/**
 * The student's activity history: the stored notifications (GET /notifications). Each assignment page keeps the
 * complete, ordered timeline of that assignment.
 */
export function StudentTimeline() {
  const { data, isPending, isError, error, refetch } = useNotifications()
  return (
    <div className="dashboard">
      <div className="dash-head">
        <div>
          <h1>Timeline</h1>
          <p className="muted">
            Your recent activity, newest first. Open an assignment for its full integrity timeline.
          </p>
        </div>
      </div>
      <section className="dash-card">
        {isPending && <SkeletonRows rows={5} label="Loading activity…" />}
        {isError && <ErrorState error={error} onRetry={() => void refetch()} />}
        {data && data.items.length === 0 && (
          <EmptyState title="No activity yet">
            Reviews, late-request decisions and deadline changes will be listed here.
          </EmptyState>
        )}
        {data && data.items.length > 0 && (
          <ul className="timeline">
            {data.items.map((n) => (
              <li key={n.id} className={n.read_at ? '' : 'tl-version_uploaded'}>
                <strong>
                  {n.ref_type === 'ASSIGNMENT' && n.ref_id ? (
                    <Link to={`/student/assignments/${n.ref_id}`}>{n.title}</Link>
                  ) : (
                    n.title
                  )}
                </strong>
                <span className="plain">{n.body}</span>
                <time className="muted small" dateTime={n.created_at}>
                  {formatIst(n.created_at)}
                </time>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}
