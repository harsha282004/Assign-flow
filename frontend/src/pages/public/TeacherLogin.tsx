import {
  ArrowLeft,
  ArrowRight,
  Eye,
  EyeOff,
  GraduationCap,
  Loader2,
  Lock,
  User,
} from 'lucide-react'
import { useState } from 'react'
import { Link, Navigate } from 'react-router-dom'
import { useLoginForm } from '../../auth/useLoginForm'
import LoginVideo from '../../components/login/LoginVideo'
import '../../student-login.css' // shared left-column look (page, brand, card, fields): identical to the student page
import '../../teacher-login.css'

const TEACHER_VIDEO = '/videos/teacher-login-background.mp4'

/**
 * Teacher (faculty) sign-in. Same layout and styling as the student page, with teacher wording and the classroom video.
 * Authentication is the existing flow (`useLoginForm('FACULTY')` -> AuthContext.login); only the presentation is new.
 */
export default function TeacherLogin() {
  const { register, errors, isSubmitting, serverError, submit, authenticatedHome } =
    useLoginForm('FACULTY')
  const [showPassword, setShowPassword] = useState(false)

  if (authenticatedHome) return <Navigate to={authenticatedHome} replace />

  const idError = errors.login_id?.message
  const pwError = errors.password?.message

  return (
    <main className="sl-page tl-page">
      <section className="sl-left" aria-labelledby="tl-brand">
        <div className="sl-stack">
          <h1 id="tl-brand" className="sl-brand">
            <GraduationCap className="sl-brand-icon" aria-hidden="true" />
            <span className="sl-brand-text">
              Assign<span className="sl-flow">Flow</span>
            </span>
          </h1>

          <div className="sl-card">
            <h2 className="sl-title">Welcome back, teacher</h2>
            <p className="sl-subtitle">
              Sign in to manage your classes, assignments and student submissions.
            </p>

            <form onSubmit={submit} noValidate className="sl-form">
              <div className="sl-field">
                <label htmlFor="tl-id">Faculty ID</label>
                <div className={`sl-input${idError ? ' invalid' : ''}`}>
                  <User size={18} className="sl-input-icon" aria-hidden="true" />
                  <input
                    id="tl-id"
                    type="text"
                    autoComplete="username"
                    autoCapitalize="characters"
                    spellCheck={false}
                    placeholder="e.g. FAC001"
                    aria-invalid={!!idError}
                    aria-describedby={idError ? 'tl-id-error' : undefined}
                    {...register('login_id')}
                  />
                </div>
                <p id="tl-id-error" className="sl-error" role={idError ? 'alert' : undefined}>
                  {idError}
                </p>
              </div>

              <div className="sl-field">
                <label htmlFor="tl-pw">Password</label>
                <div className={`sl-input${pwError ? ' invalid' : ''}`}>
                  <Lock size={18} className="sl-input-icon" aria-hidden="true" />
                  <input
                    id="tl-pw"
                    type={showPassword ? 'text' : 'password'}
                    autoComplete="current-password"
                    aria-invalid={!!pwError}
                    aria-describedby={pwError ? 'tl-pw-error' : undefined}
                    {...register('password')}
                  />
                  <button
                    type="button"
                    className="sl-eye"
                    onClick={() => setShowPassword((v) => !v)}
                    aria-label={showPassword ? 'Hide password' : 'Show password'}
                    aria-pressed={showPassword}
                  >
                    {showPassword ? (
                      <EyeOff size={18} aria-hidden="true" />
                    ) : (
                      <Eye size={18} aria-hidden="true" />
                    )}
                  </button>
                </div>
                <p id="tl-pw-error" className="sl-error" role={pwError ? 'alert' : undefined}>
                  {pwError}
                </p>
              </div>

              <div className="sl-server" aria-live="polite">
                {serverError && (
                  <p role="alert" className="sl-server-error">
                    {serverError}
                  </p>
                )}
              </div>

              <button type="submit" className="sl-submit" disabled={isSubmitting}>
                {isSubmitting ? (
                  <>
                    <Loader2 size={18} className="sl-spin" aria-hidden="true" /> Signing in…
                  </>
                ) : (
                  <>
                    Sign in <ArrowRight size={18} aria-hidden="true" />
                  </>
                )}
              </button>
            </form>

            <div className="sl-card-footer">AssignFlow · Faculty Portal</div>
          </div>

          <p className="sl-links">
            <Link to="/" className="sl-back">
              <ArrowLeft size={16} aria-hidden="true" /> Back to Home
            </Link>
            <span aria-hidden="true">·</span>
            <Link to="/login/student">Student login</Link>
          </p>
        </div>
      </section>

      <aside className="sl-right tl-right">
        {/* Teacher clip: continuous native loop (no 4-second cycle). */}
        <LoginVideo src={TEACHER_VIDEO} classPrefix="tl" cycleSeconds={null} />
      </aside>
    </main>
  )
}
