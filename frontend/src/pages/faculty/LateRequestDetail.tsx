import { Link, useParams } from 'react-router-dom'
import { useLateRequest } from '../../api/queries'
import LateDecisionForm from '../../components/LateDecisionForm'
import VersionList from '../../components/VersionList'
import { ErrorState, LoadingState, RequestBadge, TimingBadge } from '../../components/ui'
import { formatIst } from '../../lib/time'

export default function LateRequestDetail() {
  const { id = '' } = useParams()
  const { data, isPending, isError, error, refetch } = useLateRequest(id)

  return (
    <>
      <p className="small">
        <Link to="/faculty/late-requests">← All late requests</Link>
      </p>
      {isPending && <LoadingState label="Loading request…" />}
      {isError && <ErrorState error={error} onRetry={() => void refetch()} />}
      {data && (
        <>
          <div className="row">
            <h1>{data.student.full_name}</h1>
            <RequestBadge status={data.state} />
          </div>
          <p className="muted">
            {data.student.login_id} ·{' '}
            <Link to={`/faculty/assignments/${data.assignment.id}`}>{data.assignment.title}</Link> ·{' '}
            {data.assignment.subject.code} {data.assignment.section.label}
          </p>
          <section className="card-item">
            <dl className="facts">
              <dt>Requested</dt>
              <dd>{formatIst(data.requested_at)}</dd>
              <dt>Deadline when requested</dt>
              <dd>{formatIst(data.deadline_at_request)}</dd>
              <dt>Current deadline</dt>
              <dd>{formatIst(data.current_deadline)}</dd>
              <dt>Student&apos;s status now</dt>
              <dd>
                <TimingBadge timing={data.submission_timing} />
              </dd>
            </dl>
            {data.submission_timing === 'PENDING' && data.state === 'PENDING' && (
              <p className="muted small">
                The deadline was extended after this request, so the student can already submit
                normally. Approving is not needed.
              </p>
            )}
            <h2>Reason</h2>
            <p className="plain">{data.reason}</p>
            <LateDecisionForm request={data} />
          </section>
          <section className="card-item">
            <h2>Submitted versions</h2>
            <VersionList versions={data.versions} />
          </section>
        </>
      )}
    </>
  )
}
