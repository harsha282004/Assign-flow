import { useAuth } from '../auth/useAuth'

/** Collapsible "who am I teaching / which subjects do I have" panel, straight from GET /auth/me. */
export default function AcademicSummary() {
  const { state } = useAuth()
  if (state.status !== 'authenticated') return null
  const { me } = state

  return (
    <details className="panel">
      <summary>
        {me.role === 'STUDENT'
          ? `My class${me.section ? `: ${me.section.label} (semester ${me.section.semester})` : ''}`
          : `My classes (${me.teaching?.length ?? 0})`}
      </summary>
      {me.subjects && (
        <ul className="list">
          {me.subjects.map((s) => (
            <li key={s.code}>
              <span>
                {s.code} · {s.name}
              </span>
              <span className="muted">{s.faculty_name ?? 'No faculty assigned'}</span>
            </li>
          ))}
        </ul>
      )}
      {me.teaching &&
        (me.teaching.length === 0 ? (
          <p className="muted">
            You have no teaching assignments, so you cannot create assignments.
          </p>
        ) : (
          <ul className="list">
            {me.teaching.map((t) => (
              <li key={`${t.subject.code}-${t.section.label}`}>
                <span>
                  {t.subject.code} · {t.subject.name}
                </span>
                <span className="muted">{t.section.label}</span>
              </li>
            ))}
          </ul>
        ))}
    </details>
  )
}
