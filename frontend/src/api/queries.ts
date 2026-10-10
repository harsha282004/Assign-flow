import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from './client'
import type {
  Attachment,
  AssignmentCreateInput,
  DeletionCheck,
  DeletionResult,
  ScopeFilter,
  AssignmentUpdateInput,
  FacultyAssignmentDetail,
  FacultyAssignmentSummary,
  FacultyLateRequest,
  FacultyLateRequestDetail,
  LateDecisionInput,
  LateRequest,
  NotificationsResponse,
  Overview,
  OverviewFilters,
  OverviewStudents,
  QuizAttemptState,
  QuizCreateInput,
  QuizDefinitionInput,
  QuizFacultyDetail,
  QuizParticipation,
  QuizResult,
  QuizStudentView,
  ReviewInput,
  ReviewOut,
  RequestState,
  StudentAssignmentDetail,
  RosterRow,
  StudentAssignmentItem,
  StudentSubmissionDetail,
  UploadResult,
} from './types'

export const keys = {
  facultyList: ['faculty', 'assignments'] as const,
  facultyListFiltered: (f: ScopeFilter, state: ListState) =>
    ['faculty', 'assignments', 'list', state, f] as const,
  studentArchived: ['student', 'assignments', 'archived'] as const,
  facultyDetail: (id: string) => ['faculty', 'assignments', id] as const,
  studentList: ['student', 'assignments'] as const,
  studentDetail: (id: string) => ['student', 'assignments', id] as const,
  roster: (id: string) => ['faculty', 'assignments', id, 'roster'] as const,
  studentSubmission: (id: string, studentId: string) =>
    ['faculty', 'assignments', id, 'students', studentId] as const,
  lateRequests: (state: string) => ['faculty', 'late-requests', 'list', state] as const,
  lateRequest: (id: string) => ['faculty', 'late-requests', 'detail', id] as const,
  notifications: ['notifications'] as const,
}

// --- Faculty ---

/** My assignments; the optional subject / section filter is applied (and authorised) by the server. */
export type ListState = 'active' | 'archived' | 'all'

export function useFacultyAssignments(filter: ScopeFilter = {}, state: ListState = 'all') {
  return useQuery({
    queryKey: keys.facultyListFiltered(filter, state),
    gcTime: 0, // switching the subject / section filter must never flash another moment's numbers
    queryFn: async () =>
      (
        await api.get<FacultyAssignmentSummary[]>('/faculty/assignments', {
          params: { ...filter, state },
        })
      ).data,
  })
}

export function useFacultyAssignment(id: string) {
  return useQuery({
    queryKey: keys.facultyDetail(id),
    queryFn: async () =>
      (await api.get<FacultyAssignmentDetail>(`/faculty/assignments/${id}`)).data,
  })
}

/** Every faculty mutation returns the fresh detail, so the cache is updated and lists are refetched. */
function useFacultyMutation<V>(run: (vars: V) => Promise<FacultyAssignmentDetail>) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: run,
    onSuccess: (detail) => {
      qc.setQueryData(keys.facultyDetail(detail.id), detail)
      void qc.invalidateQueries({ queryKey: keys.facultyList })
      // Published assignments appear in / change for students.
      void qc.invalidateQueries({ queryKey: keys.studentList })
      void qc.invalidateQueries({ queryKey: ['notifications'] })
      void qc.invalidateQueries({ queryKey: ['faculty', 'overview'] })
      void qc.invalidateQueries({ queryKey: keys.studentDetail(detail.id) })
    },
  })
}

export function useCreateAssignment() {
  return useFacultyMutation<AssignmentCreateInput>(
    async (input) => (await api.post<FacultyAssignmentDetail>('/faculty/assignments', input)).data,
  )
}

export function useUpdateAssignment(id: string) {
  return useFacultyMutation<AssignmentUpdateInput>(
    async (input) =>
      (await api.patch<FacultyAssignmentDetail>(`/faculty/assignments/${id}`, input)).data,
  )
}

export function usePublishAssignment(id: string) {
  return useFacultyMutation<void>(
    async () =>
      (await api.post<FacultyAssignmentDetail>(`/faculty/assignments/${id}/publish`)).data,
  )
}

export function useChangeDeadline(id: string) {
  return useFacultyMutation<{ new_deadline: string; reason?: string }>(
    async (input) =>
      (await api.patch<FacultyAssignmentDetail>(`/faculty/assignments/${id}/deadline`, input)).data,
  )
}

