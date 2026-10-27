"""The agreed pay schemes come built in for the two core platforms.

Keeta: a fixed salary of 200 (over 3 years), 165 (2 to 3 years) or 140 (under 2 years), target 420 with each order
above or below at 0.476 / 0.393 / 0.333, 50 at 510 orders and 100 at 610, two red marks a month free, 3 marks − 10,
4 marks − 30, a mark on a star day or more than 4 marks: the month at 0.200 per order; the sheet's tips added and its
deductions taken; housing, SIM, maintenance and fuel on the company.
Talabat: by batch (1=0.700, 2=0.675, 3=0.600, 4=0.525, 5 to 7=0.400; fuel and SIM on the driver), or a fixed price per
order: 0.350 (everything on the company), 0.550 (maintenance and housing on the company), 0.680 (everything on him).

Each is added only where its platform exists and has no scheme with its code yet (an install that set up its own keeps
them; one deleted later is not brought back by this migration). The rules are the templates' (rules/templates.json)
as they were written here; the office edits them in the rules designer like any scheme.

Revision ID: 0077_default_schemes
Revises: 0076_rider_id_months
"""

import json

from alembic import op
from sqlalchemy import text

revision = "0077_default_schemes"
down_revision = "0076_rider_id_months"
branch_labels = None
depends_on = None

