import { useState } from 'react'
import { Archive, RotateCcw, Trash2 } from 'lucide-react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'
import { errorMessage } from '../../api/client'
import {
  useChangeDeadline,
  useFacultyAssignment,
  usePublishAssignment,
  useUpdateAssignment,
} from '../../api/queries'
import type { FacultyAssignmentDetail } from '../../api/types'
import AssignmentForm from '../../components/AssignmentForm'
import AssignmentActionDialog from '../../components/AssignmentActionDialog'
import ReferenceMaterials from '../../components/ReferenceMaterials'
import QuizFacultyPanel from '../../components/quiz/QuizFacultyPanel'
import Roster from '../../components/Roster'
import { Countdown, ErrorState, LoadingState, Notice, StatusBadge } from '../../components/ui'
import { formatIst, isoToIstInput, istInputToIso, nowIstInput } from '../../lib/time'

export default function AssignmentDetail() {
  const { id = '' } = useParams()
  const { data, isPending, isError, error, refetch } = useFacultyAssignment(id)
  const initialNotice = (useLocation().state as { notice?: string } | null)?.notice ?? null
  const [notice, setNotice] = useState<string | null>(initialNotice)
  const [editing, setEditing] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const navigate = useNavigate()

  return (
    <>
      <p className="small">
        <Link to="/faculty/assignments">← All assignments</Link>
      </p>
      {isPending && <LoadingState label="Loading assignment…" />}
      {isError && <ErrorState error={error} onRetry={() => void refetch()} />}
      {data && (
        <>
          {notice && <Notice kind="success">{notice}</Notice>}
          <div className="row">
            <h1>{data.title}</h1>
            <span className="badges">
              <StatusBadge status={data.status} />
              <button
                type="button"
                className={`secondary compact${data.status === 'ARCHIVED' ? '' : ' danger'}`}
                onClick={() => setDeleting(true)}
              >
                {data.status === 'DRAFT' && (
                  <>
                    <Trash2 size={16} aria-hidden="true" /> Delete assignment
                  </>
                )}
                {data.status === 'PUBLISHED' && (
                  <>
                    <Archive size={16} aria-hidden="true" /> Archive assignment
                  </>
                )}
                {data.status === 'ARCHIVED' && (
                  <>
                    <RotateCcw size={16} aria-hidden="true" /> Restore assignment
                  </>
                )}
              </button>
            </span>
          </div>
          {deleting && (
            <AssignmentActionDialog
              assignmentId={data.id}
              title={data.title}
              subject={`${data.subject.code} ${data.subject.name}`}
              section={data.section.label}
              onClose={() => setDeleting(false)}
              onDone={(kind, title) => {
                setDeleting(false)
                if (kind === 'deleted')
                  navigate('/faculty/assignments', {
                    replace: true,
                    state: { notice: `Assignment "${title}" was deleted.` },
                  })
                else setNotice(`Assignment "${title}" was ${kind}.`)
              }}
            />
          )}
          <p className="muted">
            {data.subject.code} {data.subject.name} · {data.section.label} ·{' '}
            {data.expected_students} students
          </p>
          {data.status === 'ARCHIVED' && (
            <div className="archived-banner" role="status">
              <p>
                <strong>
                  Archived{data.archived_at ? ` on ${formatIst(data.archived_at)}` : ''}.
                </strong>{' '}
                Students no longer see it in their active work and it accepts no new work. Every
                submission, review and file below is preserved.
              </p>
            </div>
          )}

          {data.assignment_type === 'QUIZ' ? (
            <QuizFacultyPanel data={data} onNotice={setNotice} />
          ) : (
            <section className="card-item">
              <dl className="facts">
                <dt>Deadline</dt>
                <dd>
                  {formatIst(data.deadline)}{' '}
                  {data.status === 'PUBLISHED' && <Countdown iso={data.deadline} />}
                </dd>
                {data.original_deadline !== data.deadline && (
                  <>
                    <dt>Original deadline</dt>
                    <dd>{formatIst(data.original_deadline)}</dd>
                  </>
                )}
                <dt>Allowed files</dt>
                <dd>
                  {data.allowed_types.map((t) => t.toUpperCase()).join(', ')} · up to{' '}
                  {data.max_file_mb} MB
                </dd>
                <dt>Published</dt>
                <dd>{data.published_at ? formatIst(data.published_at) : 'Not published yet'}</dd>
              </dl>
              <h2>Instructions &amp; reference materials</h2>
              <p className="plain">{data.instructions}</p>
              <ReferenceMaterials
                assignmentId={data.id}
                attachments={data.attachments}
                editable={data.status === 'DRAFT'}
              />
            </section>
          )}

          {data.assignment_type === 'QUIZ' ? (
            data.status === 'PUBLISHED' ? (
              <DeadlineChangeForm data={data} onNotice={setNotice} />
            ) : null
          ) : data.status === 'DRAFT' ? (
            <DraftActions
              data={data}
              editing={editing}
              setEditing={setEditing}
              onNotice={setNotice}
            />
          ) : data.status === 'PUBLISHED' ? (
            <DeadlineChangeForm data={data} onNotice={setNotice} />
          ) : null}

          {data.status !== 'DRAFT' && data.assignment_type !== 'QUIZ' && (
            <Roster assignmentId={data.id} />
          )}

          <h2>Deadline history</h2>
          {data.deadline_history.length === 0 ? (
            <p className="muted">
              {data.status === 'DRAFT'
                ? 'History starts once the assignment is published.'
                : 'The deadline has not been changed.'}
            </p>
          ) : (
            <ol className="history">
              {data.deadline_history.map((c) => (
                <li key={c.id}>
                  <strong>
                    {formatIst(c.old_deadline)} → {formatIst(c.new_deadline)}
                  </strong>
                  <span className="muted">
                    Changed by {c.changed_by_name} on {formatIst(c.changed_at)}
                  </span>
                  {c.reason && <span>Reason: {c.reason}</span>}
                </li>
              ))}
            </ol>
          )}
        </>
      )}
    </>
  )
}

