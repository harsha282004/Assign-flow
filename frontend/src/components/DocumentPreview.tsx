import { Download, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { errorMessage, fetchPreview } from '../api/client'

const PDF = 'application/pdf'
const IMAGES = ['image/png', 'image/jpeg']

/** The only types the server will preview. Anything else is never "rendered": the user is told to download it. */
export function isPreviewable(mime: string): boolean {
  return mime === PDF || IMAGES.includes(mime)
}

interface Props {
  filename: string
  mime: string
  previewPath: string
  onDownload: () => void
  onClose: () => void
}

/**
 * In-app preview of a private document. The file is fetched with the session token and shown from a local blob
 * URL, so no storage URL ever reaches the page. PowerPoint and other types get an honest message, not a fake render.
 */
export default function DocumentPreview({
  filename,
  mime,
  previewPath,
  onDownload,
  onClose,
}: Props) {
  const canPreview = isPreviewable(mime)
  const [url, setUrl] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(canPreview)
  const closeRef = useRef<HTMLButtonElement>(null)
  const opener = useRef<Element | null>(document.activeElement)

  useEffect(() => {
    if (!canPreview) return
    let objectUrl: string | null = null
    let cancelled = false
    fetchPreview(previewPath)
      .then((blob) => {
        if (cancelled) return
        // Re-wrap with the type the server detected: the page never lets the browser guess a type.
        objectUrl = URL.createObjectURL(new Blob([blob], { type: mime }))
        setUrl(objectUrl)
      })
      .catch((e: unknown) => !cancelled && setError(errorMessage(e)))
      .finally(() => !cancelled && setLoading(false))
    return () => {
      cancelled = true
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [canPreview, mime, previewPath])

  useEffect(() => {
    closeRef.current?.focus()
    const previous = opener.current
    const overflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => {
      window.removeEventListener('keydown', onKey)
      document.body.style.overflow = overflow
      if (previous instanceof HTMLElement) previous.focus()
    }
  }, [onClose])

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-label={`Preview of ${filename}`}
        onClick={(e) => e.stopPropagation()}
      >
        <header className="modal-head">
          <strong className="modal-title" title={filename}>
            {filename}
          </strong>
          <span className="modal-actions">
            <button className="secondary compact" onClick={onDownload}>
              <Download size={16} aria-hidden="true" /> Download
            </button>
            <button ref={closeRef} className="secondary compact" onClick={onClose}>
              <X size={16} aria-hidden="true" /> Close
            </button>
          </span>
        </header>
        <div className="modal-body">
          {!canPreview && (
            <div className="empty-soft" role="status">
              <strong>This file type cannot be previewed in AssignFlow</strong>
              <p className="muted small">
                Only PDF, PNG and JPEG files can be shown here. Use Download to open the original
                file on your device.
              </p>
            </div>
          )}
          {canPreview && loading && (
            <p className="center muted" role="status">
              Loading preview…
            </p>
          )}
          {error && (
            <p role="alert" className="notice error">
              {error}
            </p>
          )}
          {url && mime === PDF && (
            <iframe className="preview-frame" src={url} title={`PDF preview: ${filename}`} />
          )}
          {url && IMAGES.includes(mime) && (
            <img className="preview-image" src={url} alt={`Preview of ${filename}`} />
          )}
        </div>
      </div>
    </div>
  )
}
