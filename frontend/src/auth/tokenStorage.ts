// Access token lives in sessionStorage (architecture §13.2): it survives a refresh but not closing the tab.
// Storage can throw (private mode, blocked site data), so every access is guarded.
const KEY = 'assignflow.token'

export function getToken(): string | null {
  try {
    return sessionStorage.getItem(KEY)
  } catch {
    return null
  }
}

export function setToken(token: string): void {
  try {
    sessionStorage.setItem(KEY, token)
  } catch {
    /* session will simply not survive a refresh */
  }
}

export function clearToken(): void {
  try {
    sessionStorage.removeItem(KEY)
  } catch {
    /* nothing to clear */
  }
}
