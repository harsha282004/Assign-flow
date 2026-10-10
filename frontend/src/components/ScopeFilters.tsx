import { Filter, X } from 'lucide-react'
import { useMemo } from 'react'
import type { Me, ScopeFilter } from '../api/types'

type Teaching = NonNullable<Me['teaching']>

/**
 * Subject and Section filters built ONLY from the classes the signed-in faculty member teaches (GET /auth/me).
 * The options depend on each other: after picking a section only the subjects taught there are offered, and the
 * other way round, so an impossible combination cannot be chosen. The server validates every ID again.
 */
export function useScopeOptions(teaching: Teaching, filter: ScopeFilter) {
  return useMemo(() => {
    const subjects = new Map<string, Teaching[number]['subject']>()
    const sections = new Map<string, Teaching[number]['section']>()
    for (const t of teaching) {
      if (!filter.section_id || t.section.id === filter.section_id)
        subjects.set(t.subject.id, t.subject)
      if (!filter.subject_id || t.subject.id === filter.subject_id)
        sections.set(t.section.id, t.section)
    }
    return {
      subjects: [...subjects.values()].sort((a, b) => a.code.localeCompare(b.code)),
      sections: [...sections.values()].sort((a, b) => a.label.localeCompare(b.label)),
    }
  }, [teaching, filter.subject_id, filter.section_id])
}

export default function ScopeFilters({
  teaching,
  filter,
  onChange,
  children,
}: {
  teaching: Teaching
  filter: ScopeFilter
  onChange: (next: ScopeFilter) => void
  children?: React.ReactNode
}) {
  const { subjects, sections } = useScopeOptions(teaching, filter)
  const subject = subjects.find((s) => s.id === filter.subject_id)
  const section = sections.find((s) => s.id === filter.section_id)
  const active = !!(subject || section)

  function change(next: ScopeFilter) {
    // Keep only a combination that really exists among my teaching assignments.
    const valid = (f: ScopeFilter) =>
      teaching.some(
        (t) =>
          (!f.subject_id || t.subject.id === f.subject_id) &&
          (!f.section_id || t.section.id === f.section_id),
      )
    onChange(valid(next) ? next : { ...next, subject_id: undefined })
  }

  return (
    <div className="scope-filters">
      <div className="filters dash-filters">
        <label>
          Subject
          <select
            value={filter.subject_id ?? ''}
            onChange={(e) => change({ ...filter, subject_id: e.target.value || undefined })}
          >
            <option value="">All my subjects</option>
            {subjects.map((s) => (
              <option key={s.id} value={s.id}>
                {s.code} · {s.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Section
          <select
            value={filter.section_id ?? ''}
            onChange={(e) => change({ ...filter, section_id: e.target.value || undefined })}
          >
            <option value="">All my sections</option>
            {sections.map((s) => (
              <option key={s.id} value={s.id}>
                {s.label}
              </option>
            ))}
          </select>
        </label>
        {children}
      </div>
      <p className={`active-filter${active ? ' on' : ''}`} role="status" aria-live="polite">
        <Filter size={14} aria-hidden="true" />
        {active ? (
          <>
            Showing{' '}
            <strong>
              {section ? section.label : 'all my sections'}
              {' · '}
              {subject ? `${subject.code} ${subject.name}` : 'all my subjects'}
            </strong>
            <button
              type="button"
              className="secondary compact"
              onClick={() => onChange({})}
              aria-label="Clear the subject and section filters"
            >
              <X size={14} aria-hidden="true" /> Clear
            </button>
          </>
        ) : (
          <>Showing the combined totals of all my sections and subjects</>
        )}
      </p>
    </div>
  )
}
