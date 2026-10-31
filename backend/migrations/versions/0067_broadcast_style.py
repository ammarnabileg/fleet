"""Broadcasts get a look: the message style (info, announcement, reminder, warning, urgent, success: each an icon and
an accent the app knows), the card layout (standard, highlight, compact), an optional image (a stored JPEG or PNG) and
an optional action button (a target from the app's fixed list, with an optional label per language). An app that does
not know a style or a layout draws its standard card with the default icon.

Revision ID: 0067_broadcast_style
Revises: 0066_broadcasts
"""

from alembic import op

revision = "0067_broadcast_style"
down_revision = "0066_broadcasts"
branch_labels = None
depends_on = None

SQL = r"""
ALTER TABLE notifications.broadcasts
    ADD COLUMN style  text NOT NULL DEFAULT 'info'
        CONSTRAINT broadcasts_style_check
        CHECK (style IN ('info', 'announcement', 'reminder', 'warning', 'urgent', 'success')),
    ADD COLUMN layout text NOT NULL DEFAULT 'standard'
        CONSTRAINT broadcasts_layout_check CHECK (layout IN ('standard', 'highlight', 'compact')),
    ADD COLUMN image  text CONSTRAINT broadcasts_image_check CHECK (image ~ '^[0-9a-f]{64}$'),
    ADD COLUMN action jsonb;

SELECT public.fleet_apply_grants();
"""


def upgrade() -> None:
    op.get_bind().connection.driver_connection.execute(SQL)


def downgrade() -> None:
    raise NotImplementedError("forward-only migrations")
