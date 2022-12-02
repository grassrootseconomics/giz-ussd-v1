"""Create tx_meta table

Revision ID: 4a0e501fb17f
Revises: a571d0aee6f8
Create Date: 2022-07-13 12:57:14.650396

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '4a0e501fb17f'
down_revision = 'a571d0aee6f8'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('tx_meta',
                    sa.Column('id', sa.Integer(), nullable=False),
                    sa.Column('created', sa.DateTime(), nullable=True),
                    sa.Column('updated', sa.DateTime(), nullable=True),
                    sa.Column('tx_reason', sa.String(), nullable=True),
                    sa.Column('tx_from', sa.String(), nullable=True),
                    sa.Column('tx_to', sa.String(), nullable=True),
                    sa.Column('tx_amount', sa.Integer(), nullable=True),
                    sa.PrimaryKeyConstraint('id')
                    )


def downgrade():
    op.drop_table('tx_meta')
