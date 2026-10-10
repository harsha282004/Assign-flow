"""assignment_archive: reversible ARCHIVED state for published assignments (Enhancement round 3)

* adds the value ARCHIVED to the PostgreSQL enum assignment_status;
* adds assignments.archived_at / archived_by and a CHECK tying them to the status;
* adds the insert-only table assignment_state_changes (archive / restore audit trail, shown in the timeline).

No existing row is modified. Downgrade refuses to run while an archived assignment exists (it would have to invent a
status); otherwise it removes the new objects and rebuilds the enum without ARCHIVED.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-11 14:00:00
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0003'
down_revision: str | None = '0002'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # A new enum value cannot be used in the transaction that adds it: commit it first.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE assignment_status ADD VALUE IF NOT EXISTS 'ARCHIVED'")
    op.add_column('assignments', sa.Column('archived_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('assignments', sa.Column('archived_by', sa.UUID(), nullable=True))
    op.create_foreign_key(op.f('fk_assignments_archived_by_users'), 'assignments', 'users', ['archived_by'], ['id'], ondelete='RESTRICT')
    op.create_check_constraint(op.f('ck_assignments_archived_at_iff_archived'), 'assignments', "(status = 'ARCHIVED') = (archived_at IS NOT NULL)")
    op.create_table('assignment_state_changes',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('assignment_id', sa.UUID(), nullable=False),
    sa.Column('from_status', sa.String(length=20), nullable=False),
    sa.Column('to_status', sa.String(length=20), nullable=False),
    sa.Column('changed_by', sa.UUID(), nullable=False),
    sa.Column('changed_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('reason', sa.String(length=500), nullable=True),
    sa.ForeignKeyConstraint(['assignment_id'], ['assignments.id'], name=op.f('fk_assignment_state_changes_assignment_id_assignments'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['changed_by'], ['users.id'], name=op.f('fk_assignment_state_changes_changed_by_users'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_assignment_state_changes'))
    )
    op.create_index('ix_assignment_state_changes_assignment_changed', 'assignment_state_changes', ['assignment_id', 'changed_at'], unique=False)


def downgrade() -> None:
    archived = op.get_bind().execute(sa.text("SELECT count(*) FROM assignments WHERE status = 'ARCHIVED'")).scalar()
    if archived:
        raise RuntimeError(
            f"Cannot downgrade: {archived} archived assignment(s) exist. Restore them first (their history is preserved)."
        )
    op.drop_index('ix_assignment_state_changes_assignment_changed', table_name='assignment_state_changes')
    op.drop_table('assignment_state_changes')
    op.drop_constraint(op.f('ck_assignments_archived_at_iff_archived'), 'assignments', type_='check')
    op.drop_constraint(op.f('fk_assignments_archived_by_users'), 'assignments', type_='foreignkey')
    op.drop_column('assignments', 'archived_by')
    op.drop_column('assignments', 'archived_at')
    op.execute("ALTER TYPE assignment_status RENAME TO assignment_status_old")
    op.execute("CREATE TYPE assignment_status AS ENUM ('DRAFT', 'PUBLISHED')")
    op.execute("ALTER TABLE assignments ALTER COLUMN status DROP DEFAULT")
    op.execute("ALTER TABLE assignments ALTER COLUMN status TYPE assignment_status USING status::text::assignment_status")
    op.execute("ALTER TABLE assignments ALTER COLUMN status SET DEFAULT 'DRAFT'")
    op.execute("DROP TYPE assignment_status_old")
