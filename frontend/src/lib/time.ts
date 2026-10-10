// The server stores UTC and sends ISO-8601; the UI shows and accepts IST (Asia/Kolkata, UTC+05:30, no DST).
const IST = 'Asia/Kolkata'
const IST_OFFSET_MS = 5.5 * 60 * 60 * 1000

const formatter = new Intl.DateTimeFormat('en-IN', {
  timeZone: IST,
  day: '2-digit',
  month: 'short',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
  hour12: true,
})

export function formatIst(iso: string): string {
  return `${formatter.format(new Date(iso))} IST`
}

/** "YYYY-MM-DDTHH:mm" typed into a datetime-local input is interpreted as IST and sent with an offset. */
export function istInputToIso(local: string): string {
  return `${local}:00+05:30`
}

/** ISO instant -> "YYYY-MM-DDTHH:mm" in IST, for datetime-local inputs. */
export function isoToIstInput(iso: string): string {
  return new Date(new Date(iso).getTime() + IST_OFFSET_MS).toISOString().slice(0, 16)
}

/** Current time as an IST datetime-local string (used as the `min` hint of the inputs). */
export function nowIstInput(): string {
  return isoToIstInput(new Date().toISOString())
}

/** Human countdown. Display only: the server decides every status. */
export function remainingText(iso: string, nowMs: number): string {
  const diff = new Date(iso).getTime() - nowMs
  const abs = Math.abs(diff)
  const minutes = Math.floor(abs / 60000)
  const days = Math.floor(minutes / 1440)
  const hours = Math.floor((minutes % 1440) / 60)
  const mins = minutes % 60
  const parts =
    days > 0 ? `${days} d ${hours} h` : hours > 0 ? `${hours} h ${mins} min` : `${mins} min`
  return diff >= 0 ? `${parts} left` : `${parts} overdue`
}

/** "YYYY-MM-DD" of an instant in IST (calendar days are IST days, never the browser's zone). */
export function istDay(iso: string | number): string {
  return new Date(new Date(iso).getTime() + IST_OFFSET_MS).toISOString().slice(0, 10)
}

const dayFormatter = new Intl.DateTimeFormat('en-IN', {
  timeZone: IST,
  weekday: 'long',
  day: 'numeric',
  month: 'long',
  year: 'numeric',
})

export function formatIstDay(iso: string | number): string {
  return dayFormatter.format(new Date(iso))
}

const timeFormatter = new Intl.DateTimeFormat('en-IN', {
  timeZone: IST,
  hour: 'numeric',
  minute: '2-digit',
  hour12: true,
})

export function formatIstTime(iso: string): string {
  return timeFormatter.format(new Date(iso))
}

/** "Today, 5:12 PM" / "Yesterday, 2:30 PM" / "08 Oct 2026, 4:15 PM" (all IST). */
export function relativeIst(iso: string, nowMs: number = Date.now()): string {
  const day = istDay(iso)
  if (day === istDay(nowMs)) return `Today, ${formatIstTime(iso)}`
  if (day === istDay(nowMs - 86_400_000)) return `Yesterday, ${formatIstTime(iso)}`
  const d = new Intl.DateTimeFormat('en-IN', {
    timeZone: IST,
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  }).format(new Date(iso))
  return `${d}, ${formatIstTime(iso)}`
}

export function initials(name: string): string {
  const parts = name
    .replace(/\b(Prof|Dr|Mr|Ms|Mrs)\.?\s+/gi, '')
    .split(/\s+/)
    .filter(Boolean)
  return (
    (parts[0]?.[0] ?? '?') + (parts.length > 1 ? (parts[parts.length - 1][0] ?? '') : '')
  ).toUpperCase()
}
