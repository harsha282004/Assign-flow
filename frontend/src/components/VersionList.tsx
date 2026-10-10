import { useState } from 'react'
import type { UploadContext, VersionOut } from '../api/types'
import { formatIst } from '../lib/time'
import FileActions from './FileActions'
import { Notice } from './ui'

const CONTEXT_LABELS: Record<UploadContext, string> = {
  REGULAR: 'Regular',
  LATE_APPROVED: 'Late (approved)',
  REVISION: 'Revision',
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`
}

/** Immutable version history. Each version has View (in-app preview) and Download (original file). */
export default function VersionList({ versions }: { versions: VersionOut[] }) {
  const [error, setError] = useState<string | null>(null)

  if (versions.length === 0) return <p className="muted">No files have been submitted yet.</p>
  return (
    <>
      {error && <Notice kind="error">{error}</Notice>}
      <ol className="versions" aria-label="Submission versions">
        {[...versions].reverse().map((v, i) => (
          <li key={v.id}>
            <div className="row">
              <strong>
                Version {v.version_no}
                {i === 0 && <span className="muted"> (latest)</span>}
              </strong>
              <FileActions
                filename={v.original_filename}
                mime={v.mime_type}
                previewPath={`/files/versions/${v.id}/preview`}
                downloadPath={`/files/versions/${v.id}`}
                onError={setError}
              />
            </div>
            <span className="plain">{v.original_filename}</span>
            <span className="muted">
              {formatSize(v.size_bytes)} · received {formatIst(v.uploaded_at)} ·{' '}
              {CONTEXT_LABELS[v.upload_context]}
            </span>
            <span className="muted">
              Deadline at upload: {formatIst(v.deadline_at_upload)} ·{' '}
              <span className={v.timing_at_upload === 'LATE' ? 'bad' : 'good'}>
                {v.timing_at_upload === 'LATE' ? 'Late' : 'On time'} when received
              </span>
              {v.timing_now !== v.timing_at_upload && (
                <> · {v.timing_now === 'LATE' ? 'late' : 'on time'} against the current deadline</>
              )}
            </span>
          </li>
        ))}
      </ol>
    </>
  )
}
