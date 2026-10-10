import { Navigate, Outlet } from 'react-router-dom'
import type { Role } from '../api/types'
import { homePath, useAuth } from '../auth/useAuth'

/**
 * Route guard (usability only; the backend is the security boundary).
 * Anonymous -> that role's login page. Signed in with the other role -> their own home.
 */
export default function RequireRole({ role }: { role: Role }) {
  const { state, retrySession } = useAuth()
  if (state.status === 'loading') return <p className="center muted">Loading…</p>
  if (state.status === 'unavailable') {
    return (
      <main className="page">
        <div className="empty" role="alert">
          <strong className="bad">The server cannot be reached</strong>
          <p className="muted">
            You are still signed in. Check that the service is running, then try again.
          </p>
          <button className="secondary" onClick={retrySession}>
            Try again
          </button>
        </div>
      </main>
    )
  }
  if (state.status === 'anonymous') return <Navigate to={`/login/${role.toLowerCase()}`} replace />
  if (state.me.role !== role) return <Navigate to={homePath(state.me.role)} replace />
  return <Outlet />
}
