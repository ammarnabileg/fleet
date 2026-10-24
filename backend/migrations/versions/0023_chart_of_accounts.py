"""A structured chart of accounts in place of the placeholder one: four-digit codes whose first digit is the class
(1 assets, 2 liabilities, 3 equity, 4 revenue, 5 operating costs, 6 general and administrative) and second the group,
with the accounts a delivery fleet in Kuwait needs (cash held by drivers, platforms' cash on delivery, end-of-service
indemnity, government and residency fees, the owner's current account), and expense types to match.

Drivers' salaries are an operating cost and the office's an administrative one, so payroll runs are entered on two
accounts: the new role `driver_salaries_expense` takes the drivers' part.

The new chart replaces the placeholder only where nothing was entered yet and the accountant has not added accounts of
their own; otherwise the chart in use is kept, and the new role starts on the account the salaries already use.

Revision ID: 0023_chart_of_accounts
Revises: 0022_approvals
"""

import json

from alembic import op

revision = "0023_chart_of_accounts"
down_revision = "0022_approvals"
branch_labels = None
depends_on = None

PLACEHOLDER = (
    "1101", "1102", "1103", "1104", "2101", "2102", "2103", "3101", "4101", "4102", "4103", "4104",
    "5101", "5102", "5103", "5104", "5105", "5106", "5107",
)  # fmt: skip

# Frozen copy: a migration must not depend on today's application code.
ACCOUNTS = [
    # 1 assets
    ("1110", "الصندوق (الخزينة)", "Cash on hand (treasury)", "asset"),
    ("1120", "البنك", "Bank", "asset"),
    ("1130", "كاش لدى السائقين", "Cash held by drivers", "asset"),
    ("1140", "مستحقات من المنصات", "Receivables from delivery platforms", "asset"),
    ("1150", "سلف وذمم الموظفين", "Employee advances and receivables", "asset"),
    ("1160", "مصروفات مدفوعة مقدماً", "Prepaid expenses", "asset"),
    ("1210", "السيارات", "Vehicles", "asset"),
    ("1219", "مجمع إهلاك السيارات", "Accumulated depreciation, vehicles", "asset"),
    ("1220", "الأثاث والأجهزة", "Furniture and equipment", "asset"),
    ("1229", "مجمع إهلاك الأثاث والأجهزة", "Accumulated depreciation, furniture and equipment", "asset"),
    # 2 liabilities
    ("2110", "الموردون ومراكز الصيانة", "Suppliers and maintenance centers", "liability"),
    ("2120", "رواتب مستحقة", "Salaries payable", "liability"),
    ("2130", "كاش الدفع عند الاستلام المستحق للمنصات", "Cash on delivery due to platforms", "liability"),
    ("2140", "مصروفات مستحقة", "Accrued expenses", "liability"),
    ("2210", "مخصص مكافأة نهاية الخدمة", "End-of-service indemnity provision", "liability"),
    # 3 equity
    ("3110", "رأس المال", "Capital", "equity"),
    ("3120", "جاري المالك", "Owner's current account", "equity"),
    ("3210", "أرباح مرحّلة", "Retained earnings", "equity"),
    ("3900", "أرصدة افتتاحية", "Opening balances", "equity"),
    # 4 revenue
    ("4110", "إيرادات التوصيل من المنصات", "Delivery revenue from platforms", "income"),
    ("4210", "استرداد تلفيات الحوادث", "Accident damage recovered", "income"),
    ("4220", "استرداد المخالفات المرورية", "Traffic fines recovered", "income"),
    ("4230", "استرداد شرائح الاتصال", "SIM cards recovered", "income"),
    ("4290", "استردادات أخرى من الموظفين", "Other recoveries from employees", "income"),
    ("4310", "فروقات الكاش", "Cash differences", "income"),
    ("4900", "إيرادات أخرى", "Other income", "income"),
    # 5 operating costs
    ("5110", "رواتب السائقين", "Drivers' salaries", "expense"),
    ("5120", "الوقود", "Fuel", "expense"),
    ("5130", "الصيانة والإصلاح", "Maintenance and repairs", "expense"),
    ("5140", "الإطارات وقطع الغيار", "Tyres and spare parts", "expense"),
    ("5150", "تأمين السيارات", "Vehicle insurance", "expense"),
    ("5160", "ترخيص وتسجيل السيارات", "Vehicle registration and licensing", "expense"),
    ("5170", "المخالفات المرورية", "Traffic fines", "expense"),
    ("5180", "إهلاك السيارات", "Vehicle depreciation", "expense"),
    ("5190", "كاش سائقين مشطوب", "Driver cash written off", "expense"),
    # 6 general and administrative
    ("6110", "رواتب الموظفين الإداريين", "Office staff salaries", "expense"),
    ("6120", "مكافأة نهاية الخدمة", "End-of-service indemnity", "expense"),
    ("6130", "الإيجارات والسكن", "Rent and housing", "expense"),
    ("6140", "الاتصالات والإنترنت", "Telecom and internet", "expense"),
    ("6150", "الرسوم الحكومية والإقامات", "Government fees and residencies", "expense"),
    ("6160", "المصروفات المكتبية", "Office expenses", "expense"),
    ("6170", "الرسوم البنكية", "Bank charges", "expense"),
    ("6180", "إهلاك الأثاث والأجهزة", "Depreciation, furniture and equipment", "expense"),
    ("6190", "مصروفات أخرى", "Other expenses", "expense"),
]
ROLES = {
    "treasury": "1110",
    "deduction_advance": "1110",  # an advance is paid from the treasury
    "bank": "1120",
    "driver_cash": "1130",
    "employee_receivable": "1150",
    "payroll_recovery": "1150",
    "suppliers_payable": "2110",
    "salaries_payable": "2120",
    "cod_clearing": "2130",
    "opening_equity": "3900",
    "deduction_accident": "4210",
    "deduction_fine": "4220",
    "deduction_sim": "4230",
    "deduction_other": "4290",
    "cash_adjustments": "4310",
    "driver_salaries_expense": "5110",
    "maintenance_expense": "5130",
    "traffic_fines_expense": "5170",
    "cash_writeoff": "5190",
    "salaries_expense": "6110",
}
EXPENSE_TYPES = [
    ("fuel", "وقود", "Fuel", "5120", 10),
    ("repairs", "صيانة خارج المراكز", "Repairs outside the centers", "5130", 20),
    ("tyres", "إطارات وقطع غيار", "Tyres and spare parts", "5140", 30),
    ("vehicle_insurance", "تأمين سيارة", "Vehicle insurance", "5150", 40),
    ("registration", "ترخيص وتسجيل سيارة", "Vehicle registration", "5160", 50),
    ("rent", "إيجار وسكن", "Rent and housing", "6130", 60),
    ("telecom", "اتصالات وإنترنت", "Telecom and internet", "6140", 70),
    ("gov_fees", "رسوم حكومية وإقامات", "Government fees and residencies", "6150", 80),
    ("office", "مصروفات مكتبية", "Office", "6160", 85),
    ("bank_fees", "رسوم بنكية", "Bank charges", "6170", 88),
    ("other", "أخرى", "Other", "6190", 90),
]


