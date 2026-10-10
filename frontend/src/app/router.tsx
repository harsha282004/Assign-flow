import { Link, createBrowserRouter } from 'react-router-dom'
import RequireRole from '../components/RequireRole'
import AppLayout from '../layouts/AppLayout'
import AssignmentDetail from '../pages/faculty/AssignmentDetail'
import AssignmentList from '../pages/faculty/AssignmentList'
import AssignmentNew from '../pages/faculty/AssignmentNew'
import HealthBoard from '../pages/faculty/HealthBoard'
import LateRequestDetail from '../pages/faculty/LateRequestDetail'
import LateRequests from '../pages/faculty/LateRequests'
import StudentSubmission from '../pages/faculty/StudentSubmission'
import SubmissionLink from '../pages/faculty/SubmissionLink'
import Landing from '../pages/public/Landing'
import StudentLogin from '../pages/public/StudentLogin'
import TeacherLogin from '../pages/public/TeacherLogin'
import StudentAssignmentDetail from '../pages/student/AssignmentDetail'
import { StudentCollection, StudentTimeline } from '../pages/student/Collection'
import StudentDashboard from '../pages/student/Dashboard'
import FacultyDashboard from '../pages/faculty/Dashboard'

function NotFound() {
  return (
    <main className="page">
      <section className="card">
        <h1>Page not found</h1>
        <p>
          <Link to="/">Go to the start page</Link>
        </p>
      </section>
    </main>
  )
}

export const router = createBrowserRouter([
  { path: '/', element: <Landing /> },
  { path: '/login/faculty', element: <TeacherLogin /> },
  { path: '/login/student', element: <StudentLogin /> },
  {
    element: <RequireRole role="STUDENT" />,
    children: [
      {
        element: <AppLayout />,
        children: [
          { path: '/student', element: <StudentDashboard /> },
          { path: '/student/assignments', element: <StudentCollection mode="assignments" /> },
          { path: '/student/submissions', element: <StudentCollection mode="submissions" /> },
          { path: '/student/late-requests', element: <StudentCollection mode="late-requests" /> },
          { path: '/student/timeline', element: <StudentTimeline /> },
          { path: '/student/assignments/:id', element: <StudentAssignmentDetail /> },
        ],
      },
    ],
  },
  {
    element: <RequireRole role="FACULTY" />,
    children: [
      {
        element: <AppLayout />,
        children: [
          { path: '/faculty', element: <FacultyDashboard /> },
          { path: '/faculty/assignments', element: <AssignmentList /> },
          { path: '/faculty/assignments/new', element: <AssignmentNew /> },
          { path: '/faculty/assignments/:id', element: <AssignmentDetail /> },
          { path: '/faculty/submissions/:submissionId', element: <SubmissionLink /> },
          { path: '/faculty/assignments/:id/students/:studentId', element: <StudentSubmission /> },
          { path: '/faculty/board', element: <HealthBoard /> },
          { path: '/faculty/late-requests', element: <LateRequests /> },
          { path: '/faculty/late-requests/:id', element: <LateRequestDetail /> },
        ],
      },
    ],
  },
  { path: '*', element: <NotFound /> },
])
