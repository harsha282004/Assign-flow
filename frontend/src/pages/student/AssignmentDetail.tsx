import { Link, useParams } from 'react-router-dom'
import { useStudentAssignment } from '../../api/queries'
import StudentQuiz from '../../components/quiz/StudentQuiz'
import ReferenceMaterials from '../../components/ReferenceMaterials'
import { ReviewHistory } from '../../components/Reviews'
import Timeline, { WhyStatus } from '../../components/Timeline'
import { Countdown, ErrorState, LoadingState, ReviewBadge, TimingBadge } from '../../components/ui'
import LateRequestPanel from '../../components/LateRequestPanel'
import SubmissionPanel from '../../components/SubmissionPanel'
import { formatIst } from '../../lib/time'

/** Quizzes have their own page; the student's assignment list links every item here and the type decides. */
export default function StudentAssignmentDetail() {
  const { id = '' } = useParams()
  const { data } = useStudentAssignment(id)
  if (data?.assignment_type === 'QUIZ') {
    return (
      <>
        <p className="small">
          <Link to="/student/assignments">← All assignments</Link>
        </p>
        <StudentQuiz id={id} />
      </>
    )
  }
  return <FileAssignmentDetail />
}

function FileAssignmentDetail() {
  const { id = '' } = useParams()
  const { data, isPending, isError, error, refetch } = useStudentAssignment(id)

  return (
    <>
      <p className="small">
        <Link to="/student/assignments">← All assignments</Link>
      </p>
      {isPending && <LoadingState label="Loading assignment…" />}
      {isError && <ErrorState error={error} onRetry={() => void refetch()} />}
      {data && (
        <>
          <div className="row">
            <h1>{data.title}</h1>
            <TimingBadge timing={data.timing} lateApproved={data.late_approved} />
          </div>
          <p className="muted">
            {data.subject.code} {data.subject.name}
            {data.faculty_name ? ` · ${data.faculty_name}` : ''} · {data.section.label}
          </p>
          {data.assignment_state === 'ARCHIVED' && (
            <div className="archived-banner" role="status">
              <p>
                <strong>This assignment has been archived.</strong> It no longer accepts submissions
                or late requests. Your submissions, feedback and files below are kept.
              </p>
            </div>
          )}
          <section className="card-item">
            <dl className="facts">
              <dt>Deadline</dt>
              <dd>
                {formatIst(data.deadline)} <Countdown iso={data.deadline} />
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
              <dd>{formatIst(data.published_at)}</dd>
            </dl>
          </section>
          <section className="card-item" aria-labelledby="materials-heading">
            <h2 id="materials-heading">Assignment Instructions &amp; Reference Materials</h2>
            <h3 className="subhead">Instructions</h3>
            <p className="plain">{data.instructions}</p>
            <h3 className="subhead">Reference materials</h3>
            <ReferenceMaterials assignmentId={data.id} attachments={data.attachments} />
          </section>
          <LateRequestPanel assignment={data} />
          <SubmissionPanel assignment={data} />
          <section className="card-item" aria-labelledby="feedback-heading">
            <div className="row">
              <h2 id="feedback-heading">Teacher&apos;s review</h2>
              <ReviewBadge status={data.review_status} />
            </div>
            <ReviewHistory reviews={data.reviews} />
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
