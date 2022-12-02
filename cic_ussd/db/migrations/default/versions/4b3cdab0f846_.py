"""Create survey responses table

Revision ID: 4b3cdab0f846
Revises: 4a0e501fb17f
Create Date: 2022-08-10 12:05:52.326535

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '4b3cdab0f846'
down_revision = '4a0e501fb17f'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('survey_response',
                    sa.Column('id', sa.Integer(), nullable=False),
                    sa.Column('phone_number', sa.String(), nullable=True),
                    sa.Column('village', sa.String(), nullable=True),
                    sa.Column('gender', sa.String(), nullable=True),
                    sa.Column('economic_activity', sa.String(), nullable=True),
                    sa.Column('monthly_expenditure', sa.String(), nullable=True),
                    sa.Column('expenditure_band', sa.String(), nullable=True),
                    sa.Column('created', sa.DateTime(), nullable=True),
                    sa.Column('updated', sa.DateTime(), nullable=True),
                    sa.PrimaryKeyConstraint('id')
                    )
    op.create_index(op.f('ix_survey_response_phone_number'), 'survey_response', ['phone_number'], unique=True)


def downgrade():
    op.drop_index(op.f('ix_survey_response_phone_number'), table_name='account')
    op.drop_table('survey_response')
