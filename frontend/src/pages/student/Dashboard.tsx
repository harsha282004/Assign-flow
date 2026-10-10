import { BookOpen, CalendarClock, CheckCircle2, Clock, FileText } from 'lucide-react'
import { useMemo } from 'react'
import { Link } from 'react-router-dom'
import { useStudentAssignments } from '../../api/queries'
import type { StudentAssignmentItem } from '../../api/types'
import { useAuth } from '../../auth/useAuth'
import ActivityPanel, { SkeletonRows } from '../../components/dash/ActivityPanel'
import DeadlineCalendar, { type CalendarEvent } from '../../components/dash/DeadlineCalendar'
import StatCard from '../../components/dash/StatCard'
import { Countdown, ErrorState, RequestBadge, ReviewBadge, TimingBadge } from '../../components/ui'
import { formatIst, formatIstDay } from '../../lib/time'

const WEEK_MS = 7 * 24 * 60 * 60 * 1000
const COURSE_TONES = ['blue', 'yellow', 'lavender', 'green'] as const

const hasSubmission = (a: StudentAssignmentItem) => a.timing === 'ON_TIME' || a.timing === 'LATE'

function calendarKind(a: StudentAssignmentItem): CalendarEvent['kind'] {
  if (hasSubmission(a)) return 'done'
  if (a.request_status === 'PENDING' || a.request_status === 'APPROVED') return 'late'
  if (a.timing === 'MISSING') return 'missed'
  return 'due'
}

