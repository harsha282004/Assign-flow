import type { LucideIcon } from 'lucide-react'

export type Tone = 'blue' | 'green' | 'yellow' | 'red' | 'lavender'

interface Props {
  label: string
  caption: string
  value: number | undefined
  icon: LucideIcon
  tone: Tone
  loading?: boolean
  failed?: boolean
}

/** One summary metric. The value is always a real API number; while loading or on error no number is shown. */
export default function StatCard({
  label,
  caption,
  value,
  icon: Icon,
  tone,
  loading,
  failed,
}: Props) {
  return (
    <div className={`stat-card tone-${tone}`}>
      <span className="stat-icon" aria-hidden="true">
        <Icon size={24} />
      </span>
      <div>
        <p className="stat-label">{label}</p>
        {loading ? (
          <span className="skeleton skeleton-value" role="status" aria-label={`Loading ${label}`} />
        ) : failed || value === undefined ? (
          <p className="stat-value" aria-label={`${label} unavailable`}>
            –
          </p>
        ) : (
          <p className="stat-value">{String(value).padStart(2, '0')}</p>
        )}
        <p className="stat-caption">{caption}</p>
      </div>
      <Icon className="stat-watermark" size={56} aria-hidden="true" />
    </div>
  )
}
