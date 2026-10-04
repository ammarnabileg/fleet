"""The permission catalog. Roles are built from these codes in the settings screen, without code changes.
Each module adds its codes here when it is implemented."""

CATALOG: dict[str, tuple[str, str]] = {
    "users.view": ("عرض المستخدمين", "View users"),
    "users.manage": ("إدارة المستخدمين", "Manage users"),
    "roles.manage": ("إدارة الأدوار والصلاحيات", "Manage roles and permissions"),
    "branches.manage": ("إدارة الشركات والفروع", "Manage companies and branches"),
    "settings.view": ("عرض الإعدادات", "View settings"),
    "settings.manage": ("تعديل الإعدادات", "Change settings"),
    "audit.view": ("عرض سجل التدقيق", "View the audit trail"),
}
