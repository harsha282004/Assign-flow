"""quiz_assignments: teacher-built quizzes (Enhancement: quiz assignments)

* assignments: assignment_type ('FILE' default, so every existing row stays a file assignment), description,
  duration_minutes (+ CHECKs);
* new tables quiz_questions, quiz_options (answer key in is_correct), quiz_attempts (one per student and quiz),
  quiz_answers (one row per selected option; composite foreign keys tie attempt, question and option to the same quiz).

No existing row is modified. Downgrade refuses to run while any quiz assignment exists (it would destroy quiz data).

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-11 18:00:00
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0004'
down_revision: str | None = '0003'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID_DEFAULT = sa.text('gen_random_uuid()')


def upgrade() -> None:
    op.add_column('assignments', sa.Column('assignment_type', sa.String(length=10), server_default=sa.text("'FILE'"), nullable=False))
    op.add_column('assignments', sa.Column('description', sa.String(length=2000), nullable=True))
    op.add_column('assignments', sa.Column('duration_minutes', sa.Integer(), nullable=True))
    op.create_check_constraint(op.f('ck_assignments_type_valid'), 'assignments', "assignment_type IN ('FILE', 'QUIZ')")
    op.create_check_constraint(op.f('ck_assignments_duration_range'), 'assignments', 'duration_minutes IS NULL OR duration_minutes BETWEEN 1 AND 300')

    op.create_table('quiz_questions',
    sa.Column('id', sa.UUID(), server_default=UUID_DEFAULT, nullable=False),
    sa.Column('assignment_id', sa.UUID(), nullable=False),
    sa.Column('question_type', sa.String(length=20), nullable=False),
    sa.Column('text', sa.String(length=1000), nullable=False),
    sa.Column('marks', sa.Integer(), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.CheckConstraint("question_type IN ('SINGLE_CHOICE', 'MULTIPLE_SELECT', 'TRUE_FALSE')", name=op.f('ck_quiz_questions_type_valid')),
    sa.CheckConstraint('marks BETWEEN 1 AND 100', name=op.f('ck_quiz_questions_marks_range')),
    sa.ForeignKeyConstraint(['assignment_id'], ['assignments.id'], name=op.f('fk_quiz_questions_assignment_id_assignments'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_quiz_questions')),
    sa.UniqueConstraint('id', 'assignment_id', name='uq_quiz_questions_id_assignment')
    )
    op.create_index('ix_quiz_questions_assignment_position', 'quiz_questions', ['assignment_id', 'position'], unique=False)

    op.create_table('quiz_options',
    sa.Column('id', sa.UUID(), server_default=UUID_DEFAULT, nullable=False),
    sa.Column('question_id', sa.UUID(), nullable=False),
    sa.Column('text', sa.String(length=300), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.Column('is_correct', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['question_id'], ['quiz_questions.id'], name=op.f('fk_quiz_options_question_id_quiz_questions'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_quiz_options')),
    sa.UniqueConstraint('id', 'question_id', name='uq_quiz_options_id_question')
    )
    op.create_index('ix_quiz_options_question_position', 'quiz_options', ['question_id', 'position'], unique=False)

    op.create_table('quiz_attempts',
    sa.Column('id', sa.UUID(), server_default=UUID_DEFAULT, nullable=False),
    sa.Column('assignment_id', sa.UUID(), nullable=False),
    sa.Column('student_id', sa.UUID(), nullable=False),
    sa.Column('status', sa.String(length=12), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('submitted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('score', sa.Integer(), nullable=True),
    sa.Column('max_score', sa.Integer(), nullable=True),
    sa.Column('timed_out', sa.Boolean(), server_default='false', nullable=False),
    sa.CheckConstraint("status IN ('IN_PROGRESS', 'SUBMITTED')", name=op.f('ck_quiz_attempts_status_valid')),
    sa.CheckConstraint("(status = 'SUBMITTED') = (submitted_at IS NOT NULL AND score IS NOT NULL AND max_score IS NOT NULL)", name=op.f('ck_quiz_attempts_submitted_complete')),
    sa.CheckConstraint('score IS NULL OR (score >= 0 AND score <= max_score)', name=op.f('ck_quiz_attempts_score_in_range')),
    sa.ForeignKeyConstraint(['assignment_id'], ['assignments.id'], name=op.f('fk_quiz_attempts_assignment_id_assignments'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['student_id'], ['users.id'], name=op.f('fk_quiz_attempts_student_id_users'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_quiz_attempts')),
    sa.UniqueConstraint('assignment_id', 'student_id', name='uq_quiz_attempts_assignment_student'),
    sa.UniqueConstraint('id', 'assignment_id', name='uq_quiz_attempts_id_assignment')
    )
    op.create_index(op.f('ix_quiz_attempts_student_id'), 'quiz_attempts', ['student_id'], unique=False)

    op.create_table('quiz_answers',
    sa.Column('id', sa.UUID(), server_default=UUID_DEFAULT, nullable=False),
    sa.Column('attempt_id', sa.UUID(), nullable=False),
    sa.Column('assignment_id', sa.UUID(), nullable=False),
    sa.Column('question_id', sa.UUID(), nullable=False),
    sa.Column('option_id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['attempt_id', 'assignment_id'], ['quiz_attempts.id', 'quiz_attempts.assignment_id'], name='fk_quiz_answers_attempt_id_quiz_attempts', ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['question_id', 'assignment_id'], ['quiz_questions.id', 'quiz_questions.assignment_id'], name='fk_quiz_answers_question_id_quiz_questions', ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['option_id', 'question_id'], ['quiz_options.id', 'quiz_options.question_id'], name='fk_quiz_answers_option_id_quiz_options', ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_quiz_answers')),
    sa.UniqueConstraint('attempt_id', 'question_id', 'option_id', name='uq_quiz_answers_attempt_question_option')
    )
    op.create_index(op.f('ix_quiz_answers_attempt_id'), 'quiz_answers', ['attempt_id'], unique=False)


def downgrade() -> None:
    quizzes = op.get_bind().execute(sa.text("SELECT count(*) FROM assignments WHERE assignment_type = 'QUIZ'")).scalar()
    if quizzes:
        raise RuntimeError(
            f"Cannot downgrade: {quizzes} quiz assignment(s) exist. Their questions and attempts would be destroyed."
        )
    op.drop_index(op.f('ix_quiz_answers_attempt_id'), table_name='quiz_answers')
    op.drop_table('quiz_answers')
    op.drop_index(op.f('ix_quiz_attempts_student_id'), table_name='quiz_attempts')
    op.drop_table('quiz_attempts')
    op.drop_index('ix_quiz_options_question_position', table_name='quiz_options')
    op.drop_table('quiz_options')
    op.drop_index('ix_quiz_questions_assignment_position', table_name='quiz_questions')
    op.drop_table('quiz_questions')
    op.drop_constraint(op.f('ck_assignments_duration_range'), 'assignments', type_='check')
    op.drop_constraint(op.f('ck_assignments_type_valid'), 'assignments', type_='check')
    op.drop_column('assignments', 'duration_minutes')
    op.drop_column('assignments', 'description')
    op.drop_column('assignments', 'assignment_type')
