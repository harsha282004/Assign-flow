export type Role = 'FACULTY' | 'STUDENT'

export interface User {
  id: string
  login_id: string
  full_name: string
  role: Role
}

export interface LoginResponse {
  access_token: string
  token_type: 'bearer'
  expires_at: string
  user: User
}

export interface Section {
  id: string
  label: string
  semester: number
  name: string
}

export interface Subject {
  id: string
  code: string
  name: string
}

export interface Me extends User {
  section: Section | null
  subjects: (Subject & { faculty_name: string | null })[] | null
  teaching: { subject: Subject; section: Section }[] | null
}

export interface ApiErrorBody {
  error: { code: string; message: string; details?: Record<string, unknown> }
}

// --- Assignments (Phase 4) ---

export type AllowedType = 'pdf' | 'docx' | 'pptx' | 'zip' | 'png' | 'jpg'
export const ALLOWED_TYPES: AllowedType[] = ['pdf', 'docx', 'pptx', 'zip', 'png', 'jpg']

export type AssignmentStatus = 'DRAFT' | 'PUBLISHED' | 'ARCHIVED'
export type Timing = 'PENDING' | 'ON_TIME' | 'LATE' | 'MISSING'

export interface FacultyAssignmentSummary {
  id: string
  title: string
  assignment_type: AssignmentType
  status: AssignmentStatus
  subject: Subject
  section: Section
  original_deadline: string
  deadline: string
  published_at: string | null
  archived_at: string | null
  created_at: string
  expected_students: number
}

/** A reference document attached by the teacher (PDF / PPT / PPTX). No URL or storage key is ever sent. */
export interface Attachment {
  id: string
  original_filename: string
  mime_type: string
  file_type: 'PDF' | 'PPT' | 'PPTX' | string
  size_bytes: number
  uploaded_at: string
  previewable: boolean
}

export interface DeadlineChange {
  id: string
  old_deadline: string
  new_deadline: string
  changed_by_name: string
  changed_at: string
  reason: string | null
}

export interface FacultyAssignmentDetail extends FacultyAssignmentSummary {
  instructions: string
  allowed_types: AllowedType[]
  max_file_mb: number
  deadline_history: DeadlineChange[]
  attachments: Attachment[]
}

export type UploadContext = 'REGULAR' | 'LATE_APPROVED' | 'REVISION'

export interface VersionOut {
  id: string
  version_no: number
  original_filename: string
  mime_type: string
  size_bytes: number
  sha256: string
  uploaded_at: string
  deadline_at_upload: string
  upload_context: UploadContext
  timing_at_upload: 'ON_TIME' | 'LATE'
  timing_now: 'ON_TIME' | 'LATE'
}

export interface UploadResult {
  submission_id: string
  version_id: string
  version_no: number
  uploaded_at: string
  deadline_at_upload: string
  upload_context: UploadContext
  version_timing: 'ON_TIME' | 'LATE'
  submission_timing: Timing
  is_resubmitted: boolean
}

export interface StudentRef {
  id: string
  login_id: string
  full_name: string
}

// Stored status plus the derived EXPIRED / USED labels (architecture §15.1, §17.2).
export type RequestState = 'PENDING' | 'APPROVED' | 'REJECTED' | 'EXPIRED' | 'USED'
export type RequestStatus = 'NONE' | RequestState

// NOT_REVIEWED is derived: there is no review of the latest version yet.
export type ReviewStatus = 'NOT_REVIEWED' | 'UNDER_REVIEW' | 'ACCEPTED' | 'REVISION_REQUESTED'
export type RecordableReviewStatus = Exclude<ReviewStatus, 'NOT_REVIEWED'>

export interface ReviewOut {
  id: string
  version_no: number
  status: RecordableReviewStatus
  feedback: string | null
  reviewer_name: string
  reviewed_at: string
  is_current: boolean
}

export interface ReviewInput {
  status: RecordableReviewStatus
  feedback?: string
  expected_version_no?: number
}

export type TimelineEventType =
  | 'ASSIGNMENT_CREATED'
  | 'ASSIGNMENT_PUBLISHED'
  | 'ASSIGNMENT_ARCHIVED'
  | 'ASSIGNMENT_RESTORED'
  | 'DEADLINE_CHANGED'
  | 'LATE_REQUESTED'
  | 'REQUEST_APPROVED'
  | 'REQUEST_REJECTED'
  | 'VERSION_UPLOADED'
  | 'REVIEW_RECORDED'
  | 'REQUEST_WINDOW_EXPIRED'
  | 'DEADLINE_PASSED_NO_SUBMISSION'

