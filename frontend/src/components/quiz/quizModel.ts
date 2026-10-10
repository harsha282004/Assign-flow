import type {
  QuestionType,
  QuizDefinitionInput,
  QuizFacultyDetail,
  QuizQuestionInput,
} from '../../api/types'
import { istInputToIso } from '../../lib/time'

// Client-side checks are a convenience; the server validates and calculates everything again.
export const MAX_QUESTIONS = 50
export const MAX_OPTIONS = 8
export const TYPE_LABELS: Record<QuestionType, string> = {
  SINGLE_CHOICE: 'Single choice',
  MULTIPLE_SELECT: 'Multiple select',
  TRUE_FALSE: 'True / False',
}

export interface OptionDraft {
  key: string
  text: string
  correct: boolean
}
export interface QuestionDraft {
  key: string
  type: QuestionType
  text: string
  marks: string
  options: OptionDraft[]
}
export interface QuizDraft {
  slot: string
  title: string
  description: string
  instructions: string
  deadline: string
  duration: string
  questions: QuestionDraft[]
}

let counter = 0
export const newKey = () => `k${Date.now().toString(36)}${(counter++).toString(36)}`

export function blankOptions(type: QuestionType): OptionDraft[] {
  if (type === 'TRUE_FALSE')
    return [
      { key: newKey(), text: 'True', correct: false },
      { key: newKey(), text: 'False', correct: false },
    ]
  return [
    { key: newKey(), text: '', correct: false },
    { key: newKey(), text: '', correct: false },
  ]
}

export function blankQuestion(type: QuestionType = 'SINGLE_CHOICE'): QuestionDraft {
  return { key: newKey(), type, text: '', marks: '1', options: blankOptions(type) }
}

export function emptyDraft(): QuizDraft {
  return {
    slot: '',
    title: '',
    description: '',
    instructions: '',
    deadline: '',
    duration: '',
    questions: [],
  }
}

export function draftFromDetail(d: QuizFacultyDetail, deadlineInput: string): QuizDraft {
  return {
    slot: '',
    title: d.title,
    description: d.description ?? '',
    instructions: d.instructions,
    deadline: deadlineInput,
    duration: d.duration_minutes ? String(d.duration_minutes) : '',
    questions: d.questions.map((q) => ({
      key: newKey(),
      type: q.question_type,
      text: q.text,
      marks: String(q.marks),
      options: q.options.map((o) => ({ key: newKey(), text: o.text, correct: o.is_correct })),
    })),
  }
}

export function cloneQuestion(q: QuestionDraft): QuestionDraft {
  return {
    ...q,
    key: newKey(),
    options: q.options.map((o) => ({ ...o, key: newKey() })),
  }
}

/** Changing the type keeps the question text and marks but clears the correct answers (never guessed). */
export function changeType(q: QuestionDraft, type: QuestionType): QuestionDraft {
  if (type === q.type) return q
  if (type === 'TRUE_FALSE') return { ...q, type, options: blankOptions(type) }
  const keep = q.type === 'TRUE_FALSE' ? blankOptions(type) : q.options
  return { ...q, type, options: keep.map((o) => ({ ...o, correct: false })) }
}

export const marksOf = (q: QuestionDraft) => {
  const n = Number(q.marks)
  return Number.isInteger(n) && n >= 1 ? n : 0
}
export const totalMarks = (d: QuizDraft) => d.questions.reduce((sum, q) => sum + marksOf(q), 0)

export interface QuizErrors {
  fields: Partial<Record<'slot' | 'title' | 'instructions' | 'deadline' | 'duration', string>>
  questions: Record<string, string[]>
  /** Problem that only matters for publishing (no questions). */
  publish?: string
  count: number
}

export function validateQuestion(q: QuestionDraft): string[] {
  const errors: string[] = []
  if (!q.text.trim()) errors.push('Enter the question text.')
  if (q.text.length > 1000) errors.push('The question is at most 1000 characters.')
  const m = Number(q.marks)
  if (!Number.isInteger(m) || m < 1 || m > 100)
    errors.push('Marks must be a whole number from 1 to 100.')
  const texts = q.options.map((o) => o.text.trim())
  if (q.type !== 'TRUE_FALSE') {
    if (q.options.length < 2) errors.push('Add at least two answer options.')
    if (texts.some((t) => !t)) errors.push('Every answer option needs text.')
    if (new Set(texts.map((t) => t.toLowerCase())).size !== texts.length)
      errors.push('Answer options must be different from each other.')
  }
  const correct = q.options.filter((o) => o.correct).length
  if (q.type === 'MULTIPLE_SELECT' ? correct < 1 : correct !== 1)
    errors.push(
      q.type === 'MULTIPLE_SELECT'
        ? 'Mark at least one correct answer.'
        : 'Mark exactly one correct answer.',
    )
  return errors
}

export function validateDraft(d: QuizDraft, mode: 'create' | 'edit'): QuizErrors {
  const fields: QuizErrors['fields'] = {}
  if (mode === 'create' && !d.slot) fields.slot = 'Choose a class'
  if (!d.title.trim()) fields.title = 'Enter a title'
  if (!d.instructions.trim()) fields.instructions = 'Enter the instructions for students'
  if (!d.deadline) fields.deadline = 'Choose a deadline'
  else if (new Date(istInputToIso(d.deadline)).getTime() < Date.now() + 60_000)
    fields.deadline = 'The deadline must be at least 1 minute in the future'
  if (d.duration.trim()) {
    const n = Number(d.duration)
    if (!Number.isInteger(n) || n < 1 || n > 300) fields.duration = 'Whole minutes, 1 to 300'
  }
  const questions: Record<string, string[]> = {}
  for (const q of d.questions) {
    const e = validateQuestion(q)
    if (e.length) questions[q.key] = e
  }
  if (d.questions.length > MAX_QUESTIONS)
    fields.title = fields.title ?? `At most ${MAX_QUESTIONS} questions`
  const publish =
    d.questions.length === 0 ? 'Add at least one question to publish the quiz.' : undefined
  return {
    fields,
    questions,
    publish,
    count: Object.keys(fields).length + Object.keys(questions).length,
  }
}

export function toDefinition(d: QuizDraft): QuizDefinitionInput {
  return {
    title: d.title.trim(),
    description: d.description.trim() || null,
    instructions: d.instructions.trim(),
    deadline: istInputToIso(d.deadline),
    duration_minutes: d.duration.trim() ? Number(d.duration) : null,
    questions: d.questions.map((q): QuizQuestionInput => ({
      question_type: q.type,
      text: q.text.trim(),
      marks: Number(q.marks),
      options: q.options.map((o) => ({ text: o.text.trim(), is_correct: o.correct })),
    })),
  }
}

export function isDirty(d: QuizDraft): boolean {
  return !!(d.title || d.description || d.instructions || d.questions.length)
}
