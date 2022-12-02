"""Adds organization tag column

Revision ID: 68aed55dbe88
Revises: 4b3cdab0f846
Create Date: 2022-08-15 23:29:01.524272

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '68aed55dbe88'
down_revision = '4b3cdab0f846'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('account', sa.Column('organization_tag', sa.String(), nullable=True))


def downgrade():
    op.drop_column("account", "organization_tag")
