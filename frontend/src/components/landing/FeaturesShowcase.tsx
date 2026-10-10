import {
  motion,
  useMotionValueEvent,
  useReducedMotion,
  useScroll,
  useTransform,
  type MotionValue,
} from 'framer-motion'
import { ArrowRight, ChevronLeft, ChevronRight } from 'lucide-react'
import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'

interface Feature {
  title: string
  text: string
  tone: 'blue' | 'lavender' | 'violet' | 'mint' | 'sky'
  art: ReactNode
}

const stroke = {
  fill: 'none',
  strokeWidth: 3,
  strokeLinecap: 'round',
  strokeLinejoin: 'round',
} as const

// One consistent illustration style: rounded shapes, a pastel fill and a navy / blue outline.
const FEATURES: Feature[] = [
  {
    title: 'Track Deadlines',
    text: 'Keep track of assignment deadlines, with a live countdown on every assignment.',
    tone: 'blue',
    art: (
      <svg viewBox="0 0 140 100" role="img" aria-label="Calendar with a countdown clock">
        <rect
          {...stroke}
          x="18"
          y="16"
          width="78"
          height="70"
          rx="12"
          fill="#fff"
          stroke="#101d42"
        />
        <path d="M18 38h78" stroke="#101d42" {...stroke} />
        <rect x="18" y="16" width="78" height="22" rx="12" fill="#2874ff" />
        <path d="M38 10v14M76 10v14" stroke="#101d42" {...stroke} />
        {[0, 1, 2].map((r) =>
          [0, 1, 2, 3].map((c) => (
            <rect
              key={`${r}${c}`}
              x={28 + c * 17}
              y={46 + r * 12}
              width="9"
              height="7"
              rx="2"
              fill={r === 1 && c === 2 ? '#2874ff' : '#cfe0fb'}
            />
          )),
        )}
        <circle {...stroke} cx="106" cy="68" r="22" fill="#fff" stroke="#2874ff" />
        <path d="M106 56v13l9 5" stroke="#101d42" {...stroke} />
      </svg>
    ),
  },
  {
    title: 'Submit with Ease',
    text: 'Upload your work and view your complete submission history.',
    tone: 'lavender',
    art: (
      <svg viewBox="0 0 140 100" role="img" aria-label="Document with an upload arrow">
        <rect
          {...stroke}
          x="34"
          y="8"
          width="64"
          height="80"
          rx="10"
          fill="#fff"
          stroke="#101d42"
        />
        <path d="M80 8v18h18" stroke="#101d42" {...stroke} />
        <path d="M66 70V44M54 55l12-12 12 12" stroke="#7c4dff" {...stroke} />
        <rect x="46" y="76" width="40" height="6" rx="3" fill="#e4dcff" />
        <rect x="46" y="76" width="26" height="6" rx="3" fill="#7c4dff" />
        <circle {...stroke} cx="108" cy="30" r="14" fill="#e8f1ff" stroke="#2874ff" />
        <path d="M101 30l5 5 9-10" stroke="#2874ff" {...stroke} />
      </svg>
    ),
  },
  {
    title: 'Request Late Work',
    text: 'Missed a deadline? Request an extension with a clear explanation.',
    tone: 'violet',
    art: (
      <svg viewBox="0 0 140 100" role="img" aria-label="Clock with an approval check">
        <circle {...stroke} cx="62" cy="52" r="36" fill="#fff" stroke="#101d42" />
        <path d="M62 30v24l16 10" stroke="#2874ff" {...stroke} />
        <rect
          {...stroke}
          x="88"
          y="10"
          width="40"
          height="34"
          rx="8"
          fill="#f0e9ff"
          stroke="#7c4dff"
        />
        <path d="M88 22h40" stroke="#7c4dff" {...stroke} />
        <circle cx="112" cy="76" r="15" fill="#0f8a5f" />
        <path d="M105 76l5 5 9-10" stroke="#fff" {...stroke} />
      </svg>
    ),
  },
  {
    title: 'Stay Organized',
    text: 'Keep every assignment and its status organized in one place.',
    tone: 'mint',
    art: (
      <svg viewBox="0 0 140 100" role="img" aria-label="Folder with a checklist">
        <path
          {...stroke}
          d="M14 30a8 8 0 0 1 8-8h26l10 10h46a8 8 0 0 1 8 8v42a8 8 0 0 1-8 8H22a8 8 0 0 1-8-8z"
          fill="#d9f5e8"
          stroke="#101d42"
        />
        <rect
          {...stroke}
          x="36"
          y="44"
          width="70"
          height="40"
          rx="8"
          fill="#fff"
          stroke="#0f8a5f"
        />
        {[0, 1, 2].map((i) => (
          <g key={i}>
            <path d={`M46 ${55 + i * 11}l4 4 6-7`} stroke="#0f8a5f" {...stroke} strokeWidth={2.5} />
            <rect x="62" y={53 + i * 11} width="34" height="5" rx="2.5" fill="#cfe9dc" />
          </g>
        ))}
      </svg>
    ),
  },
  {
    title: 'Track Progress',
    text: 'See your academic progress and stay motivated throughout the semester.',
    tone: 'sky',
    art: (
      <svg viewBox="0 0 140 100" role="img" aria-label="Rising progress chart">
        <rect
          {...stroke}
          x="14"
          y="62"
          width="20"
          height="26"
          rx="5"
          fill="#cfe0fb"
          stroke="#101d42"
        />
        <rect
          {...stroke}
          x="42"
          y="46"
          width="20"
          height="42"
          rx="5"
          fill="#a9c8ff"
          stroke="#101d42"
        />
        <rect
          {...stroke}
          x="70"
          y="30"
          width="20"
          height="58"
          rx="5"
          fill="#6fa3ff"
          stroke="#101d42"
        />
        <rect
          {...stroke}
          x="98"
          y="14"
          width="20"
          height="74"
          rx="5"
          fill="#2874ff"
          stroke="#101d42"
        />
        <path d="M18 50l30-14 28-10 34-14" stroke="#7c4dff" {...stroke} strokeDasharray="2 7" />
        <circle {...stroke} cx="124" cy="14" r="11" fill="#fff" stroke="#0f8a5f" />
        <path d="M118 14l4 4 7-8" stroke="#0f8a5f" {...stroke} strokeWidth={2.5} />
      </svg>
    ),
  },
]