SCHEMES = json.loads(r"""
[
 {
  "platform": "keeta",
  "code": "keeta_fixed_200",
  "name": {
   "ar": "كيتا — راتب ثابت 200 (فوق 3 سنوات)",
   "en": "Keeta — fixed 200 (over 3 years)"
  },
  "description": {
   "ar": "راتب ثابت 200 د.ك، التارجت 420 طلباً: كل طلب زيادة + 0.476 وكل طلب ناقص − 0.476. بونص 50 عند 510 طلباً و100 عند 610. يومان إجازة بالشهر: علامتان حمراوان بلا خصم، 3 علامات − 10، 4 علامات − 30 (خارج أيام النجمة). علامة في يوم نجمة أو أكثر من 4 علامات: الشهر كله بالطلب 0.200 بلا راتب ولا بونص، والخصومات عليه. البقشيش يُضاف، وتلف الطعام والتعديل الآخر وخصم المنصة تُخصم. السكن والخط وصيانة السيارة والبنزين على الشركة.",
   "en": "Fixed salary 200 KWD, target 420 orders: + 0.476 per order above it and − 0.476 per order below. Bonus 50 at 510 orders and 100 at 610. Two days off a month: two red marks cost nothing, 3 marks − 10, 4 marks − 30 (outside star days). A mark on a star day, or more than 4 marks: the whole month at 0.200 per order with no salary or bonus, the deductions still taken. Tips are added; food damage, other adjustments and the platform's discount are deducted. Housing, phone line, car maintenance and fuel are on the company."
  },
  "blocks": [
   {
    "type": "star_day",
    "params": {},
    "condition": [],
    "on_exception": "neutralize",
    "group": null,
    "label": null
   },
   {
    "type": "per_order",
    "params": {
     "rate": "0.200",
     "source": "orders"
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
    "type": "per_order",
    "params": {
     "rate": "0.200",
     "source": "orders"
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
    "type": "fixed_salary",
    "params": {
     "mode": "amount",
     "amount": "200.000"
    },
    "condition": [
     {
      "fact": "month_invalid",
      "op": "is_false"
     },
     {
      "fact": "marks",
      "op": "lte",
      "value": 4
     }
    ],
    "on_exception": "none",
    "group": null,
    "label": null
   },
   {
    "type": "target_overage",
    "params": {
     "source": "orders",
     "threshold": 420,
     "rate": "0.476",
     "below_rate": "0.476"
    },
    "condition": [
     {
      "fact": "month_invalid",
      "op": "is_false"
     },
     {
      "fact": "marks",
      "op": "lte",
      "value": 4
     }
    ],
    "on_exception": "none",
    "group": null,
    "label": null
   },
   {
    "type": "tier_bonus",
    "params": {
     "mode": "highest",
     "source": "orders",
     "tiers": [
      {
       "from": 510,
       "amount": "50.000"
      },
      {
       "from": 610,
       "amount": "100.000"
      }
     ]
    },
    "condition": [
     {
      "fact": "month_invalid",
      "op": "is_false"
     },
     {
      "fact": "marks",
      "op": "lte",
      "value": 4
     }
    ],
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
      "fact": "month_invalid",
      "op": "is_false"
     },
     {
      "fact": "marks",
      "op": "lte",
      "value": 4
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
  ],
  "covers": [
   "gas",
   "housing",
   "maintenance",
   "sim"
  ]
 },
 {
  "platform": "keeta",
  "code": "keeta_fixed_165",
  "name": {
   "ar": "كيتا — راتب ثابت 165 (من سنتين إلى 3)",
   "en": "Keeta — fixed 165 (2 to 3 years)"
  },
  "description": {
   "ar": "راتب ثابت 165 د.ك، التارجت 420 طلباً: كل طلب زيادة + 0.393 وكل طلب ناقص − 0.393. بونص 50 عند 510 طلباً و100 عند 610. يومان إجازة بالشهر: علامتان حمراوان بلا خصم، 3 علامات − 10، 4 علامات − 30 (خارج أيام النجمة). علامة في يوم نجمة أو أكثر من 4 علامات: الشهر كله بالطلب 0.200 بلا راتب ولا بونص، والخصومات عليه. البقشيش يُضاف، وتلف الطعام والتعديل الآخر وخصم المنصة تُخصم. السكن والخط وصيانة السيارة والبنزين على الشركة.",
   "en": "Fixed salary 165 KWD, target 420 orders: + 0.393 per order above it and − 0.393 per order below. Bonus 50 at 510 orders and 100 at 610. Two days off a month: two red marks cost nothing, 3 marks − 10, 4 marks − 30 (outside star days). A mark on a star day, or more than 4 marks: the whole month at 0.200 per order with no salary or bonus, the deductions still taken. Tips are added; food damage, other adjustments and the platform's discount are deducted. Housing, phone line, car maintenance and fuel are on the company."
  },
  "blocks": [
   {
    "type": "star_day",
    "params": {},
    "condition": [],
    "on_exception": "neutralize",
    "group": null,
    "label": null
   },
   {
    "type": "per_order",
    "params": {
     "rate": "0.200",
     "source": "orders"
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
    "type": "per_order",
    "params": {
     "rate": "0.200",
     "source": "orders"
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
    "type": "fixed_salary",
    "params": {
     "mode": "amount",
     "amount": "165.000"
    },
    "condition": [
     {
      "fact": "month_invalid",
      "op": "is_false"
     },
     {
      "fact": "marks",
      "op": "lte",
      "value": 4
     }
    ],
    "on_exception": "none",
    "group": null,
    "label": null
   },
   {
    "type": "target_overage",
    "params": {
     "source": "orders",
     "threshold": 420,
     "rate": "0.393",
     "below_rate": "0.393"
    },
    "condition": [
     {
      "fact": "month_invalid",
      "op": "is_false"
     },
     {
      "fact": "marks",
      "op": "lte",
      "value": 4
     }
    ],
    "on_exception": "none",
    "group": null,
    "label": null
   },
   {
    "type": "tier_bonus",
    "params": {
     "mode": "highest",
     "source": "orders",
     "tiers": [
      {
       "from": 510,
       "amount": "50.000"
      },
      {
       "from": 610,
       "amount": "100.000"
      }
     ]
    },
    "condition": [
     {
      "fact": "month_invalid",
      "op": "is_false"
     },
     {
      "fact": "marks",
      "op": "lte",
      "value": 4
     }
    ],
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
      "fact": "month_invalid",
      "op": "is_false"
     },
     {
      "fact": "marks",
      "op": "lte",
      "value": 4
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
  ],
  "covers": [
   "gas",
   "housing",
   "maintenance",
   "sim"
  ]
 },
 {
  "platform": "keeta",
  "code": "keeta_fixed_140",
  "name": {
   "ar": "كيتا — راتب ثابت 140 (أقل من سنتين)",
   "en": "Keeta — fixed 140 (under 2 years)"
  },
  "description": {
   "ar": "راتب ثابت 140 د.ك، التارجت 420 طلباً: كل طلب زيادة + 0.333 وكل طلب ناقص − 0.333. بونص 50 عند 510 طلباً و100 عند 610. يومان إجازة بالشهر: علامتان حمراوان بلا خصم، 3 علامات − 10، 4 علامات − 30 (خارج أيام النجمة). علامة في يوم نجمة أو أكثر من 4 علامات: الشهر كله بالطلب 0.200 بلا راتب ولا بونص، والخصومات عليه. البقشيش يُضاف، وتلف الطعام والتعديل الآخر وخصم المنصة تُخصم. السكن والخط وصيانة السيارة والبنزين على الشركة.",
   "en": "Fixed salary 140 KWD, target 420 orders: + 0.333 per order above it and − 0.333 per order below. Bonus 50 at 510 orders and 100 at 610. Two days off a month: two red marks cost nothing, 3 marks − 10, 4 marks − 30 (outside star days). A mark on a star day, or more than 4 marks: the whole month at 0.200 per order with no salary or bonus, the deductions still taken. Tips are added; food damage, other adjustments and the platform's discount are deducted. Housing, phone line, car maintenance and fuel are on the company."
  },
  "blocks": [
   {
    "type": "star_day",
    "params": {},
    "condition": [],
    "on_exception": "neutralize",
    "group": null,
    "label": null
   },
   {
    "type": "per_order",
    "params": {
     "rate": "0.200",
     "source": "orders"
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
    "type": "per_order",
    "params": {
     "rate": "0.200",
     "source": "orders"
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
    "type": "fixed_salary",
    "params": {
     "mode": "amount",
     "amount": "140.000"
    },
    "condition": [
     {
      "fact": "month_invalid",
      "op": "is_false"
     },
     {
      "fact": "marks",
      "op": "lte",
      "value": 4
     }
    ],
    "on_exception": "none",
    "group": null,
    "label": null
   },
   {
    "type": "target_overage",
    "params": {
     "source": "orders",
     "threshold": 420,
     "rate": "0.333",
     "below_rate": "0.333"
    },
    "condition": [
     {
      "fact": "month_invalid",
      "op": "is_false"
     },
     {
      "fact": "marks",
      "op": "lte",
      "value": 4
     }
    ],
    "on_exception": "none",
    "group": null,
    "label": null
   },
   {
    "type": "tier_bonus",
    "params": {
     "mode": "highest",
     "source": "orders",
     "tiers": [
      {
       "from": 510,
       "amount": "50.000"
      },
      {
       "from": 610,
       "amount": "100.000"
      }
     ]
    },
    "condition": [
     {
      "fact": "month_invalid",
      "op": "is_false"
     },
     {
      "fact": "marks",
      "op": "lte",
      "value": 4
     }
    ],
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
      "fact": "month_invalid",
      "op": "is_false"
     },
     {
      "fact": "marks",
      "op": "lte",
      "value": 4
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
  ],
  "covers": [
   "gas",
   "housing",
   "maintenance",
   "sim"
  ]
 },
 {
  "platform": "talabat",
  "code": "talabat_batch_plan",
  "name": {
   "ar": "طلبات — نظام الباتش",
   "en": "Talabat — batch"
  },
  "description": {
   "ar": "سعر الطلب حسب الباتش: 1=0.700، 2=0.675، 3=0.600، 4=0.525، 5 و6 و7=0.400. الطلبات قد تأتي مقسمة على أكثر من باتش في الشهر، وكل باتش بسعره. في كل الباتشات يتحمل السائق البنزين وشريحة الهاتف.",
   "en": "Price per order by batch: 1=0.700, 2=0.675, 3=0.600, 4=0.525, 5, 6 and 7=0.400. A month's orders may be split by batch, each at its own price. In every batch the driver pays the fuel and the SIM."
  },
  "blocks": [
   {
    "type": "batch_rate",
    "params": {
     "rates": [
      {
       "batch": 1,
       "rate": "0.700"
      },
      {
       "batch": 2,
       "rate": "0.675"
      },
      {
       "batch": 3,
       "rate": "0.600"
      },
      {
       "batch": 4,
       "rate": "0.525"
      },
      {
       "batch": 5,
       "rate": "0.400"
      },
      {
       "batch": 6,
       "rate": "0.400"
      },
      {
       "batch": 7,
       "rate": "0.400"
      }
     ],
     "personal_rate": true
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
     "responsibility": "driver",
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
     "responsibility": "driver",
     "approved": false
    },
    "condition": [],
    "on_exception": "none",
    "group": null,
    "label": null
   }
  ],
  "covers": []
 },
 {
  "platform": "talabat",
  "code": "talabat_fixed_350",
  "name": {
   "ar": "طلبات — 350 فلس للطلب",
   "en": "Talabat — 0.350 per order"
  },
  "description": {
   "ar": "كل طلب بـ 0.350، الشركة تتحمل الصيانة والسكن والبنزين والهاتف (للعلم، لا خصم تلقائي)، ولا خصم على نقص التارجت.",
   "en": "Each order at 0.350; the company bears maintenance, housing, gas and phone (for information, never deducted automatically); no missing-target deduction."
  },
  "blocks": [
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
     "kind": "gas",
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
   }
  ],
  "covers": [
   "gas",
   "housing",
   "maintenance",
   "sim"
  ]
 },
 {
  "platform": "talabat",
  "code": "talabat_fixed_550",
  "name": {
   "ar": "طلبات — 550 فلس للطلب",
   "en": "Talabat — 0.550 per order"
  },
  "description": {
   "ar": "كل طلب بـ 0.550، السائق يتحمل البنزين والهاتف (للعلم، لا خصم تلقائي)، ولا خصم على نقص التارجت.",
   "en": "Each order at 0.550; the driver bears gas and phone (for information, never deducted automatically); no missing-target deduction."
  },
  "blocks": [
   {
    "type": "per_order",
    "params": {
     "rate": "0.550",
     "source": "orders"
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
     "kind": "gas",
     "responsibility": "driver",
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
     "responsibility": "driver",
     "approved": false
    },
    "condition": [],
    "on_exception": "none",
    "group": null,
    "label": null
   }
  ],
  "covers": [
   "housing",
   "maintenance"
  ]
 },
 {
  "platform": "talabat",
  "code": "talabat_fixed_680",
  "name": {
   "ar": "طلبات — 680 فلس للطلب",
   "en": "Talabat — 0.680 per order"
  },
  "description": {
   "ar": "كل طلب بـ 0.680، السائق يتحمل الصيانة والسكن والبنزين والهاتف (للعلم، لا خصم تلقائي)، ولا خصم على نقص التارجت.",
   "en": "Each order at 0.680; the driver bears maintenance, housing, gas and phone (for information, never deducted automatically); no missing-target deduction."
  },
  "blocks": [
   {
    "type": "per_order",
    "params": {
     "rate": "0.680",
     "source": "orders"
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
     "responsibility": "driver",
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
     "kind": "housing",
     "responsibility": "driver",
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
     "responsibility": "driver",
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
     "responsibility": "driver",
     "approved": false
    },
    "condition": [],
    "on_exception": "none",
    "group": null,
    "label": null
   }
  ],
  "covers": []
 }
]
""")

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
