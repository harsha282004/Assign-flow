import { Link, useParams } from 'react-router-dom'
import { useStudentSubmission } from '../../api/queries'
import { ReviewForm, ReviewHistory } from '../../components/Reviews'
import Timeline, { WhyStatus } from '../../components/Timeline'
import VersionList from '../../components/VersionList'
import {
  Countdown,
  ErrorState,
  LoadingState,
  RequestBadge,
  ReviewBadge,
  TimingBadge,
} from '../../components/ui'
import { formatIst } from '../../lib/time'

export default function StudentSubmission() {
  const { id = '', studentId = '' } = useParams()
  const { data, isPending, isError, error, refetch } = useStudentSubmission(id, studentId)

  return (
    <>
      <p className="small">
        <Link to={`/faculty/assignments/${id}`}>← Back to the assignment</Link>
      </p>
      {isPending && <LoadingState label="Loading submission…" />}
      {isError && <ErrorState error={error} onRetry={() => void refetch()} />}
      {data && (
        <>
          <div className="row">
            <h1>{data.student.full_name}</h1>
            <span>
              <TimingBadge timing={data.timing} lateApproved={data.late_approved} />{' '}
              <ReviewBadge status={data.review_status} />{' '}
              <RequestBadge status={data.request_status} />{' '}
              {data.is_resubmitted && <span className="badge status-draft">Resubmitted</span>}
            </span>
          </div>
          <p className="muted">
            {data.student.login_id} · deadline {formatIst(data.deadline)}{' '}
            <Countdown iso={data.deadline} />
          </p>
          <section className="card-item">
            <h2>Submitted versions</h2>
            <VersionList versions={data.versions} />
          </section>
          <section className="card-item" aria-labelledby="review-heading">
            <h2 id="review-heading">Review</h2>
            <ReviewHistory reviews={data.reviews} />
            <ReviewForm assignmentId={id} data={data} />
          </section>
          <section className="card-item" aria-labelledby="timeline-heading">
            <h2 id="timeline-heading">Deadline Integrity Timeline</h2>
            <WhyStatus why={data.why_this_status} />
            <Timeline events={data.events} />
          </section>
        </>
      )}
    </>
  )
}
