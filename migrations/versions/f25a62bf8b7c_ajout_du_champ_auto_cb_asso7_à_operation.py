"""Ajout du champ auto_cb_asso7 à Operation

Revision ID: f25a62bf8b7c
Revises: f72685bc927f
Create Date: 2025-06-21 01:56:41.295249
"""
from alembic import op
import sqlalchemy as sa

# Identifiants de révision
revision = 'f25a62bf8b7c'
down_revision = 'f72685bc927f'
branch_labels = None
depends_on = None

def upgrade():
    # ✅ Ajouter seulement le champ auto_cb_asso7
    with op.batch_alter_table('operation', schema=None) as batch_op:
        batch_op.add_column(sa.Column('auto_cb_asso7', sa.Boolean(), nullable=True))

def downgrade():
    with op.batch_alter_table('operation', schema=None) as batch_op:
        batch_op.drop_column('auto_cb_asso7')