/** Why (not) an assignment can be permanently deleted. Read-only; fetched when the delete dialog opens. */
export function useDeletionCheck(assignmentId: string, enabled: boolean) {
  return useQuery({
    queryKey: ['faculty', 'deletion-check', assignmentId] as const,
    enabled,
    gcTime: 0, // never reuse an old answer: history may have appeared since
    queryFn: async () =>
      (await api.get<DeletionCheck>(`/faculty/assignments/${assignmentId}/deletion-check`)).data,
  })
}

/** Archive / restore: reversible, nothing is deleted. Every list, count and student view is refreshed. */
function useStateChange(assignmentId: string, action: 'archive' | 'restore') {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (reason?: string) =>
      (
        await api.post<FacultyAssignmentDetail>(
          `/faculty/assignments/${assignmentId}/${action}`,
          reason ? { reason } : {},
        )
      ).data,
    onSettled: async () => {
      await Promise.all([
        qc.invalidateQueries({ queryKey: ['faculty'] }),
        qc.invalidateQueries({ queryKey: ['student'] }),
        qc.invalidateQueries({ queryKey: ['notifications'] }),
      ])
    },
  })
}

export const useArchiveAssignment = (id: string) => useStateChange(id, 'archive')
export const useRestoreAssignment = (id: string) => useStateChange(id, 'restore')

export function useDeleteAssignment(assignmentId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async () =>
      (await api.delete<DeletionResult>(`/faculty/assignments/${assignmentId}`)).data,
    // Also on errors (a 409 means the screen should show the current state); drop the deleted detail first.
    onSettled: async (_data, error) => {
      if (!error) qc.removeQueries({ queryKey: keys.facultyDetail(assignmentId) })
      await Promise.all([
        qc.invalidateQueries({ queryKey: ['faculty'] }),
        qc.invalidateQueries({ queryKey: ['student'] }),
        qc.invalidateQueries({ queryKey: ['notifications'] }),
      ])
    },
  })
}

/** Upload one reference document to a DRAFT assignment (multipart; the server validates the content). */
export async function uploadAttachment(assignmentId: string, file: File): Promise<Attachment> {
  const form = new FormData()
  form.append('file', file)
  const res = await api.post<Attachment>(`/faculty/assignments/${assignmentId}/attachments`, form, {
    timeout: 120_000,
  })
  return res.data
}

export function useUploadAttachment(assignmentId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (file: File) => uploadAttachment(assignmentId, file),
    onSettled: () => qc.invalidateQueries({ queryKey: keys.facultyDetail(assignmentId) }),
  })
}

export function useDeleteAttachment(assignmentId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (attachmentId: string) => {
      await api.delete(`/faculty/assignments/${assignmentId}/attachments/${attachmentId}`)
    },
    onSettled: () => qc.invalidateQueries({ queryKey: keys.facultyDetail(assignmentId) }),
  })
}

// --- Student ---

export function useStudentAssignments() {
  return useQuery({
    queryKey: keys.studentList,
    queryFn: async () => (await api.get<StudentAssignmentItem[]>('/student/assignments')).data,
    refetchInterval: 60_000, // deadlines and statuses are server-side; poll gently (architecture §21.3)
  })
}

/** Archived assignments on which the student has their own history (read-only). */
export function useStudentArchived() {
  return useQuery({
    queryKey: keys.studentArchived,
    queryFn: async () =>
      (await api.get<StudentAssignmentItem[]>('/student/assignments/archived')).data,
  })
}

export function useStudentAssignment(id: string) {
  return useQuery({
    queryKey: keys.studentDetail(id),
    queryFn: async () =>
      (await api.get<StudentAssignmentDetail>(`/student/assignments/${id}`)).data,
  })
}

export function useUploadSubmission(assignmentId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({
      file,
      onProgress,
    }: {
      file: File
      onProgress: (percent: number) => void
    }) => {
      const form = new FormData()
      form.append('file', file)
      const res = await api.post<UploadResult>(
        `/student/assignments/${assignmentId}/submissions`,
        form,
        {
          timeout: 120_000,
          onUploadProgress: (e) => e.total && onProgress(Math.round((e.loaded / e.total) * 100)),
        },
      )
      return res.data
    },
    // Returning the promise makes the mutation wait for fresh data, so the success message and the
    // version list always appear together.
    onSuccess: () =>
      Promise.all([
        qc.invalidateQueries({ queryKey: keys.studentDetail(assignmentId) }),
        qc.invalidateQueries({ queryKey: keys.studentList }),
        qc.invalidateQueries({ queryKey: keys.roster(assignmentId) }),
        qc.invalidateQueries({ queryKey: ['faculty', 'overview'] }),
      ]),
  })
}

