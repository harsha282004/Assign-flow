"""assignment_attachments: reference materials for assignments (Enhancement round 2, Phase B)

Adds one table. No existing table or row is modified.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-11 10:00:00
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0002'
down_revision: str | None = '0001'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('assignment_attachments',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('assignment_id', sa.UUID(), nullable=False),
    sa.Column('original_filename', sa.String(length=200), nullable=False),
    sa.Column('storage_key', sa.String(length=300), nullable=False),
    sa.Column('mime_type', sa.String(length=100), nullable=False),
    sa.Column('size_bytes', sa.BigInteger(), nullable=False),
    sa.Column('uploaded_by', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('size_bytes > 0', name=op.f('ck_assignment_attachments_size_positive')),
    sa.ForeignKeyConstraint(['assignment_id'], ['assignments.id'], name=op.f('fk_assignment_attachments_assignment_id_assignments'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['uploaded_by'], ['users.id'], name=op.f('fk_assignment_attachments_uploaded_by_users'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_assignment_attachments')),
    sa.UniqueConstraint('storage_key', name=op.f('uq_assignment_attachments_storage_key'))
    )
    op.create_index('ix_assignment_attachments_assignment_created', 'assignment_attachments', ['assignment_id', 'created_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_assignment_attachments_assignment_created', table_name='assignment_attachments')
    op.drop_table('assignment_attachments')
