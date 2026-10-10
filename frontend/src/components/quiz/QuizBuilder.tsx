import { ArrowDown, ArrowUp, Copy, Plus, Trash2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import type { Me, QuestionType } from '../../api/types'
import { nowIstInput } from '../../lib/time'
import { Notice } from '../ui'
import '../../quiz.css'
import {
  blankOptions,
  blankQuestion,
  changeType,
  cloneQuestion,
  isDirty,
  MAX_OPTIONS,
  MAX_QUESTIONS,
  newKey,
  totalMarks,
  toDefinition,
  TYPE_LABELS,
  validateDraft,
  type QuestionDraft,
  type QuizDraft,
} from './quizModel'
import type { QuizDefinitionInput } from '../../api/types'
import QuizPreview from './QuizPreview'

interface Props {
  mode: 'create' | 'edit'
  teaching?: Me['teaching']
  initial: QuizDraft
  busy: boolean
  error: string | null
  /** Called with a fully validated definition. `publish` is true for "Create and publish". */
  onSubmit: (definition: QuizDefinitionInput, publish: boolean, slot: string) => void
}

export default function QuizBuilder({ mode, teaching, initial, busy, error, onSubmit }: Props) {
  const [draft, setDraft] = useState<QuizDraft>(initial)
  const [showErrors, setShowErrors] = useState(false)
  const [preview, setPreview] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null)

  // Leaving the page with unsaved questions asks first (the builder unmounts after a successful save).
  const dirty = isDirty(draft)
  useEffect(() => {
    if (!dirty) return
    const warn = (e: BeforeUnloadEvent) => {
      e.preventDefault()
    }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [dirty])

  const errors = validateDraft(draft, mode)
  const total = totalMarks(draft)
  const set = <K extends keyof QuizDraft>(k: K, v: QuizDraft[K]) =>
    setDraft((d) => ({ ...d, [k]: v }))
  const updateQuestion = (key: string, fn: (q: QuestionDraft) => QuestionDraft) =>
    setDraft((d) => ({ ...d, questions: d.questions.map((q) => (q.key === key ? fn(q) : q)) }))

  function move(index: number, delta: -1 | 1) {
    setDraft((d) => {
      const next = [...d.questions]
      const target = index + delta
      if (target < 0 || target >= next.length) return d
      ;[next[index], next[target]] = [next[target], next[index]]
      return { ...d, questions: next }
    })
  }

  function submit(publish: boolean) {
    setShowErrors(true)
    if (errors.count > 0 || (publish && errors.publish)) return
    onSubmit(toDefinition(draft), publish, draft.slot)
  }

  const fieldError = (k: keyof typeof errors.fields) =>
    showErrors && errors.fields[k] ? <span className="field-error">{errors.fields[k]}</span> : null

  return (
    <form
      className="qz-builder"
      noValidate
      onSubmit={(e) => {
        e.preventDefault()
        submit(true)
      }}
    >
      {mode === 'create' && (
        <label>
          Class (subject · section)
          <select
            value={draft.slot}
            aria-invalid={showErrors && !!errors.fields.slot}
            onChange={(e) => set('slot', e.target.value)}
          >
            <option value="">Choose a class…</option>
            {(teaching ?? []).map((t) => (
              <option
                key={`${t.subject.id}|${t.section.id}`}
                value={`${t.subject.id}|${t.section.id}`}
              >
                {t.subject.code} {t.subject.name} · {t.section.label}
              </option>
            ))}
          </select>
          {fieldError('slot')}
        </label>
      )}
      <label>
        Quiz title
        <input
          type="text"
          maxLength={150}
          value={draft.title}
          aria-invalid={showErrors && !!errors.fields.title}
          onChange={(e) => set('title', e.target.value)}
        />
        {fieldError('title')}
      </label>
      <label>
        Instructions for students
        <textarea
          rows={3}
          maxLength={5000}
          value={draft.instructions}
          aria-invalid={showErrors && !!errors.fields.instructions}
          onChange={(e) => set('instructions', e.target.value)}
        />
        {fieldError('instructions')}
      </label>
      <label>
        Description (optional)
        <textarea
          rows={2}
          maxLength={2000}
          value={draft.description}
          onChange={(e) => set('description', e.target.value)}
        />
      </label>
      <div className="qz-grid">
        <label>
          Deadline (IST)
          <input
            type="datetime-local"
            min={nowIstInput()}
            value={draft.deadline}
            aria-invalid={showErrors && !!errors.fields.deadline}
            onChange={(e) => set('deadline', e.target.value)}
          />
          {fieldError('deadline')}
        </label>
        <label>
          Time limit in minutes (optional)
          <input
            type="number"
            min={1}
            max={300}
            placeholder="No time limit"
            value={draft.duration}
            aria-invalid={showErrors && !!errors.fields.duration}
            onChange={(e) => set('duration', e.target.value)}
          />
          {fieldError('duration')}
        </label>
      </div>

      <div className="qz-summary" role="status" aria-live="polite">
        <span>
          <strong>{draft.questions.length}</strong> question
          {draft.questions.length === 1 ? '' : 's'}
        </span>
        <span>
          <strong>{total}</strong> total marks
        </span>
        <button
          type="button"
          className="secondary compact"
          aria-pressed={preview}
          onClick={() => setPreview((p) => !p)}
        >
          {preview ? 'Back to editing' : 'Preview as student'}
        </button>
      </div>

      {preview ? (
        <QuizPreview draft={draft} />
      ) : (
        <>
          {draft.questions.length === 0 && (
            <div className="qz-empty">
              <strong>No questions yet</strong>
              <p className="muted">
                Add single-choice, multiple-select or true / false questions. You can reorder them
                and set the marks for each.
              </p>
            </div>
          )}
          <ol className="qz-questions">
            {draft.questions.map((q, i) => {
              const qErrors = errors.questions[q.key] ?? []
              return (
                <li
                  key={q.key}
                  className={`qz-card qz-${q.type.toLowerCase()}`}
                  aria-label={`Question ${i + 1}`}
                >
                  <div className="qz-card-head">
                    <span className="qz-number">Question {i + 1}</span>
                    <span className="qz-type-pill">{TYPE_LABELS[q.type]}</span>
                    <span className="qz-tools">
                      <button
                        type="button"
                        className="secondary compact"
                        onClick={() => move(i, -1)}
                        disabled={i === 0}
                        aria-label={`Move question ${i + 1} up`}
                      >
                        <ArrowUp size={16} aria-hidden="true" />
                      </button>
                      <button
                        type="button"
                        className="secondary compact"
                        onClick={() => move(i, 1)}
                        disabled={i === draft.questions.length - 1}
                        aria-label={`Move question ${i + 1} down`}
                      >
                        <ArrowDown size={16} aria-hidden="true" />
                      </button>
                      <button
                        type="button"
                        className="secondary compact"
                        disabled={draft.questions.length >= MAX_QUESTIONS}
                        onClick={() =>
                          setDraft((d) => {
                            const next = [...d.questions]
                            next.splice(i + 1, 0, cloneQuestion(q))
                            return { ...d, questions: next }
                          })
                        }
                        aria-label={`Duplicate question ${i + 1}`}
                      >
                        <Copy size={16} aria-hidden="true" />
                      </button>
                      {confirmDelete === q.key ? (
                        <span className="qz-confirm" role="group" aria-label="Confirm delete">
                          Delete question {i + 1}?
                          <button
                            type="button"
                            className="secondary compact danger"
                            onClick={() => {
                              set(
                                'questions',
                                draft.questions.filter((x) => x.key !== q.key),
                              )
                              setConfirmDelete(null)
                            }}
                          >
                            Yes, delete
                          </button>
                          <button
                            type="button"
                            className="secondary compact"
                            onClick={() => setConfirmDelete(null)}
                          >
                            Keep
                          </button>
                        </span>
                      ) : (
                        <button
                          type="button"
                          className="secondary compact danger"
                          onClick={() => setConfirmDelete(q.key)}
                          aria-label={`Delete question ${i + 1}`}
                        >
                          <Trash2 size={16} aria-hidden="true" />
                        </button>
                      )}
                    </span>
                  </div>

                  <label>
                    Question type
                    <select
                      value={q.type}
                      onChange={(e) =>
                        updateQuestion(q.key, (x) => changeType(x, e.target.value as QuestionType))
                      }
                    >
                      {(Object.keys(TYPE_LABELS) as QuestionType[]).map((t) => (
                        <option key={t} value={t}>
                          {TYPE_LABELS[t]}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    Question
                    <textarea
                      rows={2}
                      maxLength={1000}
                      value={q.text}
                      aria-invalid={showErrors && qErrors.some((e) => e.includes('question text'))}
                      onChange={(e) =>
                        updateQuestion(q.key, (x) => ({ ...x, text: e.target.value }))
                      }
                    />
                  </label>

                  <fieldset className="qz-options">
                    <legend>
                      Answer options —{' '}
                      {q.type === 'MULTIPLE_SELECT'
                        ? 'tick every correct answer'
                        : 'select the correct answer'}
                    </legend>
                    {q.options.map((o, oi) => (
                      <div key={o.key} className="qz-option">
                        <input
                          type={q.type === 'MULTIPLE_SELECT' ? 'checkbox' : 'radio'}
                          name={`correct-${q.key}`}
                          checked={o.correct}
                          aria-label={`Option ${oi + 1} is correct`}
                          onChange={(e) =>
                            updateQuestion(q.key, (x) => ({
                              ...x,
                              options: x.options.map((p) =>
                                p.key === o.key
                                  ? { ...p, correct: e.target.checked }
                                  : q.type === 'MULTIPLE_SELECT'
                                    ? p
                                    : { ...p, correct: false },
                              ),
                            }))
                          }
                        />
                        <input
                          type="text"
                          maxLength={300}
                          value={o.text}
                          readOnly={q.type === 'TRUE_FALSE'}
                          placeholder={`Option ${oi + 1}`}
                          aria-label={`Option ${oi + 1} text`}
                          onChange={(e) =>
                            updateQuestion(q.key, (x) => ({
                              ...x,
                              options: x.options.map((p) =>
                                p.key === o.key ? { ...p, text: e.target.value } : p,
                              ),
                            }))
                          }
                        />
                        {q.type !== 'TRUE_FALSE' && (
                          <button
                            type="button"
                            className="secondary compact"
                            disabled={q.options.length <= 2}
                            aria-label={`Remove option ${oi + 1}`}
                            onClick={() =>
                              updateQuestion(q.key, (x) => ({
                                ...x,
                                options: x.options.filter((p) => p.key !== o.key),
                              }))
                            }
                          >
                            <Trash2 size={14} aria-hidden="true" />
                          </button>
                        )}
                      </div>
                    ))}
                    {q.type !== 'TRUE_FALSE' && (
                      <button
                        type="button"
                        className="secondary compact"
                        disabled={q.options.length >= MAX_OPTIONS}
                        onClick={() =>
                          updateQuestion(q.key, (x) => ({
                            ...x,
                            options: [...x.options, { ...blankOptions(x.type)[0], key: newKey() }],
                          }))
                        }
                      >
                        <Plus size={14} aria-hidden="true" /> Add option
                      </button>
                    )}
                  </fieldset>

                  <label className="qz-marks">
                    Marks
                    <input
                      type="number"
                      min={1}
                      max={100}
                      value={q.marks}
                      aria-invalid={showErrors && qErrors.some((e) => e.startsWith('Marks'))}
                      onChange={(e) =>
                        updateQuestion(q.key, (x) => ({ ...x, marks: e.target.value }))
                      }
                    />
                  </label>
                  {showErrors && qErrors.length > 0 && (
                    <ul className="qz-errors" role="alert">
                      {qErrors.map((e) => (
                        <li key={e} className="field-error">
                          {e}
                        </li>
                      ))}
                    </ul>
                  )}
                </li>
              )
            })}
          </ol>
          <button
            type="button"
            className="secondary"
            disabled={draft.questions.length >= MAX_QUESTIONS}
            onClick={() => set('questions', [...draft.questions, blankQuestion()])}
          >
            <Plus size={16} aria-hidden="true" /> Add question
          </button>
        </>
      )}

      {showErrors && errors.count > 0 && (
        <Notice kind="error">
          Please fix {errors.count} problem{errors.count === 1 ? '' : 's'} above before saving.
        </Notice>
      )}
      {showErrors && errors.count === 0 && errors.publish && (
        <Notice kind="error">{errors.publish} You can still save it as a draft.</Notice>
      )}
      {error && <Notice kind="error">{error}</Notice>}

      <div className="actions">
        {mode === 'create' ? (
          <>
            <button type="submit" disabled={busy}>
              {busy ? 'Saving…' : 'Create and publish'}
            </button>
            <button
              type="button"
              className="secondary"
              disabled={busy}
              onClick={() => submit(false)}
            >
              Save as draft
            </button>
          </>
        ) : (
          <button type="button" disabled={busy} onClick={() => submit(false)}>
            {busy ? 'Saving…' : 'Save changes'}
          </button>
        )}
      </div>
    </form>
  )
}