function DraftActions({
  data,
  editing,
  setEditing,
  onNotice,
}: {
  data: FacultyAssignmentDetail
  editing: boolean
  setEditing: (v: boolean) => void
  onNotice: (m: string | null) => void
}) {
  const update = useUpdateAssignment(data.id)
  const publish = usePublishAssignment(data.id)

  return (
    <section className="card-item">
      <h2>This assignment is a draft</h2>
      <p className="muted">Students cannot see it until you publish it.</p>
      {publish.isError && <Notice kind="error">{errorMessage(publish.error)}</Notice>}
      {!editing && (
        <div className="actions">
          <button
            disabled={publish.isPending}
            onClick={() =>
              publish.mutate(undefined, { onSuccess: () => onNotice('Assignment published.') })
            }
          >
            {publish.isPending ? 'Publishing…' : 'Publish'}
          </button>
          <button className="secondary" onClick={() => setEditing(true)}>
            Edit draft
          </button>
        </div>
      )}
      {editing && (
        <>
          <AssignmentForm
            mode="edit"
            initial={data}
            busy={update.isPending}
            error={update.isError ? errorMessage(update.error) : null}
            onSubmit={(values) =>
              update.mutate(
                {
                  title: values.title,
                  instructions: values.instructions,
                  deadline: values.deadline,
                  allowed_types: values.allowed_types,
                  max_file_mb: values.max_file_mb,
                },
                {
                  onSuccess: () => {
                    onNotice('Draft updated.')
                    setEditing(false)
                  },
                },
              )
            }
          />
          <button className="secondary" onClick={() => setEditing(false)}>
            Cancel
          </button>
        </>
      )}
    </section>
  )
}

function DeadlineChangeForm({
  data,
  onNotice,
}: {
  data: FacultyAssignmentDetail
  onNotice: (m: string | null) => void
}) {
  const change = useChangeDeadline(data.id)
  const [value, setValue] = useState(isoToIstInput(data.deadline))
  const [reason, setReason] = useState('')
  const [localError, setLocalError] = useState<string | null>(null)

  function submit(e: React.FormEvent) {
    e.preventDefault()
    setLocalError(null)
    onNotice(null)
    const iso = istInputToIso(value)
    if (!value || new Date(iso).getTime() <= Date.now()) {
      setLocalError('The new deadline must be in the future.')
      return
    }
    change.mutate(
      { new_deadline: iso, ...(reason.trim() ? { reason: reason.trim() } : {}) },
      {
        onSuccess: () => {
          onNotice('Deadline updated. The change is recorded in the history below.')
          setReason('')
        },
      },
    )
  }

  const unchanged = value === isoToIstInput(data.deadline)
  return (
    <section className="card-item">
      <h2>Change deadline</h2>
      <p className="muted">Every change is recorded with who made it, when, and why.</p>
      <form onSubmit={submit} noValidate>
        <label>
          New deadline (IST)
          <input
            type="datetime-local"
            min={nowIstInput()}
            value={value}
            onChange={(e) => setValue(e.target.value)}
          />
        </label>
        <label>
          Reason (optional)
          <input
            type="text"
            maxLength={500}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
          />
        </label>
        {(localError || change.isError) && (
          <Notice kind="error">{localError ?? errorMessage(change.error)}</Notice>
        )}
        <div className="actions">
          <button type="submit" disabled={change.isPending || unchanged}>
            {change.isPending ? 'Saving…' : 'Change deadline'}
          </button>
        </div>
      </form>
    </section>
  )
}
