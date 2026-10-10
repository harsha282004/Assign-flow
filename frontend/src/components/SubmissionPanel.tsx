import { useRef, useState } from 'react'
import { errorMessage } from '../api/client'
import { useUploadSubmission } from '../api/queries'
import type { StudentAssignmentDetail } from '../api/types'
import VersionList from './VersionList'
import { Notice, TimingBadge } from './ui'

const BLOCKED: Record<'DEADLINE_PASSED' | 'SUBMISSION_ACCEPTED' | 'ARCHIVED', string> = {
  ARCHIVED:
    'This assignment has been archived, so it no longer accepts submissions. Your earlier work and feedback stay available below.',
  DEADLINE_PASSED: 'The deadline has passed, so new submissions are closed.',
  SUBMISSION_ACCEPTED: 'Your submission has been accepted, so it can no longer be replaced.',
}

function extension(name: string): string {
  const ext = name.includes('.') ? name.split('.').pop()!.toLowerCase() : ''
  return ext === 'jpeg' ? 'jpg' : ext
}

/** Student submission area: status, upload form with progress, and the full version history. */
export default function SubmissionPanel({ assignment }: { assignment: StudentAssignmentDetail }) {
  const upload = useUploadSubmission(assignment.id)
  const inputRef = useRef<HTMLInputElement>(null)
  const [file, setFile] = useState<File | null>(null)
  const [progress, setProgress] = useState(0)
  const [localError, setLocalError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)

  const hasVersions = assignment.versions.length > 0
  const accept = assignment.allowed_types
    .map((t) => `.${t}${t === 'jpg' ? ',.jpeg' : ''}`)
    .join(',')

  // Convenience checks only: the server validates the extension, the real content type and the size.
  function onPick(f: File | null) {
    setFile(f)
    setSuccess(null)
    setLocalError(null)
    if (!f) return
    if (!assignment.allowed_types.includes(extension(f.name) as never)) {
      setLocalError(
        `This assignment accepts only: ${assignment.allowed_types.map((t) => t.toUpperCase()).join(', ')}.`,
      )
    } else if (f.size > assignment.max_file_mb * 1024 * 1024) {
      setLocalError(`The file is larger than ${assignment.max_file_mb} MB.`)
    } else if (f.size === 0) {
      setLocalError('The selected file is empty.')
    }
  }

  function onSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!file || localError) return
    setSuccess(null)
    setProgress(0)
    upload.mutate(
      { file, onProgress: setProgress },
      {
        onSuccess: (r) => {
          const label =
            r.submission_timing === 'ON_TIME'
              ? 'On time'
              : r.submission_timing === 'LATE' && assignment.late_request?.status === 'APPROVED'
                ? 'Late (approved)'
                : r.submission_timing
          setSuccess(`Version ${r.version_no} received. Status: ${label}.`)
          setFile(null)
          if (inputRef.current) inputRef.current.value = ''
        },
      },
    )
  }

  return (
    <section className="card-item" aria-labelledby="submission-heading">
      <div className="row">
        <h2 id="submission-heading">My submission</h2>
        <span>
          <TimingBadge timing={assignment.timing} lateApproved={assignment.late_approved} />{' '}
          {assignment.is_resubmitted && <span className="badge status-draft">Resubmitted</span>}
        </span>
      </div>

      {assignment.can_upload ? (
        <form onSubmit={onSubmit} noValidate>
          <label>
            {hasVersions ? 'Upload a new version' : 'Choose your file'}
            <input
              ref={inputRef}
              type="file"
              accept={accept}
              disabled={upload.isPending}
              onChange={(e) => onPick(e.target.files?.[0] ?? null)}
            />
          </label>
          <p className="muted small">
            Allowed: {assignment.allowed_types.map((t) => t.toUpperCase()).join(', ')} · up to{' '}
            {assignment.max_file_mb} MB. Earlier versions are always kept.
          </p>
          {upload.isPending && (
            <p role="status">
              <progress value={progress} max={100} aria-label="Upload progress" /> Uploading…{' '}
              {progress}%
            </p>
          )}
          {localError && <Notice kind="error">{localError}</Notice>}
          {upload.isError && <Notice kind="error">{errorMessage(upload.error)}</Notice>}
          {success && <Notice kind="success">{success}</Notice>}
          <div className="actions">
            <button type="submit" disabled={!file || !!localError || upload.isPending}>
              {upload.isPending ? 'Uploading…' : hasVersions ? 'Upload new version' : 'Submit'}
            </button>
          </div>
        </form>
      ) : (
        <>
          {assignment.upload_blocked_reason && (
            <Notice kind="info">{BLOCKED[assignment.upload_blocked_reason]}</Notice>
          )}
          {success && <Notice kind="success">{success}</Notice>}
        </>
      )}

      <h2>Version history</h2>
      <VersionList versions={assignment.versions} />
    </section>
  )
}
