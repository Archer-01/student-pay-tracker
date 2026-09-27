"""users and sessions

Adds ``user`` (accounts that can sign in) and ``auth_session`` (one signed-in browser each).

Purely additive: no existing table is touched and nothing is backfilled. The app has no users
after this migration — provision the first one with ``ardoise users add``, which talks to the
database directly and so is the break-glass path if nobody can sign in.

``auth_session.token`` is the primary key rather than a surrogate integer: the lookup is by
token, and a sequential id makes a poor credential.

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-12 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0008'
down_revision: Union[str, Sequence[str], None] = '0007'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'user',
        sa.Column('id', sa.Integer(), nullable=False),
        # Stored lowercased so the UNIQUE index is genuinely case-insensitive in practice.
        sa.Column('username', sa.String(), nullable=False),
        sa.Column('display_name', sa.String(), nullable=False),
        # argon2id in PHC string format; the cost parameters travel inside the hash.
        sa.Column('password_hash', sa.String(), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default='1', nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.CheckConstraint('length(trim(username)) > 0', name='ck_user_username_nonempty'),
        sa.CheckConstraint('length(trim(display_name)) > 0', name='ck_user_display_name_nonempty'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('username', name='uq_user_username'),
    )
    op.create_table(
        'auth_session',
        sa.Column('token', sa.String(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        # CASCADE: deleting a user signs out every browser they were signed in on.
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('token'),
    )
    op.create_index('ix_auth_session_user_id', 'auth_session', ['user_id'])


def downgrade() -> None:
    """Downgrade schema. Every account and signed-in session is lost; the app reverts to open."""
    op.drop_index('ix_auth_session_user_id', table_name='auth_session')
    op.drop_table('auth_session')
    op.drop_table('user')
