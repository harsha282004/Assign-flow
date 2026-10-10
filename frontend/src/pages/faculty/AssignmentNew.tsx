import { useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api, errorMessage } from '../../api/client'
import { uploadAttachment, useCreateAssignment, useCreateQuiz } from '../../api/queries'
import QuizBuilder from '../../components/quiz/QuizBuilder'
import { emptyDraft } from '../../components/quiz/quizModel'
import '../../quiz.css'
import AssignmentForm from '../../components/AssignmentForm'
import { EmptyState } from '../../components/ui'
import { useAuth } from '../../auth/useAuth'

export default function AssignmentNew() {
  const { state } = useAuth()
  const navigate = useNavigate()
  const create = useCreateAssignment()
  const createQuiz = useCreateQuiz()
  const [type, setType] = useState<'FILE' | 'QUIZ'>('FILE')
  const qc = useQueryClient()
  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState<string | null>(null)
  if (state.status !== 'authenticated') return null
  const teaching = state.me.teaching ?? []

  return (
    <>
      <p className="small">
        <Link to="/faculty/assignments">← All assignments</Link>
      </p>
      <h1>New assignment</h1>
      {teaching.length === 0 ? (
        <EmptyState title="You have no classes">
          Assignments can only be created for subjects and sections you teach.
        </EmptyState>
      ) : (
        <section className="card-item">
          <fieldset className="qz-type-switch" role="radiogroup" aria-label="Assignment type">
            <legend className="sr-only">Assignment type</legend>
            {(
              [
                [
                  'FILE',
                  'File / Instructions Assignment',
                  'Instructions, optional reference documents, and students upload a file.',
                ],
                [
                  'QUIZ',
                  'Quiz Assignment',
                  'Build questions and answers; students answer in AssignFlow and are graded automatically.',
                ],
              ] as const
            ).map(([value, label, hint]) => (
              <button
                key={value}
                type="button"
                role="radio"
                aria-checked={type === value}
                className="qz-type-card"
                onClick={() => setType(value)}
              >
                <strong>{label}</strong>
                <span>{hint}</span>
              </button>
            ))}
          </fieldset>
          {/* Both forms stay mounted (the inactive one is only hidden), so switching never loses what was typed. */}
          <div hidden={type !== 'FILE'}>
            <AssignmentForm
              mode="create"
              teaching={teaching}
              busy={create.isPending || uploading}
              error={uploadError ?? (create.isError ? errorMessage(create.error) : null)}
              onSubmit={(values, publish, files) => {
                setUploadError(null)
                // With reference documents the assignment is first saved as a DRAFT (documents can only be added to
                // drafts), the files are uploaded, and only then is it published if the teacher asked for that.
                create.mutate(
                  {
                    subject_id: values.subject_id ?? '',
                    section_id: values.section_id ?? '',
                    title: values.title,
                    instructions: values.instructions,
                    deadline: values.deadline,
                    allowed_types: values.allowed_types,
                    max_file_mb: values.max_file_mb,
                    publish: publish && files.length === 0,
                  },
                  {
                    onSuccess: async (a) => {
                      let notice = publish ? 'Assignment published.' : 'Draft saved.'
                      if (files.length > 0) {
                        setUploading(true)
                        const failed: string[] = []
                        for (const f of files) {
                          try {
                            await uploadAttachment(a.id, f)
                          } catch (e) {
                            failed.push(`${f.name} (${errorMessage(e)})`)
                          }
                        }
                        if (failed.length > 0) {
                          notice = `Draft saved, but these documents were not added: ${failed.join('; ')}. Add them from the draft, then publish.`
                        } else if (publish) {
                          try {
                            await api.post(`/faculty/assignments/${a.id}/publish`)
                          } catch (e) {
                            notice = `Draft saved with its documents, but publishing failed: ${errorMessage(e)}`
                          }
                        } else {
                          notice = 'Draft saved with its reference documents.'
                        }
                        setUploading(false)
                      }
                      // The uploads and the publish call bypassed the mutation cache: refresh before showing the page.
                      await qc.invalidateQueries({ queryKey: ['faculty'] })
                      await qc.invalidateQueries({ queryKey: ['student'] })
                      navigate(`/faculty/assignments/${a.id}`, { state: { notice } })
                    },
                  },
                )
              }}
            />
          </div>
          <div hidden={type !== 'QUIZ'}>
            <QuizBuilder
              mode="create"
              teaching={teaching}
              initial={emptyDraft()}
              busy={createQuiz.isPending}
              error={createQuiz.isError ? errorMessage(createQuiz.error) : null}
              onSubmit={(def, publish, slot) => {
                const [subject_id, section_id] = slot.split('|')
                createQuiz.mutate(
                  { ...def, subject_id, section_id, publish },
                  {
                    onSuccess: (q) =>
                      navigate(`/faculty/assignments/${q.id}`, {
                        state: { notice: publish ? 'Quiz published.' : 'Quiz draft saved.' },
                      }),
                  },
                )
              }}
            />
          </div>
        </section>
      )}
    </>
  )
}
