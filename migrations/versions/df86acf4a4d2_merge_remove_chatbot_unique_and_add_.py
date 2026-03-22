"""merge remove_chatbot_unique and add_ingestion_task

Revision ID: df86acf4a4d2
Revises: b47fa1825eef, e013e45f3a5d
Create Date: 2026-03-23 00:36:22.636123

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'df86acf4a4d2'
down_revision = ('b47fa1825eef', 'e013e45f3a5d')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