const LAST = FEATURES.length - 1
const STAGE_QUERY = '(min-width: 820px)'

function useMatch(query: string) {
  const [match, setMatch] = useState(() => window.matchMedia(query).matches)
  useEffect(() => {
    const mq = window.matchMedia(query)
    const on = () => setMatch(mq.matches)
    mq.addEventListener('change', on)
    return () => mq.removeEventListener('change', on)
  }, [query])
  return match
}

function Card({
  feature,
  active,
  onPick,
}: {
  feature: Feature
  active: boolean
  onPick: () => void
}) {
  return (
    <article className={`lp-fx-card tone-${feature.tone}${active ? ' active' : ''}`}>
      <div className="lp-fx-art">{feature.art}</div>
      <h3>{feature.title}</h3>
      <p>{feature.text}</p>
      <button
        type="button"
        className="lp-fx-go"
        aria-label={active ? `${feature.title} (current feature)` : `Show ${feature.title}`}
        onClick={onPick}
      >
        <ArrowRight size={18} aria-hidden="true" />
      </button>
    </article>
  )
}

/** One card of the scroll-driven row. Everything is derived from the single motion value `pos` (0..4). */
function StageCard({
  index,
  pos,
  feature,
  active,
  onPick,
}: {
  index: number
  pos: MotionValue<number>
  feature: Feature
  active: boolean
  onPick: () => void
}) {
  const d = useTransform(pos, (v) => index - v) // distance from the centre, in cards
  const x = useTransform(d, (v) => `${v * 84}%`)
  const scale = useTransform(d, (v) => Math.max(0.88, 1.05 - 0.085 * Math.abs(v)))
  const rotate = useTransform(d, (v) => Math.max(-3, Math.min(3, v * 2.2)))
  const y = useTransform(d, (v) => Math.min(Math.abs(v), 2) * 16)
  const opacity = useTransform(d, (v) => Math.max(0.72, 1 - 0.14 * Math.abs(v)))
  const z = useTransform(d, (v) => 10 - Math.round(Math.abs(v) * 2))
  return (
    <motion.div className="lp-fx-slot" style={{ x, scale, rotate, y, opacity, zIndex: z }}>
      <Card feature={feature} active={active} onPick={onPick} />
    </motion.div>
  )
}

function Dots({ active, onPick }: { active: number; onPick: (i: number) => void }) {
  return (
    <div className="lp-fx-dots" role="group" aria-label="Choose a feature">
      {FEATURES.map((f, i) => (
        <button
          key={f.title}
          type="button"
          className={i === active ? 'on' : ''}
          aria-label={`${f.title} (${i + 1} of ${FEATURES.length})`}
          aria-current={i === active}
          onClick={() => onPick(i)}
        />
      ))}
    </div>
  )
}

