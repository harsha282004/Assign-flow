import { useQuery } from '@tanstack/react-query'
import { Link, Navigate, useParams } from 'react-router-dom'
import { api } from '../../api/client'
import { LoadingState } from '../../components/ui'

/** Target of a "new submission" notification: resolves the submission on the server (which checks that it belongs to
 *  one of my assignments) and opens the existing student-submission page. Anything else shows a safe message. */
export default function SubmissionLink() {
  const { submissionId = '' } = useParams()
  const { data, isPending, isError } = useQuery({
    queryKey: ['faculty', 'submission-locator', submissionId],
    retry: false,
    gcTime: 0,
    queryFn: async () =>
      (
        await api.get<{ assignment_id: string; student_id: string }>(
          `/faculty/submissions/${submissionId}/locator`,
        )
      ).data,
  })
  if (isPending) return <LoadingState label="Opening submission…" />
  if (isError)
    return (
      <section className="card-item">
        <h1>Submission not available</h1>
        <p className="muted">This submission no longer exists or is not one of your assignments.</p>
        <Link to="/faculty/assignments">← All assignments</Link>
      </section>
    )
  return (
    <Navigate
      to={`/faculty/assignments/${data.assignment_id}/students/${data.student_id}`}
      replace
    />
  )
}
