"""Role templates from BRD section 4. All are editable except the system administrator.

Revision ID: 0003_role_templates
Revises: 0002_i18n
"""

import json

from alembic import op

revision = "0003_role_templates"
down_revision = "0002_i18n"
branch_labels = None
depends_on = None

# Frozen copy: a migration must not depend on today's application code.
TEMPLATES = [
    ("system_admin", "مدير النظام", "System administrator", True, True, []),
    (
        "management",
        "الإدارة",
        "Management",
        False,
        False,
        [
            "dashboard.view",
            "reports.view",
            "reports.export",
            "approvals.view",
            "companies.view",
            "branches.view",
            "employees.view",
            "vehicles.view",
            "custody.view",
            "odometer.view",
            "tracking.live",
            "tracking.history",
            "daily_reports.view",
            "cash.view",
            "treasury.view",
            "maintenance.view",
            "maintenance.approve",
            "invoices.view",
            "invoices.approve",
            "accidents.view",
            "accidents.approve",
            "finance.view",
            "finance.approve",
            "payroll.view",
            "payroll.approve",
            "deductions.view",
            "fines.view",
            "leaves.view",
            "audit.view",
        ],
    ),
    (
        "supervisor",
        "المشرف",
        "Supervisor",
        False,
        False,
        [
            "dashboard.view",
            "employees.view",
            "documents.view",
            "vehicles.view",
            "custody.view",
            "custody.assign",
            "custody.emergency",
            "odometer.view",
            "odometer.review",
            "tracking.live",
            "tracking.history",
            "devices.manage",
            "daily_reports.view",
            "daily_reports.review",
            "maintenance.view",
            "maintenance.create",
            "accidents.view",
            "accidents.create",
            "fines.view",
            "approvals.view",
        ],
    ),
    (
        "accountant",
        "المحاسب",
        "Accountant",
        False,
        False,
        [
            "dashboard.view",
            "employees.view",
            "daily_reports.view",
            "cash.view",
            "cash.collect",
            "cash.adjust",
            "cash.export",
            "treasury.view",
            "treasury.manage",
            "finance.view",
            "finance.create",
            "finance.export",
            "invoices.view",
            "invoices.create",
            "reports.view",
            "reports.export",
            "approvals.view",
        ],
    ),
    (
        "hr",
        "الموارد البشرية",
        "Human resources",
        False,
        False,
        [
            "dashboard.view",
            "companies.view",
            "employees.view",
            "employees.create",
            "employees.update",
            "employees.export",
            "employees.view_salary",
            "documents.view",
            "documents.manage",
            "leaves.view",
            "leaves.approve",
            "payroll.view",
            "payroll.prepare",
            "payroll.export",
            "deductions.view",
            "deductions.manage",
            "reports.view",
            "approvals.view",
        ],
    ),
    (
        "maintenance_manager",
        "مدير الصيانة",
        "Maintenance manager",
        False,
        False,
        [
            "dashboard.view",
            "vehicles.view",
            "maintenance.view",
            "maintenance.create",
            "maintenance.approve",
            "maintenance.export",
            "maintenance_centers.view",
            "maintenance_centers.manage",
            "invoices.view",
            "invoices.approve",
            "accidents.view",
            "accidents.update",
            "reports.view",
            "approvals.view",
        ],
    ),
    (
        "maintenance_center",
        "مركز الصيانة",
        "Maintenance center",
        False,
        False,
        ["portal.vehicles", "portal.quotes", "portal.invoices", "portal.damage"],
    ),
    (
        "support",
        "دعم BrilliantTech",
        "BrilliantTech support",
        False,
        False,
        ["users.view", "roles.view", "companies.view", "branches.view", "settings.view", "audit.view"],
    ),
]


def upgrade() -> None:
    db = op.get_bind().connection.driver_connection
    for code, ar, en, is_system, all_permissions, permissions in TEMPLATES:
        role_id = db.execute(
            "INSERT INTO identity.roles (code, name, is_system, all_permissions) VALUES (%s, %s, %s, %s) RETURNING id",
            (code, json.dumps({"ar": ar, "en": en}, ensure_ascii=False), is_system, all_permissions),
        ).fetchone()[0]
        for permission in permissions:
            db.execute(
                "INSERT INTO identity.role_permissions (role_id, permission) VALUES (%s, %s)", (role_id, permission)
            )


def downgrade() -> None:
    raise NotImplementedError("forward-only migrations")
