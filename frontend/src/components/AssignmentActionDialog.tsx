import { AlertTriangle, Archive, RotateCcw, Trash2 } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { errorMessage } from '../api/client'
import {
  useArchiveAssignment,
  useDeleteAssignment,
  useDeletionCheck,
  useRestoreAssignment,
} from '../api/queries'
import { ErrorState } from './ui'

// [singular, plural]
const LABELS: Record<string, [string, string]> = {
  submissions: ['submission', 'submissions'],
  versions: ['submitted file version', 'submitted file versions'],
  reviews: ['review', 'reviews'],
  late_requests: ['late-submission request', 'late-submission requests'],
  deadline_changes: ['deadline change', 'deadline changes'],
  notifications: ['notification', 'notifications'],
  reference_files: ['reference document', 'reference documents'],
}
const describe = (k: string, n: number) => `${n} ${(LABELS[k] ?? [k, k])[n === 1 ? 0 : 1]}`

export type ActionKind = 'deleted' | 'archived' | 'restored'

interface Props {
  assignmentId: string
  title: string
  subject: string
  section: string
  onClose: () => void
  onDone: (kind: ActionKind, title: string) => void
}

/**
 * One dialog for the three things a teacher can do to an assignment that they no longer want:
 *  - a DRAFT is deleted permanently (only when nothing refers to it);
 *  - a PUBLISHED assignment is archived (reversible, keeps every submission, review and file); with student history the
 *    dialog says so first and the archive needs a SEPARATE second confirmation;
 *  - an ARCHIVED assignment is restored.
 * The server decides what is allowed (deletion-check) and re-checks everything when the action is sent.
 */
