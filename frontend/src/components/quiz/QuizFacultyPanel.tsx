import { Check } from 'lucide-react'
import { useState } from 'react'
import { errorMessage } from '../../api/client'
import {
  usePublishAssignment,
  useQuizFaculty,
  useQuizParticipation,
  useUpdateQuiz,
} from '../../api/queries'
import type { FacultyAssignmentDetail } from '../../api/types'
import { formatIst, isoToIstInput } from '../../lib/time'
import { ErrorState, LoadingState, Notice } from '../ui'
import '../../quiz.css'
import QuizBuilder from './QuizBuilder'
import { draftFromDetail, TYPE_LABELS } from './quizModel'

/** Faculty view of a quiz assignment: definition (with the answer key), draft actions and real participation. */
export default function QuizFacultyPanel({
  data,
  onNotice,
}: {
  data: FacultyAssignmentDetail
  onNotice: (m: string | null) => void
}) {
  const quiz = useQuizFaculty(data.id)
  const update = useUpdateQuiz(data.id)
  const publish = usePublishAssignment(data.id)
  const [editing, setEditing] = useState(false)
  const participation = useQuizParticipation(data.id, data.status !== 'DRAFT')

  if (quiz.isPending) return <LoadingState label="Loading quiz…" />
  if (quiz.isError) return <ErrorState error={quiz.error} onRetry={() => void quiz.refetch()} />
  const q = quiz.data

  return (
    <>
      <section className="card-item">
        <dl className="facts">
          <dt>Type</dt>
          <dd>Quiz</dd>
          <dt>Deadline</dt>
          <dd>{formatIst(q.deadline)}</dd>
          <dt>Questions</dt>
          <dd>
            {q.question_count} · {q.total_marks} total marks
          </dd>
          <dt>Time limit</dt>
          <dd>{q.duration_minutes ? `${q.duration_minutes} minutes` : 'None'}</dd>
          <dt>Published</dt>
          <dd>{q.published_at ? formatIst(q.published_at) : 'Not published yet'}</dd>
        </dl>
        {q.description && <p className="plain">{q.description}</p>}
        <h2>Instructions</h2>
        <p className="plain">{q.instructions}</p>
      </section>

      {data.status === 'DRAFT' && (
        <section className="card-item">
          <h2>This quiz is a draft</h2>
          <p className="muted">
            Students cannot see it until you publish it. Published quizzes cannot be edited.
          </p>
          {publish.isError && <Notice kind="error">{errorMessage(publish.error)}</Notice>}
          {!editing && (
            <div className="actions">
              <button
                disabled={publish.isPending}
                onClick={() =>
                  publish.mutate(undefined, { onSuccess: () => onNotice('Quiz published.') })
                }
              >
                {publish.isPending ? 'Publishing…' : 'Publish'}
              </button>
              <button className="secondary" onClick={() => setEditing(true)}>
                Edit quiz
              </button>
            </div>
          )}
          {editing && (
            <>
              <QuizBuilder
                mode="edit"
                initial={draftFromDetail(q, isoToIstInput(q.deadline))}
                busy={update.isPending}
                error={update.isError ? errorMessage(update.error) : null}
                onSubmit={(def) =>
                  update.mutate(def, {
                    onSuccess: () => {
                      setEditing(false)
                      onNotice('Quiz saved.')
                    },
                  })
                }
              />
              <button className="secondary" onClick={() => setEditing(false)}>
                Cancel
              </button>
            </>
          )}
        </section>
      )}

      {!editing && (
        <section className="card-item">
          <h2>Questions and answer key</h2>
          {q.questions.length === 0 && <p className="muted">No questions yet.</p>}
          <ol className="qz-questions">
            {q.questions.map((qq, i) => (
              <li key={qq.id} className={`qz-card qz-${qq.question_type.toLowerCase()}`}>
                <div className="qz-card-head">
                  <span className="qz-number">Question {i + 1}</span>
                  <span className="qz-type-pill">{TYPE_LABELS[qq.question_type]}</span>
                  <span className="muted small">
                    {qq.marks} mark{qq.marks === 1 ? '' : 's'}
                  </span>
                </div>
                <p className="plain">{qq.text}</p>
                <ul className="plain-list">
                  {qq.options.map((o) => (
                    <li key={o.id}>
                      {o.is_correct ? (
                        <strong>
                          <Check size={14} aria-hidden="true" /> {o.text}{' '}
                          <span className="sr-only">(correct)</span>
                        </strong>
                      ) : (
                        o.text
                      )}
                    </li>
                  ))}
                </ul>
              </li>
            ))}
          </ol>
        </section>
      )}

      {data.status !== 'DRAFT' && (
        <section className="card-item">
          <h2>Participation</h2>
          {participation.isPending && <LoadingState label="Loading participation…" />}
          {participation.isError && (
            <ErrorState error={participation.error} onRetry={() => void participation.refetch()} />
          )}
          {participation.data && (
            <>
              <p className="muted">
                {participation.data.submitted} of {participation.data.expected_students} submitted ·{' '}
                {participation.data.started} started
                {participation.data.average_score !== null &&
                  ` · average ${participation.data.average_score} / ${participation.data.total_marks}`}
              </p>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Student</th>
                      <th>Status</th>
                      <th>Submitted</th>
                      <th>Score</th>
                    </tr>
                  </thead>
                  <tbody>
                    {participation.data.participants.map((p) => (
                      <tr key={p.student_id}>
                        <td>
                          {p.full_name} <span className="muted small">{p.login_id}</span>
                        </td>
                        <td>
                          {p.status === 'NOT_STARTED'
                            ? 'Not started'
                            : p.status === 'IN_PROGRESS'
                              ? 'In progress'
                              : p.timed_out
                                ? 'Submitted (time up)'
                                : 'Submitted'}
                        </td>
                        <td>{p.submitted_at ? formatIst(p.submitted_at) : '—'}</td>
                        <td>{p.score !== null ? `${p.score} / ${p.max_score}` : '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </section>
      )}
    </>
  )
}
