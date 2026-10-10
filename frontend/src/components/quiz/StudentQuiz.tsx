import { useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { errorMessage } from '../../api/client'
import {
  saveQuizAnswers,
  useQuizResult,
  useQuizStudent,
  useStartQuizAttempt,
  useSubmitQuiz,
} from '../../api/queries'
import type { QuizResult, QuizStudentView } from '../../api/types'
import { formatIst } from '../../lib/time'
import { Countdown, ErrorState, LoadingState, Notice } from '../ui'
import '../../quiz.css'
import { TYPE_LABELS } from './quizModel'

type Answers = Record<string, string[]>

/** The whole student side of a quiz: details -> attempt -> result. The server decides every state. */
export default function StudentQuiz({ id }: { id: string }) {
  const { data, isPending, isError, error, refetch } = useQuizStudent(id)
  const start = useStartQuizAttempt(id)
  const [justSubmitted, setJustSubmitted] = useState<QuizResult | null>(null)

  if (isPending) return <LoadingState label="Loading quiz…" />
  if (isError) return <ErrorState error={error} onRetry={() => void refetch()} />

  const attempt = data.attempt
  return (
    <>
      <div className="row">
        <h1>{data.title}</h1>
        <span className="badge">Quiz</span>
      </div>
      <p className="muted">
        {data.subject.code} {data.subject.name}
        {data.faculty_name ? ` · ${data.faculty_name}` : ''} · {data.section.label}
      </p>

      {attempt?.status === 'SUBMITTED' ? (
        <ResultView view={data} attemptId={attempt.id} fresh={justSubmitted} />
      ) : attempt?.status === 'IN_PROGRESS' && data.questions ? (
        <Taker view={data} onSubmitted={setJustSubmitted} />
      ) : (
        <section className="card-item">
          <dl className="facts">
            <dt>Deadline</dt>
            <dd>
              {formatIst(data.deadline)} <Countdown iso={data.deadline} />
            </dd>
            <dt>Questions</dt>
            <dd>{data.question_count}</dd>
            <dt>Total marks</dt>
            <dd>{data.total_marks}</dd>
            <dt>Time limit</dt>
            <dd>
              {data.duration_minutes ? `${data.duration_minutes} minutes once you start` : 'None'}
            </dd>
            <dt>Attempts</dt>
            <dd>One attempt only</dd>
          </dl>
          {data.description && <p className="plain">{data.description}</p>}
          <h2>Instructions</h2>
          <p className="plain">{data.instructions}</p>
          {data.blocked_reason === 'DEADLINE_PASSED' && (
            <Notice kind="error">
              The deadline for this quiz has passed. It can no longer be attempted.
            </Notice>
          )}
          {data.blocked_reason === 'ARCHIVED' && (
            <Notice kind="error">
              This quiz has been archived and no longer accepts attempts.
            </Notice>
          )}
          {start.isError && <Notice kind="error">{errorMessage(start.error)}</Notice>}
          {data.can_attempt && (
            <div className="actions">
              <button disabled={start.isPending} onClick={() => start.mutate()}>
                {start.isPending ? 'Starting…' : 'Attempt Quiz'}
              </button>
            </div>
          )}
        </section>
      )}
    </>
  )
}

function useRemaining(expiresAt: string) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const t = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(t)
  }, [])
  return Math.max(0, new Date(expiresAt).getTime() - now)
}

function fmtClock(ms: number) {
  const total = Math.floor(ms / 1000)
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = total % 60
  const mm = String(m).padStart(2, '0')
  const ss = String(s).padStart(2, '0')
  return h > 0 ? `${h}:${mm}:${ss}` : `${mm}:${ss}`
}

