"""Keeta's per-order scheme comes built in beside its fixed salaries: 0.350 per order, target 420 with each order short
deducted 0.350, 28 valid days, star days mandatory, a monthly bonus for the highest tier only (450: 50, 540: 90,
620: 130, 710: 200), red marks 1 to 2 free, 3 − 10, 4 − 30, more than 4 marks or a mark on a star day: every order at
0.200 with no bonus and the shortfall still taken; the sheet's tips added and its deductions taken. Housing, phone line,
car maintenance and fuel are on the company.

Added only where the platform exists and has no scheme with this code yet. The rules are the template's
(keeta_per_order_350 in rules/templates.json) as written here.

Revision ID: 0080_keeta_per_order_scheme
Revises: 0079_platform_request_scheme
"""

import json

from alembic import op
from sqlalchemy import text

revision = "0080_keeta_per_order_scheme"
down_revision = "0079_platform_request_scheme"
branch_labels = None
depends_on = None

SCHEMES = json.loads(r"""
[
 {
  "platform": "keeta",
  "code": "keeta_per_order_350",
  "name": {
   "ar": "كيتا — بالطلب 350 فلس مع شرائح البونص",
   "en": "Keeta — 0.350 per order with bonus tiers"
  },
  "description": {
   "ar": "0.350 د.ك لكل طلب. التارجت 420 طلباً: كل طلب ناقص يُخصم 0.350. مطلوب 28 يوماً صالحاً، وأيام النجمة إلزامية. البونص الشهري لأعلى شريحة فقط: 450 طلباً 50، 540 طلباً 90، 620 طلباً 130، 710 طلباً 200 د.ك. العلامات الحمراء: 1–2 بلا خصم، 3 علامات − 10، 4 علامات − 30. أكثر من 4 علامات أو علامة في يوم نجمة: كل الطلبات بـ 0.200 بلا بونص، ويستمر خصم نقص التارجت (إلا إذا ثبت أن الخطأ ليس منه). البقشيش يُضاف، وتلف الطعام والتعديل الآخر وخصم المنصة تُخصم. السكن والخط وصيانة السيارة والبنزين على الشركة.",
   "en": "0.350 KWD per order. Target 420 orders: each order short is deducted 0.350. 28 valid days required and star days are mandatory. Monthly bonus for the highest tier only: 450 orders 50, 540 orders 90, 620 orders 130, 710 orders 200 KWD. Red marks: 1–2 free, 3 marks − 10, 4 marks − 30. More than 4 marks or a mark on a star day: every order at 0.200 with no bonus, the shortfall still deducted (unless shown not to be his fault). Tips are added; food damage, other adjustments and the platform discount are deducted. Housing, phone line, car maintenance and fuel are on the company."
  },
  "covers": [
   "gas",
   "housing",
   "maintenance",
   "sim"
  ],
  "blocks": [
   {
    "type": "exception_days",
    "params": {
     "effect": "count_valid"
    },
    "condition": [],
    "on_exception": "none",
    "group": null,
    "label": null
   },
   {
    "type": "per_order",
    "params": {
     "rate": "0.350",
     "source": "orders"
    },
    "condition": [],
    "on_exception": "none",
    "group": null,
    "label": null
   },
   {
    "type": "star_day",
    "params": {},
    "condition": [],
    "on_exception": "neutralize",
    "group": null,
    "label": null
   },
   {
    "type": "price_change",
    "params": {
     "mode": "replace",
     "rate": "0.200"
    },
    "condition": [
     {
      "fact": "month_invalid",
      "op": "is_true"
     }
    ],
    "on_exception": "none",
    "group": "reduced",
    "label": null
   },
   {
    "type": "price_change",
    "params": {
     "mode": "replace",
     "rate": "0.200"
    },
    "condition": [
     {
      "fact": "marks",
      "op": "gt",
      "value": 4
     }
    ],
    "on_exception": "none",
    "group": "reduced",
    "label": null
   },
   {
    "type": "tier_bonus",
    "params": {
     "mode": "highest",
     "source": "orders",
     "tiers": [
      {
       "from": 450,
       "amount": "50.000"
      },
      {
       "from": 540,
       "amount": "90.000"
      },
      {
       "from": 620,
       "amount": "130.000"
      },
      {
       "from": 710,
       "amount": "200.000"
      }
     ]
    },
    "condition": [
     {
      "fact": "price_changed",
      "op": "is_false"
     }
    ],
    "on_exception": "none",
    "group": null,
    "label": null
   },
   {
    "type": "required_days",
    "params": {
     "deduction": "none",
     "days": 28,
     "invalidates": false
    },
    "condition": [],
    "on_exception": "none",
    "group": null,
    "label": null
   },
   {
    "type": "missing_orders",
    "params": {
     "rate_from": "fixed",
     "source": "orders",
     "target": 420,
     "rate": "0.350"
    },
    "condition": [],
    "on_exception": "none",
    "group": null,
    "label": null
   },
   {
    "type": "attendance_marks",
    "params": {
     "mode": "table",
     "table": [
      {
       "from": 3,
       "amount": "10.000"
      },
      {
       "from": 4,
       "amount": "30.000"
      }
     ]
    },
    "condition": [
     {
      "fact": "price_changed",
      "op": "is_false"
     }
    ],
    "on_exception": "none",
    "group": null,
    "label": null
   },
   {
    "type": "platform_amounts",
    "params": {
     "tips": true,
     "food_damage": true,
     "other_adjustment": true,
     "platform_discount": true
    },
    "condition": [],
    "on_exception": "none",
    "group": null,
    "label": null
   },
   {
    "type": "expense",
    "params": {
     "kind": "housing",
     "responsibility": "company",
     "approved": false
    },
    "condition": [],
    "on_exception": "none",
    "group": null,
    "label": null
   },
   {
    "type": "expense",
    "params": {
     "kind": "phone",
     "responsibility": "company",
     "approved": false
    },
    "condition": [],
    "on_exception": "none",
    "group": null,
    "label": null
   },
   {
    "type": "expense",
    "params": {
     "kind": "maintenance",
     "responsibility": "company",
     "approved": false
    },
    "condition": [],
    "on_exception": "none",
    "group": null,
    "label": null
   },
   {
    "type": "expense",
    "params": {
     "kind": "gas",
     "responsibility": "company",
     "approved": false
    },
    "condition": [],
    "on_exception": "none",
    "group": null,
    "label": null
   }
  ]
 }
]
""")


