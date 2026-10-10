"""initial_schema: complete approved schema (architecture §14)

Tables, constraints, indexes and PostgreSQL enum types. Generated from the models with
`alembic revision --autogenerate` against an empty database, then reviewed and completed
(explicit enum drops in downgrade).

Revision ID: 0001
Revises:
Create Date: 2026-10-10 09:37:30
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '0001'
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('sections',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('semester', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=10), nullable=False),
    sa.Column('label', sa.String(length=30), nullable=False),
    sa.CheckConstraint('semester BETWEEN 1 AND 8', name=op.f('ck_sections_semester_range')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sections')),
    sa.UniqueConstraint('label', name=op.f('uq_sections_label')),
    sa.UniqueConstraint('semester', 'name', name='uq_sections_semester_name')
    )
    op.create_table('subjects',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('code', sa.String(length=20), nullable=False),
    sa.Column('name', sa.String(length=150), nullable=False),
    sa.Column('semester', sa.Integer(), nullable=False),
    sa.CheckConstraint('semester BETWEEN 1 AND 8', name=op.f('ck_subjects_semester_range')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_subjects')),
    sa.UniqueConstraint('code', name=op.f('uq_subjects_code'))
    )
    op.create_table('users',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('login_id', sa.String(length=32), nullable=False),
    sa.Column('full_name', sa.String(length=150), nullable=False),
    sa.Column('role', sa.Enum('FACULTY', 'STUDENT', name='user_role'), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_users')),
    sa.UniqueConstraint('login_id', name=op.f('uq_users_login_id'))
    )
    op.create_table('assignments',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('title', sa.String(length=150), nullable=False),
    sa.Column('instructions', sa.String(length=5000), nullable=False),
    sa.Column('subject_id', sa.UUID(), nullable=False),
    sa.Column('section_id', sa.UUID(), nullable=False),
    sa.Column('created_by', sa.UUID(), nullable=False),
    sa.Column('status', sa.Enum('DRAFT', 'PUBLISHED', name='assignment_status'), server_default=sa.text("'DRAFT'"), nullable=False),
    sa.Column('original_deadline', sa.DateTime(timezone=True), nullable=False),
    sa.Column('deadline', sa.DateTime(timezone=True), nullable=False),
    sa.Column('allowed_types', postgresql.ARRAY(sa.Text()), nullable=False),
    sa.Column('max_file_mb', sa.Integer(), server_default=sa.text('10'), nullable=False),
    sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('max_file_mb BETWEEN 1 AND 10', name=op.f('ck_assignments_max_file_mb_range')),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_assignments_created_by_users'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['section_id'], ['sections.id'], name=op.f('fk_assignments_section_id_sections'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['subject_id'], ['subjects.id'], name=op.f('fk_assignments_subject_id_subjects'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_assignments'))
    )
    op.create_index(op.f('ix_assignments_created_by'), 'assignments', ['created_by'], unique=False)
    op.create_index('ix_assignments_section_status', 'assignments', ['section_id', 'status'], unique=False)
    op.create_table('notifications',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('type', sa.String(length=50), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('body', sa.String(length=1000), nullable=False),
    sa.Column('ref_type', sa.String(length=50), nullable=True),
    sa.Column('ref_id', sa.UUID(), nullable=True),
    sa.Column('dedup_key', sa.String(length=200), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('read_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_notifications_user_id_users'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_notifications')),
    sa.UniqueConstraint('dedup_key', name=op.f('uq_notifications_dedup_key'))
    )
    op.create_index('ix_notifications_user_read_created', 'notifications', ['user_id', 'read_at', sa.literal_column('created_at DESC')], unique=False)
    op.create_table('student_profiles',
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('section_id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['section_id'], ['sections.id'], name=op.f('fk_student_profiles_section_id_sections'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_student_profiles_user_id_users'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('user_id', name=op.f('pk_student_profiles'))
    )
    op.create_index(op.f('ix_student_profiles_section_id'), 'student_profiles', ['section_id'], unique=False)
    op.create_table('teaching_assignments',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('faculty_id', sa.UUID(), nullable=False),
    sa.Column('subject_id', sa.UUID(), nullable=False),
    sa.Column('section_id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['faculty_id'], ['users.id'], name=op.f('fk_teaching_assignments_faculty_id_users'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['section_id'], ['sections.id'], name=op.f('fk_teaching_assignments_section_id_sections'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['subject_id'], ['subjects.id'], name=op.f('fk_teaching_assignments_subject_id_subjects'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_teaching_assignments')),
    sa.UniqueConstraint('subject_id', 'section_id', name='uq_teaching_assignments_subject_section')
    )
    op.create_index(op.f('ix_teaching_assignments_faculty_id'), 'teaching_assignments', ['faculty_id'], unique=False)
    op.create_table('deadline_changes',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('assignment_id', sa.UUID(), nullable=False),
    sa.Column('old_deadline', sa.DateTime(timezone=True), nullable=False),
    sa.Column('new_deadline', sa.DateTime(timezone=True), nullable=False),
    sa.Column('changed_by', sa.UUID(), nullable=False),
    sa.Column('changed_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('reason', sa.String(length=500), nullable=True),
    sa.ForeignKeyConstraint(['assignment_id'], ['assignments.id'], name=op.f('fk_deadline_changes_assignment_id_assignments'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['changed_by'], ['users.id'], name=op.f('fk_deadline_changes_changed_by_users'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_deadline_changes'))
    )
    op.create_index('ix_deadline_changes_assignment_changed', 'deadline_changes', ['assignment_id', 'changed_at'], unique=False)
    op.create_table('late_requests',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('assignment_id', sa.UUID(), nullable=False),
    sa.Column('student_id', sa.UUID(), nullable=False),
    sa.Column('reason', sa.String(length=1000), nullable=False),
    sa.Column('requested_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('deadline_at_request', sa.DateTime(timezone=True), nullable=False),
    sa.Column('status', sa.Enum('PENDING', 'APPROVED', 'REJECTED', name='late_request_status'), server_default=sa.text("'PENDING'"), nullable=False),
    sa.Column('decided_by', sa.UUID(), nullable=True),
    sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('decision_note', sa.String(length=500), nullable=True),
    sa.Column('window_start', sa.DateTime(timezone=True), nullable=True),
    sa.Column('window_end', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint("(status = 'APPROVED') = (window_start IS NOT NULL AND window_end IS NOT NULL)", name=op.f('ck_late_requests_window_fields_iff_approved')),
    sa.CheckConstraint("(status = 'PENDING') = (decided_by IS NULL AND decided_at IS NULL)", name=op.f('ck_late_requests_decision_fields_iff_decided')),
    sa.CheckConstraint('char_length(reason) BETWEEN 20 AND 1000', name=op.f('ck_late_requests_reason_length')),
    sa.CheckConstraint('window_start IS NULL OR window_end > window_start', name=op.f('ck_late_requests_window_order')),
    sa.ForeignKeyConstraint(['assignment_id'], ['assignments.id'], name=op.f('fk_late_requests_assignment_id_assignments'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['decided_by'], ['users.id'], name=op.f('fk_late_requests_decided_by_users'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['student_id'], ['users.id'], name=op.f('fk_late_requests_student_id_users'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_late_requests')),
    sa.UniqueConstraint('assignment_id', 'student_id', name='uq_late_requests_assignment_student')
    )
    op.create_index('ix_late_requests_assignment_status', 'late_requests', ['assignment_id', 'status'], unique=False)
    op.create_table('submissions',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('assignment_id', sa.UUID(), nullable=False),
    sa.Column('student_id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('latest_version_no', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.CheckConstraint('latest_version_no >= 0', name=op.f('ck_submissions_latest_version_no_nonneg')),
    sa.ForeignKeyConstraint(['assignment_id'], ['assignments.id'], name=op.f('fk_submissions_assignment_id_assignments'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['student_id'], ['users.id'], name=op.f('fk_submissions_student_id_users'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_submissions')),
    sa.UniqueConstraint('assignment_id', 'student_id', name='uq_submissions_assignment_student')
    )
    op.create_table('submission_versions',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('submission_id', sa.UUID(), nullable=False),
    sa.Column('version_no', sa.Integer(), nullable=False),
    sa.Column('storage_key', sa.String(length=300), nullable=False),
    sa.Column('original_filename', sa.String(length=200), nullable=False),
    sa.Column('mime_type', sa.String(length=100), nullable=False),
    sa.Column('size_bytes', sa.BigInteger(), nullable=False),
    sa.Column('sha256', sa.String(length=64), nullable=False),
    sa.Column('uploaded_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('uploaded_by', sa.UUID(), nullable=False),
    sa.Column('deadline_at_upload', sa.DateTime(timezone=True), nullable=False),
    sa.Column('upload_context', sa.Enum('REGULAR', 'LATE_APPROVED', 'REVISION', name='upload_context'), nullable=False),
    sa.Column('late_request_id', sa.UUID(), nullable=True),
    sa.CheckConstraint("(upload_context = 'LATE_APPROVED') = (late_request_id IS NOT NULL)", name=op.f('ck_submission_versions_late_context_iff_request')),
    sa.CheckConstraint('char_length(sha256) = 64', name=op.f('ck_submission_versions_sha256_length')),
    sa.CheckConstraint('size_bytes > 0', name=op.f('ck_submission_versions_size_positive')),
    sa.CheckConstraint('version_no >= 1', name=op.f('ck_submission_versions_version_no_positive')),
    sa.ForeignKeyConstraint(['late_request_id'], ['late_requests.id'], name=op.f('fk_submission_versions_late_request_id_late_requests'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['submission_id'], ['submissions.id'], name=op.f('fk_submission_versions_submission_id_submissions'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['uploaded_by'], ['users.id'], name=op.f('fk_submission_versions_uploaded_by_users'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_submission_versions')),
    sa.UniqueConstraint('storage_key', name=op.f('uq_submission_versions_storage_key')),
    sa.UniqueConstraint('submission_id', 'version_no', name='uq_submission_versions_submission_version')
    )
    op.create_table('reviews',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('submission_id', sa.UUID(), nullable=False),
    sa.Column('version_id', sa.UUID(), nullable=False),
    sa.Column('reviewer_id', sa.UUID(), nullable=False),
    sa.Column('status', sa.Enum('UNDER_REVIEW', 'ACCEPTED', 'REVISION_REQUESTED', name='review_status'), nullable=False),
    sa.Column('feedback', sa.String(length=2000), nullable=True),
    sa.Column('reviewed_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['reviewer_id'], ['users.id'], name=op.f('fk_reviews_reviewer_id_users'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['submission_id'], ['submissions.id'], name=op.f('fk_reviews_submission_id_submissions'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['version_id'], ['submission_versions.id'], name=op.f('fk_reviews_version_id_submission_versions'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_reviews'))
    )
    op.create_index('ix_reviews_submission_reviewed_desc', 'reviews', ['submission_id', sa.literal_column('reviewed_at DESC')], unique=False)


def downgrade() -> None:
    op.drop_index('ix_reviews_submission_reviewed_desc', table_name='reviews')
    op.drop_table('reviews')
    op.drop_table('submission_versions')
    op.drop_table('submissions')
    op.drop_index('ix_late_requests_assignment_status', table_name='late_requests')
    op.drop_table('late_requests')
    op.drop_index('ix_deadline_changes_assignment_changed', table_name='deadline_changes')
    op.drop_table('deadline_changes')
    op.drop_index(op.f('ix_teaching_assignments_faculty_id'), table_name='teaching_assignments')
    op.drop_table('teaching_assignments')
    op.drop_index(op.f('ix_student_profiles_section_id'), table_name='student_profiles')
    op.drop_table('student_profiles')
    op.drop_index('ix_notifications_user_read_created', table_name='notifications')
    op.drop_table('notifications')
    op.drop_index('ix_assignments_section_status', table_name='assignments')
    op.drop_index(op.f('ix_assignments_created_by'), table_name='assignments')
    op.drop_table('assignments')
    op.drop_table('users')
    op.drop_table('subjects')
    op.drop_table('sections')

    # create_table() created these enum types implicitly; drop them explicitly on downgrade.
    for enum_name in (
        'review_status',
        'upload_context',
        'late_request_status',
        'assignment_status',
        'user_role',
    ):
        op.execute(f'DROP TYPE IF EXISTS {enum_name}')
