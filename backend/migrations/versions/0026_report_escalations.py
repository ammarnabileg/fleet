"""A daily report left unreviewed past the review limit is escalated to the manager (BRD BR-05): a permission of its
own, given to the management role template so the alert reaches management and not the supervisors who already got
theirs.

Revision ID: 0026_report_escalations
Revises: 0025_push_tokens
"""

from alembic import op

revision = "0026_report_escalations"
down_revision = "0025_push_tokens"
branch_labels = None
depends_on = None

SQL = r"""
INSERT INTO identity.role_permissions (role_id, permission)
SELECT id, 'daily_reports.escalations' FROM identity.roles WHERE code = 'management' AND NOT all_permissions
ON CONFLICT DO NOTHING;
"""


def upgrade() -> None:
    op.execute(SQL)


def downgrade() -> None:
    raise NotImplementedError("forward-only migrations")
