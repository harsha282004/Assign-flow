import {
  BarChart3,
  Clock,
  FilePlus2,
  FileText,
  GraduationCap,
  Home,
  LogOut,
  Menu,
  UploadCloud,
  X,
  type LucideIcon,
} from 'lucide-react'
import { useEffect, useState } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { useLateRequests } from '../api/queries'
import { useAuth } from '../auth/useAuth'
import NotificationBell from '../components/NotificationBell'
import { initials } from '../lib/time'

/** Number of requests waiting for a decision (real data, refreshed every minute). */
function PendingCount() {
  const { data } = useLateRequests('PENDING', true)
  if (!data || data.length === 0) return null
  return (
    <span className="nav-count" aria-label={`${data.length} pending`}>
      {data.length}
    </span>
  )
}

interface NavItem {
  to: string
  label: string
  icon: LucideIcon
  end?: boolean
  badge?: boolean
}

const STUDENT_NAV: NavItem[] = [
  { to: '/student', label: 'Dashboard', icon: Home, end: true },
  { to: '/student/assignments', label: 'Assignments', icon: FileText },
  { to: '/student/submissions', label: 'Submissions', icon: UploadCloud },
  { to: '/student/late-requests', label: 'Late Requests', icon: Clock },
  { to: '/student/timeline', label: 'Timeline', icon: BarChart3 },
]

const FACULTY_NAV: NavItem[] = [
  { to: '/faculty', label: 'Dashboard', icon: Home, end: true },
  { to: '/faculty/assignments', label: 'Assignments', icon: FileText },
  { to: '/faculty/board', label: 'Submissions', icon: BarChart3 },
  { to: '/faculty/late-requests', label: 'Late Requests', icon: Clock, badge: true },
  { to: '/faculty/assignments/new', label: 'New assignment', icon: FilePlus2 },
]

export default function AppLayout() {
  const { state, logout } = useAuth()
  const [menuOpen, setMenuOpen] = useState(false)
  const { pathname } = useLocation()

  // Close the mobile menu on navigation.
  useEffect(() => setMenuOpen(false), [pathname])

  if (state.status !== 'authenticated') return null
  const { me } = state
  const items = me.role === 'FACULTY' ? FACULTY_NAV : STUDENT_NAV

  async function onLogout() {
    // Once the session ends, RequireRole sends the user to that role's login page.
    await logout()
  }

  return (
    <div className="shell">
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <header className="topbar">
        <span className="brand">
          <span className="brand-mark" aria-hidden="true">
            <GraduationCap size={26} />
          </span>
          <strong>
            Assign<span>Flow</span>
          </strong>
        </span>
        <button
          className="menu-toggle secondary"
          aria-expanded={menuOpen}
          aria-controls="main-nav"
          aria-label={menuOpen ? 'Close menu' : 'Open menu'}
          onClick={() => setMenuOpen((v) => !v)}
        >
          {menuOpen ? <X size={20} /> : <Menu size={20} />}
        </button>
        <nav id="main-nav" aria-label="Main" className={menuOpen ? 'open' : ''}>
          {items.map(({ to, label, icon: Icon, end, badge }) => (
            <NavLink key={to} to={to} end={end}>
              <Icon size={18} aria-hidden="true" />
              {label}
              {badge && <PendingCount />}
            </NavLink>
          ))}
        </nav>
        <div className="user">
          <NotificationBell />
          <span className="avatar" aria-hidden="true">
            {initials(me.full_name)}
          </span>
          <span className="user-id">
            <strong>{me.full_name}</strong>
            <span className="muted small">{me.login_id}</span>
          </span>
          <button className="secondary icon-text" onClick={onLogout}>
            <LogOut size={16} aria-hidden="true" />
            <span>Log out</span>
          </button>
        </div>
      </header>
      <main className="content" id="main">
        <Outlet />
      </main>
    </div>
  )
}