/** Rows for the "Upcoming assignments" card: open work first (soonest deadline), then the rest. */
export function AssignmentRows({ items }: { items: StudentAssignmentItem[] }) {
  return (
    <div className="table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            <th>Assignment</th>
            <th>Course</th>
            <th>Deadline</th>
            <th>Status</th>
            <th>
              <span className="sr-only">Action</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {items.map((a) => (
            <tr key={a.id}>
              <td data-label="Assignment">
                <Link className="title" to={`/student/assignments/${a.id}`}>
                  {a.title}
                </Link>
                <span className="block small muted">
                  {a.assignment_type === 'QUIZ'
                    ? `Quiz · ${a.question_count ?? 0} questions · ${a.total_marks ?? 0} marks${a.duration_minutes ? ` · ${a.duration_minutes} min` : ''}`
                    : 'File Assignment'}
                </span>
                {a.latest_feedback && (
                  <p className="muted small plain clamp">Feedback: {a.latest_feedback}</p>
                )}
              </td>
              <td data-label="Course">
                <span className="code-chip">{a.subject.code}</span>
                <span className="muted small block">{a.subject.name}</span>
              </td>
              <td data-label="Deadline">
                <span className="small">{formatIst(a.deadline)}</span>
                {a.timing === 'PENDING' && a.assignment_state !== 'ARCHIVED' && (
                  <span className="block small">
                    <Countdown iso={a.deadline} />
                  </span>
                )}
              </td>
              <td data-label="Status">
                <span className="badges">
                  {a.assignment_type === 'QUIZ' && (
                    <span className="badge status-published">
                      {a.quiz_status === 'SUBMITTED'
                        ? `Submitted · ${a.quiz_score ?? 0}/${a.total_marks ?? 0}`
                        : a.quiz_status === 'IN_PROGRESS'
                          ? 'In progress'
                          : 'Not attempted'}
                    </span>
                  )}
                  {a.assignment_state === 'ARCHIVED' && (
                    <span className="badge status-archived">Archived</span>
                  )}
                  {(a.assignment_state !== 'ARCHIVED' || hasSubmission(a)) && (
                    <TimingBadge timing={a.timing} lateApproved={a.late_approved} />
                  )}
                  {a.is_resubmitted && (
                    <span className="badge status-resubmitted">Resubmitted</span>
                  )}
                  <RequestBadge status={a.request_status} />
                  {a.review_status !== 'NOT_REVIEWED' && <ReviewBadge status={a.review_status} />}
                </span>
              </td>
              <td data-label="">
                <Link className="link-arrow" to={`/student/assignments/${a.id}`}>
                  View assignment →
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default function StudentDashboard() {
  const { state } = useAuth()
  const list = useStudentAssignments()
  const data = list.data

  const stats = useMemo(() => {
    if (!data) return null
    const now = Date.now()
    return {
      active: data.length,
      submitted: data.filter(hasSubmission).length,
      // Window filter only: whether an assignment is pending comes from the server (timing === PENDING).
      dueThisWeek: data.filter((a) => {
        const t = new Date(a.deadline).getTime()
        return a.timing === 'PENDING' && t >= now && t - now <= WEEK_MS
      }).length,
      requests: data.filter((a) => a.request_status === 'PENDING').length,
    }
  }, [data])

  const upcoming = useMemo(() => {
    if (!data) return []
    const open = data
      .filter((a) => a.timing === 'PENDING')
      .sort((x, y) => x.deadline.localeCompare(y.deadline))
    const rest = data
      .filter((a) => a.timing !== 'PENDING')
      .sort((x, y) => y.deadline.localeCompare(x.deadline))
    return [...open, ...rest].slice(0, 6)
  }, [data])

  const events = useMemo<CalendarEvent[]>(
    () =>
      (data ?? []).map((a) => ({
        id: a.id,
        at: a.deadline,
        kind: calendarKind(a),
        title: a.title,
        detail: `${a.subject.code} ${a.subject.name}`,
        to: `/student/assignments/${a.id}`,
      })),
    [data],
  )

  if (state.status !== 'authenticated') return null
  const { me } = state
  const firstName = me.full_name.split(' ')[0]

  return (
    <div className="dashboard">
      <div className="dash-head">
        <div>
          <h1>Welcome back, {firstName}</h1>
          <p className="muted">Your academic workload at a glance.</p>
        </div>
        <div className="dash-pill">
          <BookOpen size={18} aria-hidden="true" />
          <span>
            {me.section
              ? `Semester ${me.section.semester} · ${me.section.label}`
              : 'No class assigned'}
            <span className="muted small block">{formatIstDay(Date.now())}</span>
          </span>
        </div>
      </div>

      <div className="stat-grid">
        <StatCard
          label="Active assignments"
          caption="Total for this semester"
          value={stats?.active}
          icon={FileText}
          tone="blue"
          loading={list.isPending}
          failed={list.isError}
        />
        <StatCard
          label="Submitted"
          caption="Completed submissions"
          value={stats?.submitted}
          icon={CheckCircle2}
          tone="green"
          loading={list.isPending}
          failed={list.isError}
        />
        <StatCard
          label="Due this week"
          caption="Pending deadlines (next 7 days)"
          value={stats?.dueThisWeek}
          icon={CalendarClock}
          tone="yellow"
          loading={list.isPending}
          failed={list.isError}
        />
        <StatCard
          label="Late requests"
          caption="Awaiting a decision"
          value={stats?.requests}
          icon={Clock}
          tone="red"
          loading={list.isPending}
          failed={list.isError}
        />
      </div>

      <div className="dash-grid">
        <div className="dash-main">
          <section className="dash-card" aria-labelledby="upcoming-h">
            <div className="dash-card-head">
              <h2 id="upcoming-h">
                <FileText size={20} aria-hidden="true" /> Upcoming assignments
              </h2>
              <Link className="button" to="/student/assignments">
                View all assignments →
              </Link>
            </div>
            {list.isPending && <SkeletonRows rows={4} label="Loading assignments…" />}
            {list.isError && <ErrorState error={list.error} onRetry={() => void list.refetch()} />}
            {data && data.length === 0 && (
              <div className="empty-soft">
                <FileText size={28} aria-hidden="true" />
                <strong>No assignments yet</strong>
                <p className="muted small">
                  Assignments from your teachers will appear here once they are published.
                </p>
              </div>
            )}
            {upcoming.length > 0 && <AssignmentRows items={upcoming} />}
          </section>

          <section className="dash-card" aria-labelledby="courses-h">
            <div className="dash-card-head">
              <h2 id="courses-h">
                <BookOpen size={20} aria-hidden="true" /> My courses this semester
              </h2>
            </div>
            {!me.subjects || me.subjects.length === 0 ? (
              <p className="muted">No subjects are mapped to your class yet.</p>
            ) : (
              <ul className="course-grid">
                {me.subjects.map((s, i) => {
                  const mine = data?.filter((a) => a.subject.code === s.code)
                  const done = mine?.filter(hasSubmission).length
                  return (
                    <li
                      key={s.code}
                      className={`course tone-${COURSE_TONES[i % COURSE_TONES.length]}`}
                    >
                      <span className="code-chip strong">{s.code}</span>
                      <strong>{s.name}</strong>
                      <span className="muted small">{s.faculty_name ?? 'No faculty assigned'}</span>
                      {mine && (
                        <span className="small">
                          {mine.length === 0
                            ? 'No assignments yet'
                            : `${done} of ${mine.length} submitted`}
                        </span>
                      )}
                    </li>
                  )
                })}
              </ul>
            )}
          </section>
        </div>

        <aside className="dash-side" aria-label="Activity and calendar">
          <ActivityPanel faculty={false} viewAllTo="/student/timeline" />
          <DeadlineCalendar events={events} kinds={['due', 'late', 'done', 'missed']} />
        </aside>
      </div>
    </div>
  )
}
