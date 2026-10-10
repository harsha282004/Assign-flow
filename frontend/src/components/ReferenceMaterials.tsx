import { FileText, Presentation, Trash2, Upload } from 'lucide-react'
import { useRef, useState } from 'react'
import { errorMessage } from '../api/client'
import { useDeleteAttachment, useUploadAttachment } from '../api/queries'
import type { Attachment } from '../api/types'
import FileActions from './FileActions'
import { Notice } from './ui'

export const MAX_REFERENCE_FILES = 5
export const MAX_REFERENCE_MB = 10
export const REFERENCE_EXTENSIONS = ['pdf', 'ppt', 'pptx']

/** Client-side convenience check; the server validates the real content again. Returns an error or null. */
export function checkReferenceFile(file: File): string | null {
  const ext = file.name.split('.').pop()?.toLowerCase() ?? ''
  if (!REFERENCE_EXTENSIONS.includes(ext))
    return `${file.name}: only PDF, PPT and PPTX files are allowed.`
  if (file.size === 0) return `${file.name}: the file is empty.`
  if (file.size > MAX_REFERENCE_MB * 1024 * 1024)
    return `${file.name}: larger than ${MAX_REFERENCE_MB} MB.`
  return null
}

export function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`
}

function Row({
  a,
  onError,
  actions,
}: {
  a: Attachment
  onError: (m: string | null) => void
  actions?: React.ReactNode
}) {
  const Icon = a.file_type === 'PDF' ? FileText : Presentation
  return (
    <li className="material">
      <span className="material-icon" aria-hidden="true">
        <Icon size={22} />
      </span>
      <span className="material-info">
        <strong className="plain">{a.original_filename}</strong>
        <span className="muted small">
          {a.file_type} · {formatSize(a.size_bytes)}
          {!a.previewable && ' · download to view'}
        </span>
      </span>
      <FileActions
        filename={a.original_filename}
        mime={a.mime_type}
        previewPath={`/files/materials/${a.id}/preview`}
        downloadPath={`/files/materials/${a.id}`}
        onError={onError}
      />
      {actions}
    </li>
  )
}

/**
 * Reference documents of an assignment. Students and faculty of a published assignment get View + Download.
 * `editable` (faculty, DRAFT only) adds upload and remove; after publication the list is locked by the server.
 */
export default function ReferenceMaterials({
  assignmentId,
  attachments,
  editable = false,
}: {
  assignmentId: string
  attachments: Attachment[]
  editable?: boolean
}) {
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState<string | null>(null)
  const input = useRef<HTMLInputElement>(null)
  const upload = useUploadAttachment(assignmentId)
  const remove = useDeleteAttachment(assignmentId)
  const busy = upload.isPending || remove.isPending

  async function onFiles(files: FileList | null) {
    setError(null)
    setDone(null)
    const picked = Array.from(files ?? [])
    if (input.current) input.current.value = ''
    if (picked.length === 0) return
    if (attachments.length + picked.length > MAX_REFERENCE_FILES) {
      setError(`An assignment can have at most ${MAX_REFERENCE_FILES} reference documents.`)
      return
    }
    for (const file of picked) {
      const problem = checkReferenceFile(file)
      if (problem) return setError(problem)
    }
    let added = 0
    for (const file of picked) {
      try {
        await upload.mutateAsync(file)
        added += 1
      } catch (e) {
        setError(`${file.name}: ${errorMessage(e)}`)
        break
      }
    }
    if (added > 0) setDone(`${added} document${added === 1 ? '' : 's'} added.`)
  }

  return (
    <div className="materials">
      {error && <Notice kind="error">{error}</Notice>}
      {done && <Notice kind="success">{done}</Notice>}
      {attachments.length === 0 ? (
        <p className="muted">No reference documents were attached.</p>
      ) : (
        <ul className="materials-list" aria-label="Reference documents">
          {attachments.map((a) => (
            <Row
              key={a.id}
              a={a}
              onError={setError}
              actions={
                editable && (
                  <button
                    type="button"
                    className="secondary compact danger"
                    disabled={busy}
                    onClick={() => {
                      setError(null)
                      setDone(null)
                      remove.mutate(a.id, { onError: (e) => setError(errorMessage(e)) })
                    }}
                    aria-label={`Remove ${a.original_filename}`}
                  >
                    <Trash2 size={16} aria-hidden="true" /> Remove
                  </button>
                )
              }
            />
          ))}
        </ul>
      )}
      {editable && (
        <div className="material-add">
          <input
            ref={input}
            type="file"
            id={`ref-${assignmentId}`}
            className="sr-only"
            accept=".pdf,.ppt,.pptx"
            multiple
            disabled={busy || attachments.length >= MAX_REFERENCE_FILES}
            onChange={(e) => void onFiles(e.target.files)}
          />
          <label
            htmlFor={`ref-${assignmentId}`}
            className={`button secondary-link compact${busy || attachments.length >= MAX_REFERENCE_FILES ? ' disabled' : ''}`}
          >
            <Upload size={16} aria-hidden="true" /> {busy ? 'Working…' : 'Add reference documents'}
          </label>
          <span className="muted small">
            PDF, PPT or PPTX · up to {MAX_REFERENCE_FILES} files of {MAX_REFERENCE_MB} MB. They are
            locked once you publish.
          </span>
        </div>
      )}
    </div>
  )
}