export interface TimelineEvent {
  type: TimelineEventType
  at: string
  actor: string | null
  summary: string
  data: Record<string, unknown>
  derived: boolean
}

export interface WhyThisStatus {
  timing: Timing
  headline: string
  lines: string[]
}

export interface RosterRow {
  student: StudentRef
  timing: Timing
  late_approved: boolean
  is_resubmitted: boolean
  version_count: number
  latest_uploaded_at: string | null
  request_status: RequestStatus
  review_status: ReviewStatus
}

export interface StudentSubmissionDetail {
  student: StudentRef
  deadline: string
  original_deadline: string
  timing: Timing
  late_approved: boolean
  is_resubmitted: boolean
  request_status: RequestStatus
  submission_id: string | null
  latest_version_no: number
  review_status: ReviewStatus
  reviews: ReviewOut[]
  versions: VersionOut[]
  events: TimelineEvent[]
  why_this_status: WhyThisStatus
}

// --- Faculty Submission Health Board (Phase 7) ---

export interface Counts {
  expected: number
  on_time: number
  late: number
  late_approved: number
  pending: number
  missing: number
  submitted: number
  resubmitted: number
  under_review: number
  accepted: number
  revision_requested: number
  not_reviewed: number
  reviewed: number
  requests_pending: number
}

export interface AssignmentRef {
  id: string
  title: string
  subject: Subject
  section: Section
}

export interface AssignmentCounts extends Counts {
  assignment: AssignmentRef
  deadline: string
}

export interface Overview {
  totals: Counts
  assignments: AssignmentCounts[]
}

export interface OverviewStudentRow {
  assignment: AssignmentRef
  deadline: string
  student: StudentRef
  timing: Timing
  late_approved: boolean
  is_resubmitted: boolean
  version_count: number
  latest_uploaded_at: string | null
  review_status: ReviewStatus
  request_status: RequestStatus
}

export interface OverviewStudents {
  total: number
  items: OverviewStudentRow[]
  truncated: boolean
}

/** Subject / section filter shared by the faculty dashboard, assignment list, late requests and the board. */
export interface ScopeFilter {
  subject_id?: string
  section_id?: string
}

export interface DeletionCheck {
  assignment_id: string
  title: string
  status: AssignmentStatus
  can_delete: boolean
  action: 'DELETE' | 'ARCHIVE' | 'RESTORE'
  can_archive: boolean
  student_history: boolean
  blockers: Record<string, number>
  reference_files: number
  message: string | null
}

export interface DeletionResult {
  deleted: boolean
  assignment_id: string
  title: string
  files_removed: number
  files_left: number
}

export interface OverviewFilters {
  assignment_id?: string
  subject_id?: string
  section_id?: string
  timing?: Timing
  review_status?: ReviewStatus
}

// --- Notifications (Phase 7) ---

export interface AppNotification {
  id: string
  type: string
  title: string
  body: string
  ref_type: string | null
  ref_id: string | null
  created_at: string
  read_at: string | null
}

export interface Alert {
  type: 'DUE_24H' | 'DUE_3H' | 'MISSING' | 'WINDOW_CLOSING' | 'WINDOW_EXPIRED'
  assignment_id: string
  assignment_title: string
  message: string
  at: string
}

export interface NotificationsResponse {
  alerts: Alert[]
  items: AppNotification[]
  unread_count: number
}

export interface LateRequest {
  id: string
  status: 'PENDING' | 'APPROVED' | 'REJECTED'
  state: RequestState
  reason: string
  requested_at: string
  deadline_at_request: string
  decided_by_name: string | null
  decided_at: string | null
  decision_note: string | null
  window_start: string | null
  window_end: string | null
}

export interface FacultyLateRequest extends LateRequest {
  student: StudentRef
  assignment: { id: string; title: string; subject: Subject; section: Section }
  current_deadline: string
}

export interface FacultyLateRequestDetail extends FacultyLateRequest {
  submission_timing: Timing
  versions: VersionOut[]
}

export interface LateDecisionInput {
  decision: 'APPROVE' | 'REJECT'
  note?: string
  window_hours?: number
}