/** Student: ask for permission to submit late. The server decides whether the student is eligible. */
export function useCreateLateRequest(assignmentId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (reason: string) =>
      (
        await api.post<LateRequest>(`/student/assignments/${assignmentId}/late-request`, {
          reason,
        })
      ).data,
    onSuccess: () =>
      Promise.all([
        qc.invalidateQueries({ queryKey: keys.studentDetail(assignmentId) }),
        qc.invalidateQueries({ queryKey: keys.studentList }),
        qc.invalidateQueries({ queryKey: ['faculty', 'late-requests'] }),
        qc.invalidateQueries({ queryKey: ['notifications'] }),
      ]),
  })
}

// --- Faculty: late requests ---

export function useLateRequests(
  state: RequestState | 'ALL',
  poll = false,
  filter: ScopeFilter = {},
) {
  return useQuery({
    queryKey: [...keys.lateRequests(state), filter] as const,
    gcTime: Object.keys(filter).length ? 0 : undefined,
    queryFn: async () =>
      (
        await api.get<FacultyLateRequest[]>('/faculty/late-requests', {
          params: { ...(state === 'ALL' ? {} : { status: state }), ...filter },
        })
      ).data,
    refetchInterval: poll ? 60_000 : false,
  })
}

export function useLateRequest(id: string) {
  return useQuery({
    queryKey: keys.lateRequest(id),
    queryFn: async () =>
      (await api.get<FacultyLateRequestDetail>(`/faculty/late-requests/${id}`)).data,
  })
}

export function useDecideLateRequest(id: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (input: LateDecisionInput) =>
      (await api.post<FacultyLateRequest>(`/faculty/late-requests/${id}/decision`, input)).data,
    // A 409 ALREADY_DECIDED also needs a refresh, so the card shows the decision that won.
    onSettled: () =>
      Promise.all([
        qc.invalidateQueries({ queryKey: ['faculty', 'late-requests'] }),
        qc.invalidateQueries({ queryKey: ['notifications'] }),
        qc.invalidateQueries({ queryKey: ['faculty', 'assignments'] }),
        qc.invalidateQueries({ queryKey: ['student', 'assignments'] }),
      ]),
  })
}

export function useRoster(assignmentId: string, enabled: boolean) {
  return useQuery({
    queryKey: keys.roster(assignmentId),
    enabled,
    queryFn: async () =>
      (await api.get<RosterRow[]>(`/faculty/assignments/${assignmentId}/roster`)).data,
  })
}

export function useStudentSubmission(assignmentId: string, studentId: string) {
  return useQuery({
    queryKey: keys.studentSubmission(assignmentId, studentId),
    queryFn: async () =>
      (
        await api.get<StudentSubmissionDetail>(
          `/faculty/assignments/${assignmentId}/students/${studentId}/timeline`,
        )
      ).data,
  })
}

// --- Reviews, health board, notifications (Phase 7) ---

export function useRecordReview(assignmentId: string, studentId: string, submissionId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (input: ReviewInput) =>
      (await api.post<ReviewOut>(`/faculty/submissions/${submissionId}/reviews`, input)).data,
    // Also on errors: a 409 (stale version / unchanged) means the screen should show the current state.
    onSettled: () =>
      Promise.all([
        qc.invalidateQueries({ queryKey: keys.studentSubmission(assignmentId, studentId) }),
        qc.invalidateQueries({ queryKey: keys.roster(assignmentId) }),
        qc.invalidateQueries({ queryKey: ['faculty', 'overview'] }),
        qc.invalidateQueries({ queryKey: ['student'] }),
        qc.invalidateQueries({ queryKey: keys.notifications }),
      ]),
  })
}

export function useOverview(filters: OverviewFilters) {
  return useQuery({
    queryKey: ['faculty', 'overview', 'counts', filters] as const,
    gcTime: 0,
    queryFn: async () => (await api.get<Overview>('/faculty/overview', { params: filters })).data,
    refetchInterval: 60_000,
  })
}

export function useOverviewStudents(filters: OverviewFilters) {
  return useQuery({
    queryKey: ['faculty', 'overview', 'students', filters] as const,
    gcTime: 0,
    queryFn: async () =>
      (await api.get<OverviewStudents>('/faculty/overview/students', { params: filters })).data,
    refetchInterval: 60_000,
  })
}

export function useNotifications(enabled = true) {
  return useQuery({
    queryKey: keys.notifications,
    enabled,
    staleTime: 0, // opening the panel always shows the server's current list
    queryFn: async () => (await api.get<NotificationsResponse>('/notifications')).data,
    refetchInterval: enabled ? 60_000 : false, // the server computes alerts from its own clock (architecture §22)
  })
}

