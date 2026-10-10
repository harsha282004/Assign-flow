import axios from 'axios'
import { createContext, useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { api, setUnauthorizedHandler } from '../api/client'
import { queryClient } from '../api/queryClient'
import type { LoginResponse, Me, Role } from '../api/types'
import { clearToken, getToken, setToken } from './tokenStorage'

export type AuthState =
  | { status: 'loading'; me: null }
  | { status: 'anonymous'; me: null }
  // A token exists but the API could not be reached (network error or 5xx): keep the session, offer a retry.
  | { status: 'unavailable'; me: null }
  | { status: 'authenticated'; me: Me }

export interface AuthContextValue {
  state: AuthState
  login: (role: Role, loginId: string, password: string) => Promise<Role>
  logout: () => Promise<void>
  retrySession: () => void
}

export const AuthContext = createContext<AuthContextValue | null>(null)

async function fetchMe(): Promise<Me> {
  const res = await api.get<Me>('/auth/me')
  return res.data
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>(() =>
    getToken() ? { status: 'loading', me: null } : { status: 'anonymous', me: null },
  )

  // Any 401 from the API (expired / revoked token) ends the session centrally.
  useEffect(() => {
    setUnauthorizedHandler(() => {
      queryClient.clear()
      setState({ status: 'anonymous', me: null })
    })
    return () => setUnauthorizedHandler(null)
  }, [])

  // Restore the session after a page refresh; the role always comes from the server (/auth/me).
  // Only a 401 ends the session. If the API is merely unreachable the token is kept, so a short outage does
  // not log anyone out.
  const restore = useCallback((isCancelled: () => boolean = () => false) => {
    if (!getToken()) return
    setState({ status: 'loading', me: null })
    fetchMe()
      .then((me) => !isCancelled() && setState({ status: 'authenticated', me }))
      .catch((error: unknown) => {
        if (isCancelled()) return
        if (axios.isAxiosError(error) && error.response?.status === 401) {
          clearToken()
          setState({ status: 'anonymous', me: null })
        } else {
          setState({ status: 'unavailable', me: null })
        }
      })
  }, [])

  useEffect(() => {
    let cancelled = false
    restore(() => cancelled)
    return () => {
      cancelled = true
    }
  }, [restore])

  const retrySession = useCallback(() => restore(), [restore])

  const login = useCallback(async (role: Role, loginId: string, password: string) => {
    const res = await api.post<LoginResponse>('/auth/login', {
      role,
      login_id: loginId,
      password,
    })
    setToken(res.data.access_token)
    try {
      const me = await fetchMe()
      setState({ status: 'authenticated', me })
      return me.role
    } catch (error) {
      clearToken()
      setState({ status: 'anonymous', me: null })
      throw error
    }
  }, [])

  const logout = useCallback(async () => {
    try {
      await api.post('/auth/logout')
    } catch {
      // Even if revocation could not be recorded (e.g. server unreachable), end the local session.
    }
    clearToken()
    queryClient.clear() // never keep one user's data around for the next login
    setState({ status: 'anonymous', me: null })
  }, [])

  const value = useMemo(
    () => ({ state, login, logout, retrySession }),
    [state, login, logout, retrySession],
  )
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
