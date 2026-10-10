import { useState } from 'react'
import { errorMessage } from '../api/client'
import { useCreateLateRequest } from '../api/queries'
import type { StudentAssignmentDetail } from '../api/types'
import { formatIst } from '../lib/time'
import { Countdown, Notice, RequestBadge } from './ui'

const MIN = 20
const MAX = 1000

/** Student side of the late-submission workflow: ask, then follow the decision and the approved window. */
export default function LateRequestPanel({ assignment }: { assignment: StudentAssignmentDetail }) {
  const create = useCreateLateRequest(assignment.id)
  const [reason, setReason] = useState('')
  const request = assignment.late_request

  const trimmed = reason.trim().length
  const tooShort = trimmed > 0 && trimmed < MIN
  const invalid = trimmed < MIN || trimmed > MAX

  function onSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (invalid || create.isPending) return
    create.mutate(reason.trim(), { onSuccess: () => setReason('') })
  }

  if (!request && !assignment.can_request_late) return null

  return (
    <section className="card-item" aria-labelledby="late-heading">
      <div className="row">
        <h2 id="late-heading">Late submission</h2>
        {request && <RequestBadge status={request.state} />}
      </div>

      {!request && (
        <form onSubmit={onSubmit} noValidate>
          <p>
            The deadline has passed and nothing has been submitted. You can ask your teacher for
            permission to submit late. You may send <strong>one</strong> request for this
            assignment.
          </p>
          <label>
            Why do you need extra time?
            <textarea
              rows={4}
              value={reason}
              maxLength={MAX + 200}
              disabled={create.isPending}
              onChange={(e) => setReason(e.target.value)}
              aria-describedby="late-reason-help"
            />
          </label>
          <p id="late-reason-help" className={`small counter ${tooShort ? 'bad' : 'muted'}`}>
            {trimmed} / {MAX} characters (at least {MIN})
          </p>
          {create.isError && <Notice kind="error">{errorMessage(create.error)}</Notice>}
          <div className="actions">
            <button type="submit" disabled={invalid || create.isPending}>
              {create.isPending ? 'Sending…' : 'Request late submission'}
            </button>
          </div>
        </form>
      )}

      {request && (
        <>
          {create.isSuccess && (
            <Notice kind="success">Your request was sent to your teacher.</Notice>
          )}
          <dl className="facts">
            <dt>Your reason</dt>
            <dd className="plain">{request.reason}</dd>
            <dt>Sent</dt>
            <dd>{formatIst(request.requested_at)}</dd>
            {request.decided_at && (
              <>
                <dt>Decision</dt>
                <dd>
                  {request.status === 'REJECTED' ? 'Rejected' : 'Approved'}
                  {request.decided_by_name ? ` by ${request.decided_by_name}` : ''} on{' '}
                  {formatIst(request.decided_at)}
                </dd>
              </>
            )}
            {request.decision_note && (
              <>
                <dt>Teacher&apos;s note</dt>
                <dd className="plain">{request.decision_note}</dd>
              </>
            )}
            {request.window_start && request.window_end && (
              <>
                <dt>Submission window</dt>
                <dd>
                  {formatIst(request.window_start)} to {formatIst(request.window_end)}{' '}
                  {request.state === 'APPROVED' && <Countdown iso={request.window_end} />}
                </dd>
              </>
            )}
          </dl>

          {request.state === 'PENDING' && (
            <Notice kind="info">
              Waiting for your teacher to decide. You cannot upload until the request is approved.
            </Notice>
          )}
          {request.state === 'APPROVED' && assignment.can_upload && (
            <Notice kind="success">
              Approved. Upload your file below before the window closes. It will be recorded as a
              late submission with the real time it is received.
            </Notice>
          )}
          {request.state === 'REJECTED' && (
            <Notice kind="error">
              Your request was rejected, so this assignment stays missing. A new request cannot be
              sent.
            </Notice>
          )}
          {request.state === 'EXPIRED' && (
            <Notice kind="error">
              The approved window has closed without an upload, so this assignment stays missing. A
              new request cannot be sent.
            </Notice>
          )}
          {request.state === 'USED' && (
            <Notice kind="info">Your late upload was received inside the approved window.</Notice>
          )}
        </>
      )}
    </section>
  )
}