/** The bell badge: a single COUNT on the server, polled while the tab is visible and refreshed on tab focus.
 *  Its key sits under ['notifications'], so every notification action (and the quiz / deadline mutations that
 *  invalidate that key) refreshes it at once; logout clears the whole query cache. */
export function useUnreadCount() {
  return useQuery({
    queryKey: [...keys.notifications, 'unread-count'] as const,
    queryFn: async () =>
      (await api.get<{ unread_count: number }>('/notifications/unread-count')).data.unread_count,
    refetchInterval: 10_000, // pauses while the tab is hidden (react-query default); refreshed on tab focus
    refetchOnWindowFocus: 'always',
    staleTime: 0,
  })
}

export function useMarkAllNotificationsRead() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async () => {
      await api.post('/notifications/read-all')
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.notifications }),
  })
}

export function useMarkNotificationRead() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (id: string) => {
      await api.post(`/notifications/${id}/read`)
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.notifications }),
  })
}

// --- Quizzes ---

function invalidateQuizViews(qc: ReturnType<typeof useQueryClient>, id?: string) {
  void qc.invalidateQueries({ queryKey: keys.facultyList })
  void qc.invalidateQueries({ queryKey: keys.studentList })
  void qc.invalidateQueries({ queryKey: ['notifications'] })
  if (id) {
    void qc.invalidateQueries({ queryKey: keys.facultyDetail(id) })
    void qc.invalidateQueries({ queryKey: ['faculty', 'quiz', id] })
    void qc.invalidateQueries({ queryKey: ['student', 'quiz', id] })
  }
}

export function useQuizFaculty(id: string, enabled = true) {
  return useQuery({
    queryKey: ['faculty', 'quiz', id] as const,
    enabled,
    queryFn: async () => (await api.get<QuizFacultyDetail>(`/faculty/quizzes/${id}`)).data,
  })
}

export function useQuizParticipation(id: string, enabled: boolean) {
  return useQuery({
    queryKey: ['faculty', 'quiz', id, 'participation'] as const,
    enabled,
    queryFn: async () =>
      (await api.get<QuizParticipation>(`/faculty/quizzes/${id}/participation`)).data,
  })
}

export function useCreateQuiz() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (input: QuizCreateInput) =>
      (await api.post<QuizFacultyDetail>('/faculty/quizzes', input)).data,
    onSuccess: (q) => invalidateQuizViews(qc, q.id),
  })
}

export function useUpdateQuiz(id: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (input: QuizDefinitionInput) =>
      (await api.put<QuizFacultyDetail>(`/faculty/quizzes/${id}`, input)).data,
    onSuccess: () => invalidateQuizViews(qc, id),
  })
}

export function useQuizStudent(id: string) {
  return useQuery({
    queryKey: ['student', 'quiz', id] as const,
    gcTime: 0, // always fetch the server's current attempt state, never a remembered one
    queryFn: async () => (await api.get<QuizStudentView>(`/student/quizzes/${id}`)).data,
  })
}

export function useStartQuizAttempt(id: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async () =>
      (await api.post<QuizStudentView>(`/student/quizzes/${id}/attempts`)).data,
    onSuccess: (view) => {
      qc.setQueryData(['student', 'quiz', id], view)
      void qc.invalidateQueries({ queryKey: keys.studentList })
    },
  })
}

export async function saveQuizAnswers(
  attemptId: string,
  answers: { question_id: string; option_ids: string[] }[],
): Promise<QuizAttemptState> {
  return (
    await api.put<QuizAttemptState>(`/student/quiz-attempts/${attemptId}/answers`, { answers })
  ).data
}

export function useSubmitQuiz(assignmentId: string, attemptId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (answers: { question_id: string; option_ids: string[] }[]) =>
      (await api.post<QuizResult>(`/student/quiz-attempts/${attemptId}/submit`, { answers })).data,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['student'] })
      void qc.invalidateQueries({ queryKey: ['notifications'] })
      void qc.invalidateQueries({ queryKey: ['student', 'quiz', assignmentId] })
    },
  })
}

export function useQuizResult(attemptId: string | undefined) {
  return useQuery({
    queryKey: ['student', 'quiz-result', attemptId] as const,
    enabled: !!attemptId,
    gcTime: 0,
    queryFn: async () =>
      (await api.get<QuizResult>(`/student/quiz-attempts/${attemptId}/result`)).data,
  })
}
