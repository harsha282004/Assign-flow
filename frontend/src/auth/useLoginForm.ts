import { zodResolver } from '@hookform/resolvers/zod'
import { useRef, useState } from 'react'
import { useForm } from 'react-hook-form'
import { useNavigate } from 'react-router-dom'
import { z } from 'zod'
import { errorMessage } from '../api/client'
import type { Role } from '../api/types'
import { homePath, useAuth } from './useAuth'

// Client-side validation is a convenience only; the server validates everything again.
const schema = z.object({
  login_id: z.string().trim().min(1, 'Enter your ID'),
  password: z.string().min(1, 'Enter your password'),
})
export type LoginFormValues = z.infer<typeof schema>

/**
 * The one login flow for both portals (the faculty page and the student page render it differently).
 * It calls the existing `login(role, id, password)` of the AuthContext: nothing here talks to the API directly,
 * stores a token or decides who is allowed in. After a successful login the user is routed by the role the server
 * reports. `authenticatedHome` is set when a session already exists.
 */
export function useLoginForm(role: Role) {
  const { state, login } = useAuth()
  const navigate = useNavigate()
  const [serverError, setServerError] = useState<string | null>(null)
  const inFlight = useRef(false) // set synchronously: a double click can arrive before React disables the button
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<LoginFormValues>({ resolver: zodResolver(schema) })

  async function onSubmit(values: LoginFormValues) {
    if (inFlight.current) return
    inFlight.current = true
    setServerError(null)
    try {
      // Route by the role the server reports, not by the form that was used.
      const actual = await login(role, values.login_id, values.password)
      navigate(homePath(actual), { replace: true })
    } catch (error) {
      setServerError(errorMessage(error))
    } finally {
      inFlight.current = false
    }
  }

  return {
    register,
    errors,
    isSubmitting,
    serverError,
    submit: handleSubmit(onSubmit),
    authenticatedHome: state.status === 'authenticated' ? homePath(state.me.role) : null,
  }
}
