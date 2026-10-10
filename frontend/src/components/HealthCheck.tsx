import { useState } from 'react'
import { API_BASE_URL } from '../api/client'

type Dep = 'ok' | 'down'
interface HealthResponse {
  status: string
  db: Dep
  redis: Dep
  storage: Dep
}

type State =
  | { kind: 'idle' }
  | { kind: 'loading' }
  | { kind: 'result'; httpStatus: number; data: HealthResponse }
  | { kind: 'error'; message: string }

const DEPS: { key: 'db' | 'redis' | 'storage'; label: string }[] = [
  { key: 'db', label: 'PostgreSQL' },
  { key: 'redis', label: 'Redis' },
  { key: 'storage', label: 'MinIO storage' },
]

function isHealth(v: unknown): v is HealthResponse {
  if (typeof v !== 'object' || v === null) return false
  const o = v as Record<string, unknown>
  return ['status', 'db', 'redis', 'storage'].every((k) => typeof o[k] === 'string')
}

/** Phase 1 system-status control: shows the real /health response, never a hard-coded status. */
export default function HealthCheck() {
  const [state, setState] = useState<State>({ kind: 'idle' })

  async function checkHealth() {
    setState({ kind: 'loading' })
    try {
      const res = await fetch(`${API_BASE_URL}/health`, { headers: { Accept: 'application/json' } })
      const data: unknown = await res.json()
      if (!isHealth(data)) throw new Error('Unexpected response from the API')
      setState({ kind: 'result', httpStatus: res.status, data })
    } catch (err) {
      const detail = err instanceof Error ? err.message : 'Unknown error'
      setState({ kind: 'error', message: `Could not reach the backend (${detail}).` })
    }
  }

  const healthy = state.kind === 'result' && state.httpStatus === 200 && state.data.status === 'ok'

  return (
    <section className="health">
      <p className="api">
        API base URL: <code>{API_BASE_URL || '(not configured)'}</code>
      </p>
      <button className="secondary" onClick={checkHealth} disabled={state.kind === 'loading'}>
        {state.kind === 'loading' ? 'Checking…' : 'Check backend health'}
      </button>
      <div role="status" aria-live="polite" className="result">
        {state.kind === 'error' && <p className="bad">{state.message}</p>}
        {state.kind === 'result' && (
          <>
            <p className={healthy ? 'good' : 'bad'}>
              {healthy ? 'All services healthy' : 'Degraded: a dependency is down'} (HTTP{' '}
              {state.httpStatus})
            </p>
            <ul>
              {DEPS.map((d) => (
                <li key={d.key}>
                  <span>{d.label}</span>
                  <strong className={state.data[d.key] === 'ok' ? 'good' : 'bad'}>
                    {state.data[d.key]}
                  </strong>
                </li>
              ))}
            </ul>
          </>
        )}
      </div>
    </section>
  )
}
