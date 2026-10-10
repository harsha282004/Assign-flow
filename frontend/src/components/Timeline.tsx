import type { TimelineEvent, WhyThisStatus } from '../api/types'
import { formatIst } from '../lib/time'

const LABELS: Record<TimelineEvent['type'], string> = {
  ASSIGNMENT_CREATED: 'Assignment created',
  ASSIGNMENT_PUBLISHED: 'Published',
  ASSIGNMENT_ARCHIVED: 'Archived',
  ASSIGNMENT_RESTORED: 'Restored',
  DEADLINE_CHANGED: 'Deadline changed',
  LATE_REQUESTED: 'Late request',
  REQUEST_APPROVED: 'Request approved',
  REQUEST_REJECTED: 'Request rejected',
  VERSION_UPLOADED: 'Version uploaded',
  REVIEW_RECORDED: 'Review',
  REQUEST_WINDOW_EXPIRED: 'Window expired',
  DEADLINE_PASSED_NO_SUBMISSION: 'Deadline passed',
}

/** "Why this status": the server's explanation, built by the same status functions as every badge. */
export function WhyStatus({ why }: { why: WhyThisStatus }) {
  return (
    <div className="why" aria-label="Why this status">
      <strong>Why: {why.headline}</strong>
      <ul>
        {why.lines.map((line) => (
          <li key={line} className="plain">
            {line}
          </li>
        ))}
      </ul>
    </div>
  )
}

/**
 * Deadline Integrity Timeline: the chronological, read-only history behind the current status. Every entry is a
 * stored record with its own timestamp and actor; derived markers are labelled. Text is shown as plain text.
 */
export default function Timeline({ events }: { events: TimelineEvent[] }) {
  return (
    <ol className="timeline" aria-label="Deadline Integrity Timeline">
      {events.map((e, i) => (
        <li key={`${e.type}-${e.at}-${i}`} className={`tl-${e.type.toLowerCase()}`}>
          <div className="row">
            <strong>
              {LABELS[e.type]}
              {e.derived && <span className="muted small"> (derived from the clock)</span>}
            </strong>
            <span className="muted small">{formatIst(e.at)}</span>
          </div>
          <span className="plain">{e.summary}</span>
          {e.actor && <span className="muted small">by {e.actor}</span>}
        </li>
      ))}
    </ol>
  )
}