def _q(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


def _name(ar: str, en: str) -> str:
    return _q(json.dumps({"ar": ar, "en": en}, ensure_ascii=False)) + "::jsonb"


def upgrade() -> None:
    accounts = ",\n      ".join(f"({_q(c)}, {_name(ar, en)}, {_q(t)})" for c, ar, en, t in ACCOUNTS)
    roles = ",\n      ".join(f"({_q(r)}, {_q(c)})" for r, c in ROLES.items())
    types = ",\n      ".join(f"({_q(c)}, {_name(ar, en)}, {_q(a)}, {o})" for c, ar, en, a, o in EXPENSE_TYPES)
    placeholder = ", ".join(_q(c) for c in PLACEHOLDER)
    # every value comes from the constants above, quoted by _q: nothing outside this file reaches the SQL
    sql = f"""
-- the drivers' part of payroll, on the salaries' account wherever the chart in use is kept
INSERT INTO finance.account_roles (role, account_id)
SELECT 'driver_salaries_expense', account_id FROM finance.account_roles WHERE role = 'salaries_expense'
ON CONFLICT (role) DO NOTHING;

DO $chart$
BEGIN
  IF EXISTS (SELECT 1 FROM finance.entries)
     OR EXISTS (SELECT 1 FROM finance.accounts WHERE code NOT IN ({placeholder})) THEN
    RAISE NOTICE 'finance: entries or accounts of the accountant exist, the chart in use is kept';
    RETURN;
  END IF;

  INSERT INTO finance.accounts (code, name, type) VALUES
      {accounts};

  INSERT INTO finance.account_roles (role, account_id)
  SELECT m.role, a.id FROM (VALUES
      {roles}
  ) AS m (role, code) JOIN finance.accounts a ON a.code = m.code
  ON CONFLICT (role) DO UPDATE SET account_id = EXCLUDED.account_id;

  INSERT INTO finance.expense_types (code, name, account_id, sort_order)
  SELECT m.code, m.name, a.id, m.sort_order FROM (VALUES
      {types}
  ) AS m (code, name, account, sort_order) JOIN finance.accounts a ON a.code = m.account
  ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name, account_id = EXCLUDED.account_id,
                                   sort_order = EXCLUDED.sort_order;

  DELETE FROM finance.accounts a
   WHERE a.code IN ({placeholder})
     AND NOT EXISTS (SELECT 1 FROM finance.account_roles r WHERE r.account_id = a.id)
     AND NOT EXISTS (SELECT 1 FROM finance.expense_types t WHERE t.account_id = a.id);
END
$chart$;

SELECT public.fleet_apply_grants();
"""  # noqa: S608
    op.execute(sql)


def downgrade() -> None:
    raise NotImplementedError("forward-only migrations")