function Taker({
  view,
  onSubmitted,
}: {
  view: QuizStudentView
  onSubmitted: (r: QuizResult) => void
}) {
  const attempt = view.attempt!
  const questions = view.questions!
  const [answers, setAnswers] = useState<Answers>(attempt.answers)
  const [index, setIndex] = useState(0)
  const [saveState, setSaveState] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle')
  const [confirming, setConfirming] = useState(false)
  const submit = useSubmitQuiz(view.assignment_id, attempt.id)
  const remaining = useRemaining(attempt.expires_at)
  const answersRef = useRef(answers)
  answersRef.current = answers
  const q = questions[index]

  const payload = (a: Answers) =>
    questions.map((x) => ({ question_id: x.id, option_ids: a[x.id] ?? [] }))

  // Every change is saved, in order (one request at a time, so a quick second click can never overtake the first and
  // a change to question 2 never cancels the save of question 1). Failures are shown, never hidden.
  const queue = useRef<Promise<unknown>>(Promise.resolve())
  const pending = useRef(0)
  function change(questionId: string, next: string[]) {
    setAnswers((a) => ({ ...a, [questionId]: next }))
    setSaveState('saving')
    pending.current += 1
    queue.current = queue.current.then(() =>
      saveQuizAnswers(attempt.id, [{ question_id: questionId, option_ids: next }])
        .then(() => {
          pending.current -= 1
          if (pending.current === 0) setSaveState('saved')
        })
        .catch(() => {
          pending.current -= 1
          setSaveState('error')
        }),
    )
  }

  function finish() {
    if (submit.isPending || submit.isSuccess) return // one submission at a time
    submit.mutate(payload(answersRef.current), { onSuccess: onSubmitted })
  }

  // When the displayed clock reaches zero, ask the SERVER what happened: it closes an expired attempt with the answers
  // it has saved, and the page then switches to the result. A client clock that runs fast therefore never ends a quiz
  // early; the quiz simply continues and the check repeats.
  const qc = useQueryClient()
  useEffect(() => {
    if (remaining > 0) return
    const check = () =>
      void qc.invalidateQueries({ queryKey: ['student', 'quiz', view.assignment_id] })
    check()
    const t = window.setInterval(check, 5000)
    return () => window.clearInterval(t)
  }, [remaining, qc, view.assignment_id])

  const answered = useMemo(
    () => questions.filter((x) => (answers[x.id] ?? []).length > 0).length,
    [questions, answers],
  )
  const unanswered = questions.length - answered
  const low = remaining < 5 * 60 * 1000

  return (
    <div className="qz-take">
      <aside className="qz-nav" aria-label="Quiz navigation">
        <div>
          <div className="muted small">Time left</div>
          <div className={`qz-timer${low ? ' low' : ''}`} role="timer">
            {fmtClock(remaining)}
          </div>
          <div className="muted small">Ends {formatIst(attempt.expires_at)}</div>
        </div>
        <div>
          <div className="muted small">
            {answered} of {questions.length} answered
          </div>
          <div className="qz-progress" aria-hidden="true">
            <div style={{ width: `${(answered / questions.length) * 100}%` }} />
          </div>
        </div>
        <div className="qz-nav-grid">
          {questions.map((x, i) => (
            <button
              key={x.id}
              type="button"
              className={`secondary compact${(answers[x.id] ?? []).length > 0 ? ' answered' : ''}`}
              aria-current={i === index}
              aria-label={`Question ${i + 1}${(answers[x.id] ?? []).length > 0 ? ' (answered)' : ''}`}
              onClick={() => setIndex(i)}
            >
              {i + 1}
            </button>
          ))}
        </div>
        <div className="muted small" role="status" aria-live="polite">
          {saveState === 'saving' && 'Saving…'}
          {saveState === 'saved' && 'All answers saved'}
          {saveState === 'error' && 'Could not save the last answer. Check your connection.'}
        </div>
      </aside>

      <section className="card-item">
        <div className="qz-card-head">
          <span className="qz-number">
            Question {index + 1} of {questions.length}
          </span>
          <span className="qz-type-pill">{TYPE_LABELS[q.question_type]}</span>
          <span className="muted small">
            {q.marks} mark{q.marks === 1 ? '' : 's'}
          </span>
        </div>
        <p className="plain">{q.text}</p>
        {q.question_type === 'MULTIPLE_SELECT' && (
          <p className="muted small">Select all that apply.</p>
        )}
        <div
          className="qz-choices"
          role={q.question_type === 'MULTIPLE_SELECT' ? 'group' : 'radiogroup'}
          aria-label={q.text}
        >
          {q.options.map((o) => {
            const chosen = (answers[q.id] ?? []).includes(o.id)
            const multi = q.question_type === 'MULTIPLE_SELECT'
            return (
              <label key={o.id} className="qz-choice">
                <input
                  type={multi ? 'checkbox' : 'radio'}
                  name={`q-${q.id}`}
                  checked={chosen}
                  onChange={() =>
                    change(
                      q.id,
                      multi
                        ? chosen
                          ? (answers[q.id] ?? []).filter((x) => x !== o.id)
                          : [...(answers[q.id] ?? []), o.id]
                        : [o.id],
                    )
                  }
                />
                {o.text}
              </label>
            )
          })}
        </div>
        {submit.isError && <Notice kind="error">{errorMessage(submit.error)}</Notice>}
        <div className="actions">
          <button
            type="button"
            className="secondary"
            disabled={index === 0}
            onClick={() => setIndex(index - 1)}
          >
            Previous
          </button>
          {index < questions.length - 1 ? (
            <button type="button" onClick={() => setIndex(index + 1)}>
              Next
            </button>
          ) : (
            <button type="button" disabled={submit.isPending} onClick={() => setConfirming(true)}>
              Submit quiz
            </button>
          )}
          {index < questions.length - 1 && (
            <button
              type="button"
              className="secondary"
              disabled={submit.isPending}
              onClick={() => setConfirming(true)}
            >
              Submit quiz
            </button>
          )}
        </div>
      </section>

      {confirming && (
        <div className="qz-dialog-backdrop">
          <div
            className="qz-dialog"
            role="alertdialog"
            aria-modal="true"
            aria-labelledby="qz-confirm-h"
          >
            <h2 id="qz-confirm-h">Submit your quiz?</h2>
            <p>
              {unanswered > 0
                ? `${unanswered} question${unanswered === 1 ? ' is' : 's are'} unanswered and will score zero. `
                : 'You have answered every question. '}
              You can only submit once and cannot change your answers afterwards.
            </p>
            <div className="actions">
              <button
                type="button"
                disabled={submit.isPending}
                onClick={() => {
                  setConfirming(false)
                  finish()
                }}
              >
                {submit.isPending ? 'Submitting…' : 'Yes, submit'}
              </button>
              <button type="button" className="secondary" onClick={() => setConfirming(false)}>
                Keep working
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function ResultView({
  view,
  attemptId,
  fresh,
}: {
  view: QuizStudentView
  attemptId: string
  fresh: QuizResult | null
}) {
  const query = useQuizResult(fresh ? undefined : attemptId)
  const result = fresh ?? query.data
  if (!result && query.isPending) return <LoadingState label="Loading result…" />
  if (!result) return <ErrorState error={query.error} onRetry={() => void query.refetch()} />
  return (
    <>
      <section className="card-item">
        <p className="muted">
          Submitted {formatIst(result.submitted_at)}
          {result.timed_out ? ' · time ran out, your saved answers were submitted' : ''}
        </p>
        <div className="qz-score" aria-label="Your score">
          {result.score} / {result.max_score}
        </div>
        {!result.answers_released && (
          <p className="muted">
            Correct answers are shown after the deadline ({formatIst(view.deadline)}).
          </p>
        )}
        <p className="small">
          <Link to="/student/assignments">← All assignments</Link>
        </p>
      </section>
      <ol className="qz-questions">
        {result.questions.map((q, i) => (
          <li key={q.question_id} className="qz-card">
            <div className="qz-card-head">
              <span className="qz-number">Question {i + 1}</span>
              <span className="qz-type-pill">{TYPE_LABELS[q.question_type]}</span>
              <span className="muted small">
                {q.awarded} / {q.marks}
              </span>
            </div>
            <p className="plain">{q.text}</p>
            <div className="qz-choices">
              {q.options.map((o) => {
                const chosen = q.selected_option_ids.includes(o.id)
                const correct = q.correct_option_ids?.includes(o.id)
                const cls =
                  q.correct_option_ids === null ? '' : correct ? ' right' : chosen ? ' wrong' : ''
                return (
                  <div key={o.id} className={`qz-choice${cls}`}>
                    {chosen ? '● ' : '○ '}
                    {o.text}
                    {chosen && <span className="sr-only"> (your answer)</span>}
                    {correct && <span className="sr-only"> (correct answer)</span>}
                  </div>
                )
              })}
            </div>
          </li>
        ))}
      </ol>
    </>
  )
}