# as in 0077_default_schemes: the scheme and its first version from this month, where it is not there yet
INSERT = text(
    """
    WITH p AS (SELECT id FROM payroll.platforms WHERE code = :platform),
    s AS (
        INSERT INTO payroll.schemes (platform_id, code, name, description, calculator, company_covers, created_by)
        SELECT p.id, :code, CAST(:name AS jsonb), CAST(:description AS jsonb), 'blocks', CAST(:covers AS text[]),
               COALESCE((SELECT min(id) FROM identity.users), 0)
        FROM p
        WHERE NOT EXISTS (SELECT 1 FROM payroll.schemes x WHERE x.platform_id = p.id AND x.code = :code)
        RETURNING id
    )
    INSERT INTO payroll.scheme_versions (scheme_id, version_no, effective_month, target_orders, required_valid_days,
                                         bonus_when_reduced, marks_when_reduced, floor_at_zero, company_covers, blocks)
    SELECT s.id, 1, date_trunc('month', now())::date, 420, 28, false, false, true, CAST(:covers AS text[]),
           CAST(:blocks AS jsonb)
    FROM s
    """
)


def upgrade() -> None:
    bind = op.get_bind()
    for s in SCHEMES:
        bind.execute(
            INSERT,
            {
                "platform": s["platform"],
                "code": s["code"],
                "name": json.dumps(s["name"], ensure_ascii=False),
                "description": json.dumps(s["description"], ensure_ascii=False),
                "covers": "{" + ",".join(s["covers"]) + "}",
                "blocks": json.dumps(s["blocks"], ensure_ascii=False),
            },
        )
    op.execute("SELECT public.fleet_apply_grants();")


def downgrade() -> None:
    raise NotImplementedError("forward-only migrations")