export default function AssignmentActionDialog({
  assignmentId,
  title,
  subject,
  section,
  onClose,
  onDone,
}: Props) {
  const check = useDeletionCheck(assignmentId, true)
  const del = useDeleteAssignment(assignmentId)
  const archive = useArchiveAssignment(assignmentId)
  const restore = useRestoreAssignment(assignmentId)
  const [step, setStep] = useState<'info' | 'confirm'>('info')
  const [reason, setReason] = useState('')
  const cancelRef = useRef<HTMLButtonElement>(null)
  const opener = useRef<Element | null>(document.activeElement)
  const busy = del.isPending || archive.isPending || restore.isPending

  useEffect(() => {
    cancelRef.current?.focus()
    const previous = opener.current
    const overflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape' && !busy) onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => {
      window.removeEventListener('keydown', onKey)
      document.body.style.overflow = overflow
      if (previous instanceof HTMLElement) previous.focus()
    }
  }, [onClose, busy, step])

  const data = check.data
  const action = data?.action
  const blockers = Object.entries(data?.blockers ?? {})
  const refusal = [del, archive, restore].find((m) => m.isError)
  const refusalText = refusal?.error ? errorMessage(refusal.error) : null
  // An archive of an assignment WITH student history gets the explanation first and a separate confirmation after.
  const archiveSteps = action === 'ARCHIVE' && data?.student_history
  const confirming = action === 'ARCHIVE' && (!archiveSteps || step === 'confirm')

  let heading = 'Remove assignment?'
  let icon = <AlertTriangle size={18} aria-hidden="true" />
  if (action === 'DELETE') heading = 'Delete assignment?'
  if (action === 'ARCHIVE') {
    heading =
      archiveSteps && step === 'info'
        ? 'This assignment has student history'
        : `Archive “${title}”?`
    icon = <Archive size={18} aria-hidden="true" />
  }
  if (action === 'RESTORE') {
    heading = 'Restore assignment?'
    icon = <RotateCcw size={18} aria-hidden="true" />
  }

  return (
    <div className="modal-backdrop" onClick={() => !busy && onClose()}>
      <div
        className="modal confirm"
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="act-title"
        aria-describedby="act-body"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="modal-head">
          <strong id="act-title" className={action === 'RESTORE' ? 'accent-text' : 'danger-text'}>
            {icon} {heading}
          </strong>
        </header>
        <div className="modal-body confirm-body" id="act-body">
          <dl className="facts">
            <dt>Assignment</dt>
            <dd>{title}</dd>
            <dt>Subject</dt>
            <dd>{subject}</dd>
            <dt>Section</dt>
            <dd>{section}</dd>
            {data && (
              <>
                <dt>State</dt>
                <dd>
                  {data.status === 'DRAFT'
                    ? 'Draft (never visible to students)'
                    : data.status === 'ARCHIVED'
                      ? 'Archived'
                      : 'Published'}
                </dd>
              </>
            )}
          </dl>

          {check.isPending && (
            <p className="muted" role="status">
              Checking submission and review history…
            </p>
          )}
          {check.isError && <ErrorState error={check.error} onRetry={() => void check.refetch()} />}

          {action === 'DELETE' && (
            <>
              <p>
                <strong>This cannot be undone.</strong> The draft has no submissions, reviews, late
                requests or notifications, so no student work or history is lost.
              </p>
              {data && data.reference_files > 0 && (
                <p className="muted small">
                  Its {data.reference_files} draft reference document
                  {data.reference_files === 1 ? '' : 's'} will be deleted with it.
                </p>
              )}
              {data && !data.can_delete && (
                <div className="notice error" role="alert">
                  <strong>This draft cannot be permanently deleted.</strong>
                  <p>
                    Records refer to it: {blockers.map(([k, n]) => describe(k, n)).join(', ')}.
                    Nothing was changed.
                  </p>
                </div>
              )}
            </>
          )}

          {action === 'ARCHIVE' && archiveSteps && step === 'info' && (
            <>
              <p>
                This assignment contains submissions, reviews or other records that must be
                preserved
                {blockers.length > 0 && (
                  <>: {blockers.map(([k, n]) => describe(k, n)).join(', ')}</>
                )}
                . It cannot be permanently deleted, but you can <strong>archive</strong> it: it
                leaves active use and every record and file is kept.
              </p>
            </>
          )}

          {confirming && (
            <>
              {!archiveSteps && (
                <p>
                  Nothing has been submitted for this assignment. Archiving takes it out of active
                  use; you can restore it later.
                </p>
              )}
              <p className="small">
                <strong>What archiving does</strong>
              </p>
              <ul className="effects">
                <li>
                  Students stop seeing it in their active work, alerts and upcoming deadlines.
                </li>
                <li>
                  It leaves your dashboard counts and the health board. New uploads, late requests,
                  reviews, late-request decisions and deadline changes are blocked.
                </li>
                <li>
                  Students who already submitted can still open it read-only, with their feedback
                  and files. You keep the roster, every submission, review, late request, deadline
                  change and notification.
                </li>
                <li>Nothing is deleted or changed, and you can restore it at any time.</li>
              </ul>
              <label>
                Reason (optional, shown in the timeline)
                <input
                  type="text"
                  maxLength={500}
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                />
              </label>
            </>
          )}

          {action === 'RESTORE' && (
            <p>
              Restoring makes it active again with the <strong>same deadline</strong>: students see
              it, and uploads and late requests are accepted again. All history is unchanged.
            </p>
          )}

          {refusalText && (
            <p className="notice error" role="alert">
              {refusalText}
            </p>
          )}
        </div>

        <footer className="confirm-actions">
          {action === 'ARCHIVE' && archiveSteps && step === 'confirm' ? (
            <button className="secondary" disabled={busy} onClick={() => setStep('info')}>
              Back
            </button>
          ) : (
            <button ref={cancelRef} className="secondary" disabled={busy} onClick={onClose}>
              {action === 'DELETE' && data && !data.can_delete
                ? 'Close'
                : action === 'ARCHIVE' && archiveSteps
                  ? 'Close'
                  : 'Cancel'}
            </button>
          )}

          {action === 'DELETE' && data?.can_delete && (
            <button
              className="danger-solid"
              disabled={busy || del.isSuccess}
              onClick={() =>
                del.mutate(undefined, { onSuccess: (r) => onDone('deleted', r.title) })
              }
            >
              <Trash2 size={16} aria-hidden="true" /> {busy ? 'Deleting…' : 'Delete permanently'}
            </button>
          )}

          {action === 'ARCHIVE' && archiveSteps && step === 'info' && (
            <button className="danger-solid" onClick={() => setStep('confirm')}>
              <Archive size={16} aria-hidden="true" /> Archive assignment
            </button>
          )}

          {confirming && (
            <button
              className="danger-solid"
              disabled={busy || archive.isSuccess}
              onClick={() =>
                archive.mutate(reason.trim() || undefined, {
                  onSuccess: (r) => onDone('archived', r.title),
                })
              }
            >
              <Archive size={16} aria-hidden="true" /> {busy ? 'Archiving…' : 'Confirm archive'}
            </button>
          )}

          {action === 'RESTORE' && (
            <button
              className="primary-solid"
              disabled={busy || restore.isSuccess}
              onClick={() =>
                restore.mutate(undefined, { onSuccess: (r) => onDone('restored', r.title) })
              }
            >
              <RotateCcw size={16} aria-hidden="true" />{' '}
              {busy ? 'Restoring…' : 'Restore assignment'}
            </button>
          )}
        </footer>
      </div>
    </div>
  )
}
