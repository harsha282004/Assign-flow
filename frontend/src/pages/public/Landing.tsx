import { ArrowRight, ClipboardCheck, GraduationCap, Menu, Users, X } from 'lucide-react'
import { useState } from 'react'
import { Link, Navigate } from 'react-router-dom'
import FeaturesShowcase from '../../components/landing/FeaturesShowcase'
import HealthCheck from '../../components/HealthCheck'
import { homePath, useAuth } from '../../auth/useAuth'
import '../../landing.css'

/** Public landing page. Routes and authentication are unchanged: the buttons only link to the existing login pages. */
export default function Landing() {
  const { state } = useAuth()
  const [menuOpen, setMenuOpen] = useState(false)
  if (state.status === 'authenticated') return <Navigate to={homePath(state.me.role)} replace />

  const close = () => setMenuOpen(false)

  return (
    <div className="lp">
      <header className="lp-header">
        <a className="lp-logo" href="#top" aria-label="AssignFlow home" onClick={close}>
          <GraduationCap size={30} aria-hidden="true" />
          <span>
            Assign<b>Flow</b>
          </span>
        </a>
        <button
          type="button"
          className="lp-menu-btn"
          aria-expanded={menuOpen}
          aria-controls="lp-nav"
          aria-label={menuOpen ? 'Close menu' : 'Open menu'}
          onClick={() => setMenuOpen((o) => !o)}
        >
          {menuOpen ? <X size={22} aria-hidden="true" /> : <Menu size={22} aria-hidden="true" />}
        </button>
        <nav id="lp-nav" className={`lp-nav${menuOpen ? ' open' : ''}`} aria-label="Main">
          <a className="active" href="#top" aria-current="page" onClick={close}>
            Home
          </a>
          <a href="#features" onClick={close}>
            Features
          </a>
          <a href="#students" onClick={close}>
            For Students
          </a>
          <a href="#faculty" onClick={close}>
            For Faculty
          </a>
          <a href="#about" onClick={close}>
            About
          </a>
          <a className="lp-cta lp-cta-mobile" href="#access" onClick={close}>
            Get Started <ArrowRight size={16} aria-hidden="true" />
          </a>
        </nav>
        <a className="lp-cta lp-cta-desktop" href="#access">
          Get Started <ArrowRight size={16} aria-hidden="true" />
        </a>
      </header>

      <main id="top">
        <section className="lp-hero" aria-labelledby="lp-title">
          <div className="lp-hero-copy">
            <span className="lp-badge">Student Assignment &amp; Late Work Manager</span>
            <h1 id="lp-title">
              Organize Today,
              <span>Achieve Tomorrow.</span>
            </h1>
            <p>
              A simple and powerful platform to manage assignments, submit work, track deadlines and
              handle late requests — all in one place.
            </p>
            <div className="lp-actions" id="access">
              <Link className="lp-btn lp-btn-primary" to="/login/student">
                <GraduationCap size={18} aria-hidden="true" /> Student Login{' '}
                <ArrowRight size={18} aria-hidden="true" />
              </Link>
              <Link className="lp-btn lp-btn-secondary" to="/login/faculty">
                <Users size={18} aria-hidden="true" /> Faculty Login{' '}
                <ArrowRight size={18} aria-hidden="true" />
              </Link>
            </div>
          </div>
          <div className="lp-hero-art" aria-hidden="true">
            <img src="/images/landing-hero.png" alt="" width={1266} height={975} decoding="async" />
          </div>
        </section>

        <FeaturesShowcase />

        <section className="lp-section lp-two" aria-label="Who it is for">
          <article id="students" className="lp-panel">
            <h2>For Students</h2>
            <p>
              See every assignment for your class in deadline order, upload your work, track reviews
              and feedback, and ask for late submission when you need it.
            </p>
            <Link className="lp-link" to="/login/student">
              Student Login <ArrowRight size={16} aria-hidden="true" />
            </Link>
          </article>
          <article id="faculty" className="lp-panel">
            <h2>For Faculty</h2>
            <p>
              Create assignments for the classes you teach, attach reference materials, review
              submissions, and decide on late requests with a full audit trail.
            </p>
            <Link className="lp-link" to="/login/faculty">
              Faculty Login <ArrowRight size={16} aria-hidden="true" />
            </Link>
          </article>
        </section>

        <section id="about" className="lp-section lp-about" aria-labelledby="lp-about-h">
          <ClipboardCheck size={28} aria-hidden="true" />
          <h2 id="lp-about-h">About AssignFlow</h2>
          <p>
            AssignFlow is a Student Assignment Submission &amp; Late Work Manager. It keeps
            deadlines, submissions, reviews and late-work requests in one clear, trustworthy place.
            The data shown here is demo data with fictional accounts.
          </p>
          <details className="lp-status">
            <summary>System status</summary>
            <HealthCheck />
          </details>
        </section>
      </main>
    </div>
  )
}
