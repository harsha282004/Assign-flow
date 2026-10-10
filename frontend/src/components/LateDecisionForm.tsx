import { useState } from 'react'
import { errorMessage } from '../api/client'
import { useDecideLateRequest } from '../api/queries'
import type { LateRequest } from '../api/types'
import { formatIst } from '../lib/time'
import { Notice, RequestBadge } from './ui'

const NOTE_MAX = 500

/** What was decided, shown for every request that is no longer pending. */
export function DecisionSummary({ request }: { request: LateRequest }) {
  if (!request.decided_at) return null
  return (
    <dl className="facts">
      <dt>Decision</dt>
      <dd>
        <RequestBadge status={request.state} /> by {request.decided_by_name ?? 'faculty'} on{' '}
        {formatIst(request.decided_at)}
      </dd>
      {request.window_start && request.window_end && (
        <>
          <dt>Submission window</dt>
          <dd>
            {formatIst(request.window_start)} to {formatIst(request.window_end)}
          </dd>
        </>
      )}
      {request.decision_note && (
        <>
          <dt>Note</dt>
          <dd className="plain">{request.decision_note}</dd>
        </>
      )}
    </dl>
  )
}

/**
 * Approve (with a 1-72 hour window, default 24) or reject a pending request. The decision time and the
 * window are set by the server; nothing here sends a timestamp.
 */
export default function LateDecisionForm({ request }: { request: LateRequest }) {
  const decide = useDecideLateRequest(request.id)
  const [hours, setHours] = useState('24')
  const [note, setNote] = useState('')

  if (request.state !== 'PENDING') {
    return (
      <>
        <DecisionSummary request={request} />
        {decide.isError && <Notice kind="error">{errorMessage(decide.error)}</Notice>}
      </>
    )
  }

  const hoursNumber = Number(hours)
  const hoursValid = Number.isInteger(hoursNumber) && hoursNumber >= 1 && hoursNumber <= 72
  const noteValid = note.trim().length <= NOTE_MAX

  function send(decision: 'APPROVE' | 'REJECT') {
    if (decide.isPending) return
    const trimmed = note.trim()
    decide.mutate({
      decision,
      ...(trimmed ? { note: trimmed } : {}),
      ...(decision === 'APPROVE' ? { window_hours: hoursNumber } : {}),
    })
  }

  return (
    <form className="decision" onSubmit={(e) => e.preventDefault()}>
      <label>
        Submission window in hours (1 to 72), used when approving
        <input
          type="number"
          min={1}
          max={72}
          step={1}
          value={hours}
          disabled={decide.isPending}
          onChange={(e) => setHours(e.target.value)}
        />
      </label>
      <label>
        Note to the student (optional)
        <textarea
          rows={2}
          value={note}
          disabled={decide.isPending}
          onChange={(e) => setNote(e.target.value)}
        />
      </label>
      {!noteValid && <Notice kind="error">The note can have at most {NOTE_MAX} characters.</Notice>}
      {decide.isError && <Notice kind="error">{errorMessage(decide.error)}</Notice>}
      <div className="actions">
        <button
          type="button"
          disabled={!hoursValid || !noteValid || decide.isPending}
          onClick={() => send('APPROVE')}
        >
          {decide.isPending ? 'Saving…' : 'Approve'}
        </button>
        <button
          type="button"
          className="secondary"
          disabled={!noteValid || decide.isPending}
          onClick={() => send('REJECT')}
        >
          Reject
        </button>
      </div>
      {!hoursValid && <p className="bad small">Enter a whole number of hours from 1 to 72.</p>}
    </form>
  )
}
