import { CalendarDays, ChevronLeft, ChevronRight } from 'lucide-react'
import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { formatIstDay, formatIstTime, istDay } from '../../lib/time'

export type MarkerKind = 'due' | 'late' | 'done' | 'missed' | 'other'

export interface CalendarEvent {
  id: string
  at: string // ISO instant of the deadline
  kind: MarkerKind
  title: string
  detail: string
  to: string
}

export const LEGEND: Record<MarkerKind, string> = {
  due: 'Submission due',
  late: 'Late request open',
  done: 'Completed',
  missed: 'Missed',
  other: 'Deadline',
}

const MONTHS = [
  'January',
  'February',
  'March',
  'April',
  'May',
  'June',
  'July',
  'August',
  'September',
  'October',
  'November',
  'December',
]
const WEEKDAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
// Highest-priority marker wins when several deadlines share a day.
const PRIORITY: MarkerKind[] = ['due', 'late', 'missed', 'other', 'done']

const pad = (n: number) => String(n).padStart(2, '0')

/** Monthly calendar of real deadlines (IST days). Selecting a day lists that day's deadlines. */
export default function DeadlineCalendar({
  events,
  kinds,
}: {
  events: CalendarEvent[]
  kinds: MarkerKind[]
}) {
  const today = istDay(Date.now())
  const [view, setView] = useState(() => ({
    y: Number(today.slice(0, 4)),
    m: Number(today.slice(5, 7)) - 1,
  }))
  const [selected, setSelected] = useState<string | null>(null)

  const byDay = useMemo(() => {
    const map = new Map<string, CalendarEvent[]>()
    for (const e of events) {
      const d = istDay(e.at)
      map.set(d, [...(map.get(d) ?? []), e])
    }
    return map
  }, [events])

  const first = new Date(Date.UTC(view.y, view.m, 1)).getUTCDay()
  const days = new Date(Date.UTC(view.y, view.m + 1, 0)).getUTCDate()
  const cells: (number | null)[] = [
    ...Array.from({ length: first }, () => null),
    ...Array.from({ length: days }, (_, i) => i + 1),
  ]
  const weeks = Math.ceil(cells.length / 7)

  function move(delta: number) {
    setSelected(null)
    setView(({ y, m }) => {
      const n = m + delta
      return { y: y + Math.floor(n / 12), m: ((n % 12) + 12) % 12 }
    })
  }

  const picked = selected ? (byDay.get(selected) ?? []) : []

  return (
    <section className="dash-card" aria-labelledby="cal-h">
      <div className="dash-card-head">
        <h2 id="cal-h">
          <CalendarDays size={20} aria-hidden="true" /> Deadline calendar
        </h2>
        <div className="cal-nav">
          <button className="icon-btn" aria-label="Previous month" onClick={() => move(-1)}>
            <ChevronLeft size={18} />
          </button>
          <strong aria-live="polite">
            {MONTHS[view.m]} {view.y}
          </strong>
          <button className="icon-btn" aria-label="Next month" onClick={() => move(1)}>
            <ChevronRight size={18} />
          </button>
        </div>
      </div>

      <div className="cal" role="grid" aria-label={`${MONTHS[view.m]} ${view.y}`}>
        <div className="cal-row" role="row">
          {WEEKDAYS.map((w) => (
            <span key={w} className="cal-wd" role="columnheader">
              {w}
            </span>
          ))}
        </div>
        {Array.from({ length: weeks }, (_, r) => (
          <div className="cal-row" role="row" key={r}>
            {Array.from({ length: 7 }, (_, c) => {
              const day = cells[r * 7 + c]
              if (!day) return <span key={c} role="gridcell" />
              const key = `${view.y}-${pad(view.m + 1)}-${pad(day)}`
              const list = byDay.get(key) ?? []
              const kind = PRIORITY.find((k) => list.some((e) => e.kind === k))
              const label =
                `${day} ${MONTHS[view.m]}` +
                (kind
                  ? `, ${list.length} deadline${list.length > 1 ? 's' : ''}: ${LEGEND[kind]}`
                  : '')
              return (
                <span key={c} role="gridcell">
                  <button
                    className={[
                      'cal-day',
                      kind ? `mk-${kind}` : '',
                      key === today ? 'today' : '',
                      key === selected ? 'selected' : '',
                    ].join(' ')}
                    aria-label={label}
                    aria-pressed={key === selected}
                    aria-current={key === today ? 'date' : undefined}
                    onClick={() => setSelected(key === selected ? null : key)}
                  >
                    {day}
                  </button>
                </span>
              )
            })}
          </div>
        ))}
      </div>

      <ul className="legend" aria-label="Legend">
        {kinds.map((k) => (
          <li key={k}>
            <span className={`dot mk-${k}`} aria-hidden="true" /> {LEGEND[k]}
          </li>
        ))}
        <li>
          <span className="dot today-dot" aria-hidden="true" /> Today
        </li>
      </ul>

      {selected && (
        <div className="cal-picked" aria-live="polite">
          <p className="small muted">{formatIstDay(`${selected}T12:00:00+05:30`)}</p>
          {picked.length === 0 ? (
            <p className="small">No deadlines on this day.</p>
          ) : (
            <ul className="list">
              {picked.map((e) => (
                <li key={e.id}>
                  <span>
                    <Link to={e.to}>{e.title}</Link>
                    <br />
                    <span className="muted small">{e.detail}</span>
                  </span>
                  <span className="muted small">
                    {formatIstTime(e.at)} · {LEGEND[e.kind]}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  )
}
