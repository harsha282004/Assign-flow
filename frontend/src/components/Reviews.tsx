import { useState } from 'react'
import { errorMessage } from '../api/client'
import { useRecordReview } from '../api/queries'
import type { RecordableReviewStatus, ReviewOut, StudentSubmissionDetail } from '../api/types'
import { formatIst } from '../lib/time'
import { Notice, ReviewBadge } from './ui'

const FEEDBACK_MAX = 2000

/** The review log, oldest first. Reviews are append-only: nothing here edits or deletes one. */
export function ReviewHistory({ reviews }: { reviews: ReviewOut[] }) {
  if (reviews.length === 0) return <p className="muted">No review has been recorded yet.</p>
  return (
    <ol className="versions" aria-label="Reviews">
      {reviews.map((r) => (
        <li key={r.id}>
          <div className="row">
            <span>
              <ReviewBadge status={r.status} />{' '}
              <span className="muted small">
                version {r.version_no}
                {r.is_current ? ' · current' : ''}
              </span>
            </span>
            <span className="muted small">
              {r.reviewer_name} · {formatIst(r.reviewed_at)}
            </span>
          </div>
          {r.feedback && <span className="plain">{r.feedback}</span>}
        </li>
      ))}
    </ol>
  )
}

const OPTIONS: { value: RecordableReviewStatus; label: string }[] = [
  { value: 'UNDER_REVIEW', label: 'Under review' },
  { value: 'ACCEPTED', label: 'Accepted' },
  { value: 'REVISION_REQUESTED', label: 'Revision requested' },
]

/** Faculty: record a review of the latest version. The server sets the reviewer, version and time. */
export function ReviewForm({
  assignmentId,
  data,
}: {
  assignmentId: string
  data: StudentSubmissionDetail
}) {
  const record = useRecordReview(assignmentId, data.student.id, data.submission_id ?? '')
  const [status, setStatus] = useState<RecordableReviewStatus>('ACCEPTED')
  const [feedback, setFeedback] = useState('')
  const [saved, setSaved] = useState(false)

  if (!data.submission_id) {
    return <p className="muted">Nothing to review yet: this student has not submitted a file.</p>
  }

  const trimmed = feedback.trim()
  const needsFeedback = status === 'REVISION_REQUESTED' && trimmed.length === 0
  const tooLong = trimmed.length > FEEDBACK_MAX

  function submit(e: React.FormEvent) {
    e.preventDefault()
    if (needsFeedback || tooLong || record.isPending) return
    setSaved(false)
    record.mutate(
      {
        status,
        ...(trimmed ? { feedback: trimmed } : {}),
        expected_version_no: data.latest_version_no,
      },
      {
        onSuccess: () => {
          setFeedback('')
          setSaved(true)
        },
      },
    )
  }

  return (
    <form className="decision" onSubmit={submit} noValidate>
      <p className="muted small">
        Reviews apply to the latest version (version {data.latest_version_no}). They never change
        the timing status.
      </p>
      <label>
        Review status
        <select
          value={status}
          disabled={record.isPending}
          onChange={(e) => setStatus(e.target.value as RecordableReviewStatus)}
        >
          {OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      </label>
      <label>
        Feedback {status === 'REVISION_REQUESTED' ? '(required)' : '(optional)'}
        <textarea
          rows={3}
          value={feedback}
          disabled={record.isPending}
          onChange={(e) => {
            setFeedback(e.target.value)
            setSaved(false)
          }}
        />
      </label>
      <p className={`small counter ${tooLong ? 'bad' : 'muted'}`}>
        {trimmed.length} / {FEEDBACK_MAX}
      </p>
      {status === 'ACCEPTED' && (
        <p className="muted small">
          Accepting closes the submission: the student cannot upload another version unless you
          later request a revision.
        </p>
      )}
      {record.isError && <Notice kind="error">{errorMessage(record.error)}</Notice>}
      {saved && <Notice kind="success">Review recorded. The student has been notified.</Notice>}
      <div className="actions">
        <button type="submit" disabled={needsFeedback || tooLong || record.isPending}>
          {record.isPending ? 'Saving…' : 'Record review'}
        </button>
      </div>
    </form>
  )
}
