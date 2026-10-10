import { AlertTriangle, ClipboardList, FileText, Inbox, Users } from 'lucide-react'
import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useFacultyAssignments, useLateRequests, useOverview } from '../../api/queries'
import type { ScopeFilter } from '../../api/types'
import { useAuth } from '../../auth/useAuth'
import ActivityPanel, { SkeletonRows } from '../../components/dash/ActivityPanel'
import DeadlineCalendar, { type CalendarEvent } from '../../components/dash/DeadlineCalendar'
import StatCard from '../../components/dash/StatCard'
import ScopeFilters from '../../components/ScopeFilters'
import { Countdown, ErrorState, StatusBadge } from '../../components/ui'
import { formatIst, formatIstDay, relativeIst } from '../../lib/time'

export default function FacultyDashboard() {
  const { state } = useAuth()
  const [filter, setFilter] = useState<ScopeFilter>({})

  // The server authorises and applies the subject / section filter to every query below; while a new filter loads
  // each card and table shows a skeleton (no stale numbers), and failures show an error, never sample data.
  const overview = useOverview(filter)
  const list = useFacultyAssignments(filter, 'active')
  const archivedList = useFacultyAssignments(filter, 'archived')
  const pending = useLateRequests('PENDING', true, filter)

  const counts = useMemo(() => {
    const map = new Map<string, { submitted: number; missing: number }>()
    for (const a of overview.data?.assignments ?? [])
      map.set(a.assignment.id, { submitted: a.submitted, missing: a.missing })
    return map
  }, [overview.data])

  const rows = useMemo(
    () => [...(list.data ?? [])].sort((x, y) => y.deadline.localeCompare(x.deadline)),
    [list.data],
  )

  const events = useMemo<CalendarEvent[]>(
    () =>
      rows
        .filter((a) => a.status === 'PUBLISHED')
        .map((a) => ({
          id: a.id,
          at: a.deadline,
          kind: new Date(a.deadline).getTime() >= Date.now() ? 'due' : 'other',
          title: a.title,
          detail: `${a.subject.code} · ${a.section.label}`,
          to: `/faculty/assignments/${a.id}`,
        })),
    [rows],
  )

  if (state.status !== 'authenticated') return null
  const { me } = state

  const teaching = me.teaching ?? []
  const subjects = [...new Map(teaching.map((t) => [t.subject.id, t.subject])).values()]
  const sections = [...new Map(teaching.map((t) => [t.section.id, t.section])).values()]
  const chosenSection = sections.find((x) => x.id === filter.section_id)
  const totals = overview.data?.totals
  const activeCount = rows.filter((a) => a.status === 'PUBLISHED').length
  const pendingList = pending.data ?? []

  return (
    <div className="dashboard">
      <div className="dash-head">
        <div>
          <h1>Welcome back, {me.full_name}</h1>
          <p className="muted">Your teaching and submission overview.</p>
        </div>
        <div className="dash-pill">
          <Users size={18} aria-hidden="true" />
          <span>
            {teaching.length === 0
              ? 'No teaching assignments'
              : `${subjects.length} subject${subjects.length === 1 ? '' : 's'} · ${sections.length} section${sections.length === 1 ? '' : 's'}`}
            <span className="muted small block">{formatIstDay(Date.now())}</span>
          </span>
        </div>
      </div>

      <ScopeFilters teaching={teaching} filter={filter} onChange={setFilter}>
        <Link className="button secondary-link" to="/faculty/board">
          Open the full health board →
        </Link>
      </ScopeFilters>

      <div className="stat-grid">
        <StatCard
          label="Active assignments"
          caption="Published, in your scope"
          value={list.data ? activeCount : undefined}
          icon={FileText}
          tone="blue"
          loading={list.isPending}
          failed={list.isError}
        />
        <StatCard
          label="Expected submissions"
          caption="Student–assignment pairs"
          value={totals?.expected}
          icon={ClipboardList}
          tone="green"
          loading={overview.isPending}
          failed={overview.isError}
        />
        <StatCard
          label="Missing submissions"
          caption="Past deadline, nothing uploaded"
          value={totals?.missing}
          icon={AlertTriangle}
          tone="red"
          loading={overview.isPending}
          failed={overview.isError}
        />
        <StatCard
          label="Pending late requests"
          caption="Awaiting your decision"
          value={totals?.requests_pending}
          icon={Inbox}
          tone="yellow"
          loading={overview.isPending}
          failed={overview.isError}
        />
      </div>

      <div className="dash-grid">
        <div className="dash-main">
          <section className="dash-card" aria-labelledby="mgmt-h">
            <div className="dash-card-head">
              <h2 id="mgmt-h">
                <ClipboardList size={20} aria-hidden="true" /> Assignments and submission health
              </h2>
              <Link className="button" to="/faculty/assignments/new">
                New assignment
              </Link>
            </div>
            {archivedList.data && archivedList.data.length > 0 && (
              <p className="muted small">
                {archivedList.data.length} archived assignment
                {archivedList.data.length === 1 ? '' : 's'} (not counted here, history kept) ·{' '}
                <Link to="/faculty/assignments?state=archived">View archived</Link>
              </p>
            )}
            {(list.isPending || overview.isPending) && (
              <SkeletonRows rows={4} label="Loading assignments…" />
            )}
            {list.isError && <ErrorState error={list.error} onRetry={() => void list.refetch()} />}
            {overview.isError && (
              <ErrorState error={overview.error} onRetry={() => void overview.refetch()} />
            )}
            {list.data && rows.length === 0 && (
              <div className="empty-soft">
                <FileText size={28} aria-hidden="true" />
                <strong>
                  {chosenSection
                    ? `No assignments for ${chosenSection.label} yet`
                    : 'No assignments in this scope'}
                </strong>
                <p className="muted small">
                  {filter.section_id || filter.subject_id
                    ? 'Nothing matches the selected filters. Clear them or create an assignment for this class.'
                    : 'Create an assignment for one of your classes.'}
                </p>
              </div>
            )}
            {rows.length > 0 && (
              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Assignment</th>
                      <th>Class</th>
                      <th>Deadline</th>
                      <th>State</th>
                      <th>Submitted</th>
                      <th>Missing</th>
                      <th>
                        <span className="sr-only">Action</span>
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.slice(0, 8).map((a) => {
                      const c = counts.get(a.id)
                      return (
                        <tr key={a.id}>
                          <td data-label="Assignment">
                            <Link className="title" to={`/faculty/assignments/${a.id}`}>
                              {a.title}
                            </Link>
                          </td>
                          <td data-label="Class">
                            <span className="code-chip">{a.subject.code}</span>
                            <span className="muted small block">{a.section.label}</span>
                          </td>
                          <td data-label="Deadline">
                            <span className="small">{formatIst(a.deadline)}</span>
                            {a.status === 'PUBLISHED' && (
                              <span className="block small">
                                <Countdown iso={a.deadline} />
                              </span>
                            )}
                          </td>
                          <td data-label="State">
                            <StatusBadge status={a.status} />
                          </td>
                          <td data-label="Submitted">
                            {c ? (
                              <>
                                <strong>{c.submitted}</strong>
                                <span className="muted small"> / {a.expected_students}</span>
                              </>
                            ) : (
                              <span className="muted small">
                                {a.status === 'DRAFT' ? 'Not published' : '–'}
                              </span>
                            )}
                          </td>
                          <td data-label="Missing">
                            {c ? (
                              <span className={c.missing > 0 ? 'bad' : ''}>{c.missing}</span>
                            ) : (
                              '–'
                            )}
                          </td>
                          <td data-label="">
                            <Link className="link-arrow" to={`/faculty/assignments/${a.id}`}>
                              Manage →
                            </Link>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
                {rows.length > 8 && (
                  <p className="small">
                    <Link to="/faculty/assignments">All {rows.length} assignments →</Link>
                  </p>
                )}
              </div>
            )}
          </section>

          <section className="dash-card" aria-labelledby="lr-h">
            <div className="dash-card-head">
              <h2 id="lr-h">
                <Inbox size={20} aria-hidden="true" /> Late requests awaiting a decision
              </h2>
              <Link className="link-arrow" to="/faculty/late-requests">
                Open queue →
              </Link>
            </div>
            {pending.isPending && <SkeletonRows rows={2} label="Loading late requests…" />}
            {pending.isError && (
              <ErrorState error={pending.error} onRetry={() => void pending.refetch()} />
            )}
            {pending.data && pendingList.length === 0 && (
              <div className="empty-soft">
                <Inbox size={28} aria-hidden="true" />
                <strong>Nothing to decide</strong>
                <p className="muted small">New late requests from your students appear here.</p>
              </div>
            )}
            {pendingList.length > 0 && (
              <ul className="list">
                {pendingList.slice(0, 4).map((r) => (
                  <li key={r.id}>
                    <span>
                      <Link to={`/faculty/late-requests/${r.id}`}>
                        {r.student.full_name} · {r.assignment.title}
                      </Link>
                      <br />
                      <span className="muted small">
                        {r.assignment.subject.code} · {r.assignment.section.label}
                      </span>
                    </span>
                    <span className="muted small">{relativeIst(r.requested_at)}</span>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>

        <aside className="dash-side" aria-label="Activity and calendar">
          <ActivityPanel
            faculty
            viewAllTo="/faculty/late-requests"
            note="Notifications are not tied to a section, so this feed always covers all your classes."
          />
          <DeadlineCalendar events={events} kinds={['due', 'other']} />
        </aside>
      </div>
    </div>
  )
}
