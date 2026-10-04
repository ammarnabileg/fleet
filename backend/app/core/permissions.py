"""The complete permission catalog, for every module of the system (BRD 5.1: module + action).

It is defined up front, including modules not built yet, so roles can be designed correctly from day one.
A module may only use codes listed here: `require_permission` refuses unknown codes at import time.
Labels are translations: namespace "permissions" (key = code) and "modules" (key = module).
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Permission:
    code: str
    module: str
    action: str
    sensitive: bool = False  # money, access control or irreversible: shown with a warning in the roles screen


def _module(module: str, *actions: str, sensitive: tuple[str, ...] = ()) -> list[Permission]:
    return [Permission(f"{module}.{a}", module, a, a in sensitive) for a in actions]


MODULES: list[tuple[str, list[Permission]]] = [
    ("dashboard", _module("dashboard", "view")),
    ("users", _module("users", "view", "create", "update", sensitive=("create", "update"))),
    ("roles", _module("roles", "view", "manage", sensitive=("manage",))),
    ("companies", _module("companies", "view", "create", "update")),
    ("branches", _module("branches", "view", "manage")),
    ("settings", _module("settings", "view", "update", sensitive=("update",))),
    ("i18n", _module("i18n", "manage")),
    ("audit", _module("audit", "view", "export")),
    (
        "employees",
        _module(
            "employees",
            "view",
            "create",
            "update",
            "delete",
            "export",
            "view_salary",
            "onboarding",  # review drivers' self-registration (applies personal data, documents and custody)
            sensitive=("delete", "view_salary", "onboarding"),
        ),
    ),
    ("documents", _module("documents", "view", "manage")),
    ("vehicles", _module("vehicles", "view", "create", "update", "delete", "export", sensitive=("delete",))),
    ("custody", _module("custody", "view", "assign", "emergency")),
    ("odometer", _module("odometer", "view", "review")),
    ("tracking", _module("tracking", "live", "history", "export")),
    ("devices", _module("devices", "manage")),
    ("daily_reports", _module("daily_reports", "view", "review", "export")),
    (
        "cash",
        _module(
            "cash",
            "view",
            "collect",
            "adjust",
            "reverse",
            "writeoff",
            "export",
            sensitive=("adjust", "reverse", "writeoff"),
        ),
    ),
    ("treasury", _module("treasury", "view", "manage", sensitive=("manage",))),
    ("maintenance", _module("maintenance", "view", "create", "approve", "export")),
    ("maintenance_centers", _module("maintenance_centers", "view", "manage")),
    ("invoices", _module("invoices", "view", "create", "approve", sensitive=("approve",))),
    ("accidents", _module("accidents", "view", "create", "update", "approve", "export", sensitive=("approve",))),
    ("fines", _module("fines", "view", "manage")),
    ("finance", _module("finance", "view", "create", "approve", "export", sensitive=("approve",))),
    ("payroll", _module("payroll", "view", "prepare", "approve", "unlock", "export", sensitive=("approve", "unlock"))),
    ("deductions", _module("deductions", "view", "manage", sensitive=("manage",))),
    ("leaves", _module("leaves", "view", "approve")),
    ("approvals", _module("approvals", "view", "workflows")),
    ("notifications", _module("notifications", "manage")),
    ("reports", _module("reports", "view", "export")),
    ("integrations", _module("integrations", "manage", sensitive=("manage",))),
    ("portal", _module("portal", "vehicles", "quotes", "invoices", "damage")),  # maintenance-center users
]

CATALOG: dict[str, Permission] = {p.code: p for _, perms in MODULES for p in perms}


def exists(code: str) -> bool:
    return code in CATALOG
