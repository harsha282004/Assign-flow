import { Download, Eye } from 'lucide-react'
import { useState } from 'react'
import { downloadFile, errorMessage } from '../api/client'
import DocumentPreview from './DocumentPreview'

interface Props {
  filename: string
  mime: string
  /** API path of the inline preview endpoint and of the original-file download endpoint. */
  previewPath: string
  downloadPath: string
  onError?: (message: string | null) => void
}

/** [ View ] [ Download ] side by side. View opens the in-app preview; Download always saves the original file. */
export default function FileActions({ filename, mime, previewPath, downloadPath, onError }: Props) {
  const [viewing, setViewing] = useState(false)
  const [downloading, setDownloading] = useState(false)

  async function download() {
    onError?.(null)
    setDownloading(true)
    try {
      await downloadFile(downloadPath, filename)
    } catch (e) {
      onError?.(errorMessage(e))
    } finally {
      setDownloading(false)
    }
  }

  return (
    <>
      <span className="file-actions">
        <button
          type="button"
          className="secondary compact"
          onClick={() => setViewing(true)}
          aria-label={`View ${filename}`}
        >
          <Eye size={16} aria-hidden="true" /> View
        </button>
        <button
          type="button"
          className="secondary compact"
          disabled={downloading}
          onClick={() => void download()}
          aria-label={`Download ${filename}`}
        >
          <Download size={16} aria-hidden="true" /> {downloading ? 'Downloading…' : 'Download'}
        </button>
      </span>
      {viewing && (
        <DocumentPreview
          filename={filename}
          mime={mime}
          previewPath={previewPath}
          onDownload={() => void download()}
          onClose={() => setViewing(false)}
        />
      )}
    </>
  )
}