function Arrows({ active, onPick }: { active: number; onPick: (i: number) => void }) {
  return (
    <>
      <button
        type="button"
        className="lp-fx-arrow prev"
        aria-label="Previous feature"
        disabled={active === 0}
        onClick={() => onPick(active - 1)}
      >
        <ChevronLeft size={22} aria-hidden="true" />
      </button>
      <button
        type="button"
        className="lp-fx-arrow next"
        aria-label="Next feature"
        disabled={active === LAST}
        onClick={() => onPick(active + 1)}
      >
        <ChevronRight size={22} aria-hidden="true" />
      </button>
    </>
  )
}

function Heading() {
  return (
    <motion.div
      className="lp-fx-head"
      initial={{ opacity: 0, y: 22 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, amount: 0.4 }}
      transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
    >
      <span className="lp-fx-pill">Why choose AssignFlow</span>
      <h2 id="lp-features-h">
        Everything you need to <em>stay on top</em> of your work
      </h2>
      <p>
        Powerful tools for a smoother academic journey. Explore the key features that make
        AssignFlow simple, efficient and student-friendly.
      </p>
    </motion.div>
  )
}

/**
 * Features. Desktop: the page scroll drives a sticky card row (scroll position -> `pos`, a MotionValue, so no React
 * re-render per scroll event; React state only changes when the rounded card index changes). The arrows and dots do
 * not keep a second state: they scroll the page to the matching position, so scroll is the single source of truth.
 * Narrow screens and reduced motion: a plain swipeable carousel (CSS scroll-snap) with the same arrows and dots.
 */
export default function FeaturesShowcase() {
  const reduce = useReducedMotion()
  const wide = useMatch(STAGE_QUERY)
  return (
    <section id="features" className="lp-fx" aria-labelledby="lp-features-h">
      {wide && !reduce ? <Stage /> : <Carousel />}
    </section>
  )
}

function Stage() {
  const wrap = useRef<HTMLDivElement>(null)
  const { scrollYProgress } = useScroll({ target: wrap, offset: ['start start', 'end end'] })
  const pos = useTransform(scrollYProgress, [0, 1], [0, LAST], { clamp: true })
  const [active, setActive] = useState(0)
  useMotionValueEvent(pos, 'change', (v) => {
    const i = Math.round(v)
    setActive((prev) => (prev === i ? prev : i))
  })

  const goTo = useCallback((i: number) => {
    const el = wrap.current
    if (!el) return
    const top = el.getBoundingClientRect().top + window.scrollY
    const range = el.offsetHeight - window.innerHeight
    window.scrollTo({
      top: top + (Math.max(0, Math.min(LAST, i)) / LAST) * range,
      behavior: 'smooth',
    })
  }, [])

  return (
    <div ref={wrap} className="lp-fx-wrap">
      <div className="lp-fx-sticky">
        <Heading />
        <div className="lp-fx-stage">
          <Arrows active={active} onPick={goTo} />
          <div className="lp-fx-row" aria-live="off">
            {FEATURES.map((f, i) => (
              <StageCard
                key={f.title}
                index={i}
                pos={pos}
                feature={f}
                active={i === active}
                onPick={() => goTo(i)}
              />
            ))}
          </div>
        </div>
        <Dots active={active} onPick={goTo} />
      </div>
    </div>
  )
}

function Carousel() {
  const track = useRef<HTMLUListElement>(null)
  const [active, setActive] = useState(0)

  const step = () => {
    const t = track.current
    const first = t?.children[0] as HTMLElement | undefined
    const second = t?.children[1] as HTMLElement | undefined
    return first && second ? second.offsetLeft - first.offsetLeft : (first?.offsetWidth ?? 1)
  }
  const goTo = (i: number) => {
    const t = track.current
    if (!t) return
    const clamped = Math.max(0, Math.min(LAST, i))
    t.scrollTo({ left: clamped * step(), behavior: 'smooth' })
  }
  const onScroll = () => {
    const t = track.current
    if (!t) return
    const i = Math.round(t.scrollLeft / step())
    setActive((prev) => (prev === i ? prev : Math.max(0, Math.min(LAST, i))))
  }

  return (
    <div className="lp-fx-flat">
      <Heading />
      <div className="lp-fx-stage">
        <ul ref={track} className="lp-fx-track" onScroll={onScroll} aria-label="Features">
          {FEATURES.map((f, i) => (
            <li key={f.title}>
              <Card feature={f} active={i === active} onPick={() => goTo(i)} />
            </li>
          ))}
        </ul>
        <Arrows active={active} onPick={goTo} />
      </div>
      <Dots active={active} onPick={goTo} />
    </div>
  )
}
