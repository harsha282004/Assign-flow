import axios, { AxiosError } from 'axios'
import { clearToken, getToken } from '../auth/tokenStorage'
import type { ApiErrorBody } from './types'

// Public, build-time, browser-reachable URL (never an internal Docker hostname).
export const API_BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? ''

export const api = axios.create({ baseURL: API_BASE_URL, timeout: 15000 })

let onUnauthorized: (() => void) | null = null

/** AuthContext registers this so a 401 anywhere logs the user out centrally. */
export function setUnauthorizedHandler(handler: (() => void) | null): void {
  onUnauthorized = handler
}

api.interceptors.request.use((config) => {
  const token = getToken()
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

api.interceptors.response.use(
  (response) => response,
  (error: AxiosError<ApiErrorBody>) => {
    // A failed login is also a 401; that must show the form error, not trigger a logout.
    const isLogin = error.config?.url?.endsWith('/auth/login')
    if (error.response?.status === 401 && !isLogin) {
      clearToken()
      onUnauthorized?.()
    }
    return Promise.reject(error)
  },
)

/** Error bodies of blob requests arrive as Blobs: turn them back into the API's message. */
async function blobError(error: unknown): Promise<never> {
  if (axios.isAxiosError(error) && error.response?.data instanceof Blob) {
    try {
      const body = JSON.parse(await error.response.data.text()) as ApiErrorBody
      throw new Error(body.error.message)
    } catch (inner) {
      if (inner instanceof Error && inner.message) throw inner
    }
  }
  throw error
}

/** Authenticated download of the ORIGINAL file: the token is a Bearer header, so a plain link cannot be used. */
export async function downloadFile(path: string, filename: string): Promise<void> {
  try {
    const res = await api.get<Blob>(path, { responseType: 'blob', timeout: 120_000 })
    const url = URL.createObjectURL(res.data)
    const link = document.createElement('a')
    link.href = url
    link.download = filename
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(url)
  } catch (error) {
    return blobError(error)
  }
}

export const downloadVersion = (versionId: string, filename: string) =>
  downloadFile(`/files/versions/${versionId}`, filename)

/** Fetch a preview (inline PDF / image) as a Blob. The caller owns the object URL and must revoke it. */
export async function fetchPreview(path: string): Promise<Blob> {
  try {
    const res = await api.get<Blob>(path, { responseType: 'blob', timeout: 120_000 })
    return res.data
  } catch (error) {
    return blobError(error)
  }
}

/** Human-readable message from the API error envelope, or a safe fallback. */
export function errorMessage(error: unknown): string {
  if (axios.isAxiosError<ApiErrorBody>(error)) {
    if (error.response?.data?.error?.message) return error.response.data.error.message
    if (!error.response) return 'Cannot reach the server. Check your connection and try again.'
  }
  if (error instanceof Error && error.message) return error.message
  return 'Something went wrong. Please try again.'
}