export interface StudentAssignmentItem {
  id: string
  title: string
  assignment_type: AssignmentType
  /** Quizzes only: the student's own attempt state, size and score. */
  quiz_status: QuizStatus | null
  question_count: number | null
  total_marks: number | null
  duration_minutes: number | null
  quiz_score: number | null
  subject: Subject
  faculty_name: string | null
  published_at: string
  deadline: string
  timing: Timing
  late_approved: boolean
  is_resubmitted: boolean
  request_status: RequestStatus
  /** ARCHIVED: kept for the student's own history, read-only, outside the active work. */
  assignment_state: 'ACTIVE' | 'ARCHIVED'
  review_status: ReviewStatus
  latest_feedback: string | null
}

export interface StudentAssignmentDetail extends StudentAssignmentItem {
  instructions: string
  allowed_types: AllowedType[]
  max_file_mb: number
  original_deadline: string
  section: Section
  versions: VersionOut[]
  can_upload: boolean
  upload_blocked_reason: 'DEADLINE_PASSED' | 'SUBMISSION_ACCEPTED' | 'ARCHIVED' | null
  late_request: LateRequest | null
  can_request_late: boolean
  reviews: ReviewOut[]
  events: TimelineEvent[]
  why_this_status: WhyThisStatus
  attachments: Attachment[]
}

export interface AssignmentCreateInput {
  title: string
  instructions: string
  subject_id: string
  section_id: string
  deadline: string
  allowed_types: AllowedType[]
  max_file_mb: number
  publish: boolean
}

export type AssignmentUpdateInput = Partial<
  Pick<
    AssignmentCreateInput,
    'title' | 'instructions' | 'deadline' | 'allowed_types' | 'max_file_mb'
  >
>

// --- Quizzes ---

export type AssignmentType = 'FILE' | 'QUIZ'
export type QuizStatus = 'NOT_STARTED' | 'IN_PROGRESS' | 'SUBMITTED'
export type QuestionType = 'SINGLE_CHOICE' | 'MULTIPLE_SELECT' | 'TRUE_FALSE'

export interface QuizOptionInput {
  text: string
  is_correct: boolean
}
export interface QuizQuestionInput {
  question_type: QuestionType
  text: string
  marks: number
  options: QuizOptionInput[]
}
export interface QuizDefinitionInput {
  title: string
  description: string | null
  instructions: string
  deadline: string
  duration_minutes: number | null
  questions: QuizQuestionInput[]
}
export interface QuizCreateInput extends QuizDefinitionInput {
  subject_id: string
  section_id: string
  publish: boolean
}

export interface QuizFacultyDetail extends FacultyAssignmentSummary {
  instructions: string
  description: string | null
  duration_minutes: number | null
  question_count: number
  total_marks: number
  questions: {
    id: string
    question_type: QuestionType
    text: string
    marks: number
    options: { id: string; text: string; is_correct: boolean }[]
  }[]
}

export interface QuizParticipation {
  assignment_id: string
  total_marks: number
  expected_students: number
  started: number
  submitted: number
  average_score: number | null
  participants: {
    student_id: string
    login_id: string
    full_name: string
    status: QuizStatus
    started_at: string | null
    submitted_at: string | null
    score: number | null
    max_score: number | null
    timed_out: boolean
  }[]
}

export interface QuizAttemptState {
  id: string
  status: 'IN_PROGRESS' | 'SUBMITTED'
  started_at: string
  expires_at: string
  submitted_at: string | null
  timed_out: boolean
  answers: Record<string, string[]>
}

export interface QuizStudentView {
  assignment_id: string
  title: string
  description: string | null
  instructions: string
  subject: Subject
  section: Section
  faculty_name: string | null
  deadline: string
  duration_minutes: number | null
  question_count: number
  total_marks: number
  can_attempt: boolean
  blocked_reason: 'DEADLINE_PASSED' | 'ARCHIVED' | null
  attempt: QuizAttemptState | null
  questions:
    | {
        id: string
        question_type: QuestionType
        text: string
        marks: number
        options: { id: string; text: string }[]
      }[]
    | null
}

export interface QuizResult {
  attempt_id: string
  assignment_id: string
  title: string
  started_at: string
  submitted_at: string
  timed_out: boolean
  score: number
  max_score: number
  answers_released: boolean
  questions: {
    question_id: string
    text: string
    marks: number
    awarded: number
    question_type: QuestionType
    options: { id: string; text: string }[]
    selected_option_ids: string[]
    correct_option_ids: string[] | null
  }[]
}
