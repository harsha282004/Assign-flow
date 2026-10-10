import { zodResolver } from '@hookform/resolvers/zod'
import { useRef, useState } from 'react'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { ALLOWED_TYPES, type AllowedType, type Me } from '../api/types'
import { isoToIstInput, istInputToIso, nowIstInput } from '../lib/time'
import {
  checkReferenceFile,
  formatSize,
  MAX_REFERENCE_FILES,
  MAX_REFERENCE_MB,
} from './ReferenceMaterials'
import { Notice } from './ui'

// Client-side validation is a convenience only; the server validates everything again.
function makeSchema(mode: 'create' | 'edit') {
  return z.object({
    slot: mode === 'create' ? z.string().min(1, 'Choose a class') : z.string().optional(),
    title: z.string().trim().min(1, 'Enter a title').max(150, 'At most 150 characters'),
    instructions: z
      .string()
      .trim()
      .min(1, 'Enter the instructions')
      .max(5000, 'At most 5000 characters'),
    deadline: z
      .string()
      .min(1, 'Choose a deadline')
      .refine(
        (v) => new Date(istInputToIso(v)).getTime() >= Date.now() + 60_000,
        'The deadline must be at least 1 minute in the future',
      ),
    allowed_types: z.array(z.enum(ALLOWED_TYPES)).min(1, 'Choose at least one file type'),
    max_file_mb: z
      .number({ message: 'Enter a number' })
      .int('Whole megabytes only')
      .min(1, 'At least 1 MB')
      .max(10, 'At most 10 MB'),
  })
}
export type AssignmentFormValues = z.infer<ReturnType<typeof makeSchema>>

export interface AssignmentFormOutput {
  subject_id?: string
  section_id?: string
  title: string
  instructions: string
  deadline: string
  allowed_types: AllowedType[]
  max_file_mb: number
}

interface Props {
  mode: 'create' | 'edit'
  teaching?: Me['teaching']
  initial?: {
    title: string
    instructions: string
    deadline: string
    allowed_types: AllowedType[]
    max_file_mb: number
  }
  busy: boolean
  error: string | null
  onSubmit: (values: AssignmentFormOutput, publish: boolean, files: File[]) => void
}

export default function AssignmentForm({ mode, teaching, initial, busy, error, onSubmit }: Props) {
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<AssignmentFormValues>({
    resolver: zodResolver(makeSchema(mode)),
    defaultValues: {
      slot: '',
      title: initial?.title ?? '',
      instructions: initial?.instructions ?? '',
      deadline: initial ? isoToIstInput(initial.deadline) : '',
      allowed_types: initial?.allowed_types ?? ['pdf'],
      max_file_mb: initial?.max_file_mb ?? 10,
    },
  })

  const [files, setFiles] = useState<File[]>([])
  const [fileError, setFileError] = useState<string | null>(null)
  const picker = useRef<HTMLInputElement>(null)

  function addFiles(list: FileList | null) {
    setFileError(null)
    const picked = Array.from(list ?? [])
    if (picker.current) picker.current.value = ''
    if (files.length + picked.length > MAX_REFERENCE_FILES) {
      setFileError(`At most ${MAX_REFERENCE_FILES} reference documents are allowed.`)
      return
    }
    for (const f of picked) {
      const problem = checkReferenceFile(f)
      if (problem) return setFileError(problem)
    }
    setFiles((prev) => [...prev, ...picked])
  }

  function submit(publish: boolean) {
    return handleSubmit((v) => {
      const [subject_id, section_id] = (v.slot ?? '').split('|')
      onSubmit(
        {
          ...(mode === 'create' ? { subject_id, section_id } : {}),
          title: v.title,
          instructions: v.instructions,
          deadline: istInputToIso(v.deadline),
          allowed_types: v.allowed_types,
          max_file_mb: v.max_file_mb,
        },
        publish,
        mode === 'create' ? files : [],
      )
    })
  }

  return (
    <form onSubmit={submit(true)} noValidate>
      {mode === 'create' && (
        <label>
          Class (subject · section)
          <select aria-invalid={!!errors.slot} {...register('slot')}>
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
          {errors.slot && <span className="field-error">{errors.slot.message}</span>}
        </label>
      )}
      <label>
        Title
        <input type="text" maxLength={150} aria-invalid={!!errors.title} {...register('title')} />
        {errors.title && <span className="field-error">{errors.title.message}</span>}
      </label>
      <label>
        Instructions
        <textarea
          rows={6}
          maxLength={5000}
          aria-invalid={!!errors.instructions}
          {...register('instructions')}
        />
        {errors.instructions && <span className="field-error">{errors.instructions.message}</span>}
      </label>
      {mode === 'create' && (
        <fieldset>
          <legend>Reference documents (optional)</legend>
          <p className="muted small">
            Attach question papers, slides or notes for students. PDF, PPT or PPTX, up to{' '}
            {MAX_REFERENCE_FILES} files of {MAX_REFERENCE_MB} MB. They are locked once the
            assignment is published.
          </p>
          <input
            ref={picker}
            type="file"
            accept=".pdf,.ppt,.pptx"
            multiple
            aria-label="Reference documents"
            onChange={(e) => addFiles(e.target.files)}
          />
          {fileError && <span className="field-error">{fileError}</span>}
          {files.length > 0 && (
            <ul className="materials-list" aria-label="Selected reference documents">
              {files.map((f, i) => (
                <li key={`${f.name}-${i}`} className="material">
                  <span className="material-info">
                    <strong className="plain">{f.name}</strong>
                    <span className="muted small">{formatSize(f.size)}</span>
                  </span>
                  <button
                    type="button"
                    className="secondary compact danger"
                    onClick={() => setFiles((prev) => prev.filter((_, j) => j !== i))}
                    aria-label={`Remove ${f.name}`}
                  >
                    Remove
                  </button>
                </li>
              ))}
            </ul>
          )}
        </fieldset>
      )}
      <label>
        Deadline (IST)
        <input
          type="datetime-local"
          min={nowIstInput()}
          aria-invalid={!!errors.deadline}
          {...register('deadline')}
        />
        {errors.deadline && <span className="field-error">{errors.deadline.message}</span>}
      </label>
      <fieldset>
        <legend>Allowed file types</legend>
        <div className="checks">
          {ALLOWED_TYPES.map((t) => (
            <label key={t} className="check">
              <input type="checkbox" value={t} {...register('allowed_types')} />
              {t.toUpperCase()}
            </label>
          ))}
        </div>
        {errors.allowed_types && (
          <span className="field-error">{errors.allowed_types.message}</span>
        )}
      </fieldset>
      <label>
        Maximum file size (MB, 1–10)
        <input
          type="number"
          min={1}
          max={10}
          aria-invalid={!!errors.max_file_mb}
          {...register('max_file_mb', { valueAsNumber: true })}
        />
        {errors.max_file_mb && <span className="field-error">{errors.max_file_mb.message}</span>}
      </label>

      {error && <Notice kind="error">{error}</Notice>}

      <div className="actions">
        {mode === 'create' ? (
          <>
            <button type="submit" disabled={busy}>
              {busy ? 'Saving…' : 'Create and publish'}
            </button>
            <button type="button" className="secondary" disabled={busy} onClick={submit(false)}>
              Save as draft
            </button>
          </>
        ) : (
          <button type="submit" disabled={busy} onClick={submit(false)}>
            {busy ? 'Saving…' : 'Save changes'}
          </button>
        )}
      </div>
    </form>
  )
}
