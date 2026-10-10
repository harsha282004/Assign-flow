import { TYPE_LABELS, marksOf, type QuizDraft } from './quizModel'

/** How the quiz will look to students (inputs are disabled; nothing is stored). */
export default function QuizPreview({ draft }: { draft: QuizDraft }) {
  return (
    <section className="qz-preview" aria-label="Student preview">
      <p className="muted small">
        Preview: this is what students will see. Correct answers are never shown to students while
        they take the quiz.
      </p>
      <h2>{draft.title || 'Untitled quiz'}</h2>
      {draft.description && <p className="plain">{draft.description}</p>}
      <p className="plain">{draft.instructions}</p>
      {draft.questions.length === 0 && <p className="muted">There are no questions yet.</p>}
      <ol className="qz-questions">
        {draft.questions.map((q, i) => (
          <li key={q.key} className="qz-card">
            <div className="qz-card-head">
              <span className="qz-number">Question {i + 1}</span>
              <span className="qz-type-pill">{TYPE_LABELS[q.type]}</span>
              <span className="muted small">
                {marksOf(q)} mark{marksOf(q) === 1 ? '' : 's'}
              </span>
            </div>
            <p className="plain">{q.text || '(no question text)'}</p>
            <div className="qz-choices">
              {q.options.map((o) => (
                <label key={o.key} className="check">
                  <input
                    type={q.type === 'MULTIPLE_SELECT' ? 'checkbox' : 'radio'}
                    disabled
                    name={`pv-${q.key}`}
                  />
                  {o.text || '(empty option)'}
                </label>
              ))}
            </div>
          </li>
        ))}
      </ol>
    </section>
  )
}
