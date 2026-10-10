import { Archive, RotateCcw, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { Link, useLocation, useSearchParams } from 'react-router-dom'
import { useFacultyAssignments } from '../../api/queries'
import type { ScopeFilter } from '../../api/types'
import { useAuth } from '../../auth/useAuth'
import AcademicSummary from '../../components/AcademicSummary'
import AssignmentActionDialog from '../../components/AssignmentActionDialog'
import ScopeFilters from '../../components/ScopeFilters'
import {
  Countdown,
  EmptyState,
  ErrorState,
  LoadingState,
  Notice,
  StatusBadge,
} from '../../components/ui'
import { formatIst } from '../../lib/time'

const ACTION_LABEL = {
  DRAFT: 'Delete assignment',
  PUBLISHED: 'Archive assignment',
  ARCHIVED: 'Restore assignment',
} as const

export default function AssignmentList() {
  const { state } = useAuth()
  const [filter, setFilter] = useState<ScopeFilter>({})
  const [params, setParams] = useSearchParams()
  const tab = params.get('state') === 'archived' ? 'archived' : 'active'
  const { data, isPending, isError, error, refetch } = useFacultyAssignments(filter, tab)
  const initial = (useLocation().state as { notice?: string } | null)?.notice
  const [notice, setNotice] = useState<string | null>(initial ?? null)
  const [toDelete, setToDelete] = useState<NonNullable<typeof data>[number] | null>(null)
  const teaching = state.status === 'authenticated' ? (state.me.teaching ?? []) : []

  return (
    <>
      <div className="row">
        <h1>My assignments</h1>
        <Link className="button" to="/faculty/assignments/new">
          New assignment
        </Link>
      </div>
      <AcademicSummary />
      <div className="tabs" role="group" aria-label="Assignment state">
        <button type="button" aria-pressed={tab === 'active'} onClick={() => setParams({})}>
          Active
        </button>
        <button
          type="button"
          aria-pressed={tab === 'archived'}
          onClick={() => setParams({ state: 'archived' })}
        >
          Archived
        </button>
      </div>
      <ScopeFilters teaching={teaching} filter={filter} onChange={setFilter} />
      {notice && <Notice kind="success">{notice}</Notice>}

      {isPending && <LoadingState label="Loading assignments…" />}
      {isError && <ErrorState error={error} onRetry={() => void refetch()} />}
      {data && data.length === 0 && (
        <EmptyState
          title={
            filter.section_id || filter.subject_id
              ? 'No assignments match these filters'
              : tab === 'archived'
                ? 'No archived assignments'
                : 'No assignments yet'
          }
        >
          {filter.section_id || filter.subject_id
            ? 'Clear the filters or create an assignment for this class.'
            : tab === 'archived'
              ? 'Assignments you archive are kept here with all their submissions and reviews.'
              : 'Create your first assignment for one of your classes.'}
        </EmptyState>
      )}
      {data && data.length > 0 && (
        <ul className="cards">
          {data.map((a) => (
            <li key={a.id} className="card-item">
              <div className="row">
                <Link className="title" to={`/faculty/assignments/${a.id}`}>
                  {a.title}
                </Link>
                <span className="badges">
                  <span className="badge">{a.assignment_type === 'QUIZ' ? 'Quiz' : 'File'}</span>
                  <StatusBadge status={a.status} />
                  <button
                    type="button"
                    className={`secondary compact${a.status === 'ARCHIVED' ? '' : ' danger'}`}
                    onClick={() => setToDelete(a)}
                    aria-label={`${ACTION_LABEL[a.status]} ${a.title}`}
                  >
                    {a.status === 'DRAFT' && <Trash2 size={16} aria-hidden="true" />}
                    {a.status === 'PUBLISHED' && <Archive size={16} aria-hidden="true" />}
                    {a.status === 'ARCHIVED' && <RotateCcw size={16} aria-hidden="true" />}{' '}
                    {ACTION_LABEL[a.status]}
                  </button>
                </span>
              </div>
              <p className="muted">
                {a.subject.code} {a.subject.name} · {a.section.label} · {a.expected_students}{' '}
                students
              </p>
              <p>
                Due {formatIst(a.deadline)}{' '}
                {a.status === 'PUBLISHED' && <Countdown iso={a.deadline} />}
                {a.status === 'ARCHIVED' && a.archived_at && (
                  <span className="muted"> · archived {formatIst(a.archived_at)}</span>
                )}
              </p>
            </li>
          ))}
        </ul>
      )}
      {toDelete && (
        <AssignmentActionDialog
          assignmentId={toDelete.id}
          title={toDelete.title}
          subject={`${toDelete.subject.code} ${toDelete.subject.name}`}
          section={toDelete.section.label}
          onClose={() => setToDelete(null)}
          onDone={(kind, title) => {
            setToDelete(null)
            setNotice(`Assignment "${title}" was ${kind}.`)
          }}
        />
      )}
    </>
  )
}
