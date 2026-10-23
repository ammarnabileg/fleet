"""The status templates the office manages: what each state card of the driver app says and looks like.

A template is data, never code: its kind picks one of the card layouts built into the app, its icon and actions come
from the lists the app ships with, its texts may only use the known variables. The app renders the same way as
`render` here (the panel's preview): a variable is replaced by its value, or by "—" when there is none.
An app that does not know a kind, an icon or an action falls back to the generic card, the default icon, or hides it.
"""

import re

# the template engine the app needs to understand this config: an older app ignores the config and shows the texts
# the server rendered for it (the alerts' title and subtitle) with its built-in cards
ENGINE_VERSION = 1

KINDS = ("shift_working", "shift_off", "vehicle_maintenance", "custody", "contact", "location", "generic")
ICONS = (
    "work",
    "off",
    "car",
    "wrench",
    "breakdown",
    "wallet",
    "phone",
    "location",
    "location_off",
    "document",
    "warning",
    "info",
    "check",
    "clock",
)
ACTIONS = (
    "open_cash",
    "open_custody",
    "open_contact",
    "call_supervisor",
    "open_location_settings",
    "open_maintenance",
    "open_documents",
    "acknowledge",
)
VARIABLES = ("amount", "due", "shift_duration", "supervisor", "last_update", "center", "stage", "document")
VISIBILITY = ("always", "working", "off_duty", "has_vehicle")
AUDIENCES = ("all", "company")
PALETTE = ("#15803D", "#6B7280", "#B45309", "#B91C1C", "#1D4ED8", "#7C3AED", "#0F766E", "#374151")
MAX_ACTIONS = 3
MAX_TEXT = 120

HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")
PLACEHOLDER = re.compile(r"\{([^{}]*)\}")
EMPTY = "—"


def _t(ar: str, en: str) -> dict:
    return {"ar": ar, "en": en}


def _tpl(kind, name, icon, color, title, subtitle, priority, actions=(), visibility="always", ttl=None) -> dict:
    return {
        "kind": kind,
        "name": name,
        "icon": icon,
        "color": color,
        "title": title,
        "subtitle": subtitle,
        "priority": priority,
        "visibility": visibility,
        "ttl_minutes": ttl,
        "audience": "all",
        "company_ids": [],
        "actions": list(actions),
        "active": True,
    }


# every state the server computes has a fixed code; these are the templates until the office publishes its own
DEFAULTS: dict[str, dict] = {
    "shift_working": _tpl(
        "shift_working",
        _t("في العمل", "Working"),
        "work",
        "#15803D",
        _t("في العمل", "Working"),
        _t("منذ {shift_duration}", "For {shift_duration}"),
        10,
    ),
    "shift_off": _tpl(
        "shift_off",
        _t("خارج الدوام", "Off duty"),
        "off",
        "#6B7280",
        _t("خارج الدوام", "Off duty"),
        _t("لم يبدأ يوم العمل", "The work day has not started"),
        10,
    ),
    "vehicle_maintenance": _tpl(
        "vehicle_maintenance",
        _t("السيارة في الصيانة", "Car in maintenance"),
        "wrench",
        "#B45309",
        _t("السيارة في الصيانة", "Your car is in maintenance"),
        _t("{center} · {stage}", "{center} · {stage}"),
        50,
        ("open_maintenance",),
        "has_vehicle",
    ),
    "vehicle_breakdown": _tpl(
        "vehicle_maintenance",
        _t("السيارة معطلة", "Car broken down"),
        "breakdown",
        "#B91C1C",
        _t("السيارة لا تصلح للقيادة", "The car is not drivable"),
        _t("حادث مفتوح · راجع المكتب", "Open accident · contact the office"),
        70,
        ("open_custody",),
        "has_vehicle",
    ),
    "custody_settlement": _tpl(
        "custody",
        _t("تسوية العهدة النقدية", "Cash settlement"),
        "wallet",
        "#B45309",
        _t("معك {amount} د.ك للتسوية", "You hold {amount} KWD to settle"),
        _t("التسوية قبل {due}", "Settle by {due}"),
        60,
        ("open_cash",),
    ),
    "contact_request": _tpl(
        "contact",
        _t("طلب تواصل من الإدارة", "Contact request"),
        "phone",
        "#1D4ED8",
        _t("{supervisor} يطلب التواصل معك", "{supervisor} asks you to get in touch"),
        _t("اضغط «اتصل» أو «تم»", "Tap Call or Done"),
        90,
        ("call_supervisor", "acknowledge"),
        ttl=24 * 60,
    ),
    "document_missing": _tpl(
        "generic",
        _t("مستند ناقص أو منتهٍ", "Missing or expired document"),
        "document",
        "#B91C1C",
        _t("{document}", "{document}"),
        _t("ناقص أو منتهٍ: جدّده من «مستنداتي»", "Missing or expired: renew it in My documents"),
        40,
        ("open_documents",),
    ),
    "location_problem": _tpl(
        "location",
        _t("مشكلة في الموقع", "Location problem"),
        "location_off",
        "#B91C1C",
        _t("الموقع لا يصل", "Your location is not coming through"),
        _t("آخر تحديث {last_update}", "Last update {last_update}"),
        80,
        ("open_location_settings",),
        "has_vehicle",
    ),
}
CODES = tuple(DEFAULTS)
# the variables each code has values for (the preview fills the others with samples; the app shows "—")
SAMPLES = {
    "amount": "125.500",
    "due": "15:00",
    "shift_duration": "3:25",
    "supervisor": "Supervisor",
    "last_update": "10:42",
    "center": "Center",
    "stage": "Quote",
    "document": "Driving licence",
}


class TemplateError(ValueError):
    def __init__(self, code: str, **params) -> None:
        super().__init__(code)
        self.code, self.params = code, params


def variables_in(text: str) -> list[str]:
    return PLACEHOLDER.findall(text)


def check_text(text: str, field: str) -> str:
    if not isinstance(text, str):
        raise TemplateError("template_text_invalid", field=field)
    text = text.strip()
    if len(text) > MAX_TEXT:
        raise TemplateError("template_text_too_long", field=field, max=MAX_TEXT)
    unknown = [v for v in variables_in(text) if v not in VARIABLES]
    if unknown:
        raise TemplateError("template_variable_unknown", field=field, variable=unknown[0])
    if "{" in PLACEHOLDER.sub("", text) or "}" in PLACEHOLDER.sub("", text):
        raise TemplateError("template_text_invalid", field=field)
    return text


def validate(code: str, data: dict, company_ids: set[int] | None = None) -> dict:
    """The template as stored, or TemplateError naming what is wrong (the panel shows it on the field)."""
    if code not in DEFAULTS:
        raise TemplateError("template_code_unknown")
    if data.get("kind") not in KINDS:
        raise TemplateError("template_kind_unknown")
    if data.get("icon") not in ICONS:
        raise TemplateError("template_icon_unknown")
    color = data.get("color")
    if not isinstance(color, str) or not HEX.match(color):
        raise TemplateError("template_color_invalid")
    out = {"kind": data["kind"], "icon": data["icon"], "color": color.upper()}
    for field in ("name", "title", "subtitle"):
        value = data.get(field) or {}
        if not isinstance(value, dict) or not all(lang in value for lang in ("ar", "en")):
            raise TemplateError("template_text_invalid", field=field)
        out[field] = {lang: check_text(value[lang], f"{field}.{lang}") for lang in ("ar", "en")}
        if field != "subtitle" and not all(out[field].values()):
            raise TemplateError("template_text_invalid", field=field)
    priority = data.get("priority")
    if not isinstance(priority, int) or isinstance(priority, bool) or not 0 <= priority <= 100:
        raise TemplateError("template_priority_invalid")
    if data.get("visibility") not in VISIBILITY:
        raise TemplateError("template_visibility_unknown")
    ttl = data.get("ttl_minutes")
    if ttl is not None and (not isinstance(ttl, int) or isinstance(ttl, bool) or not 1 <= ttl <= 43_200):
        raise TemplateError("template_ttl_invalid")
    audience = data.get("audience")
    if audience not in AUDIENCES:
        raise TemplateError("template_audience_unknown")
    ids = sorted({int(i) for i in data.get("company_ids") or []}) if audience == "company" else []
    if audience == "company" and (not ids or (company_ids is not None and not set(ids) <= company_ids)):
        raise TemplateError("template_audience_companies")
    actions = data.get("actions") or []
    if not isinstance(actions, list) or len(actions) > MAX_ACTIONS:
        raise TemplateError("template_actions_too_many", max=MAX_ACTIONS)
    if any(a not in ACTIONS for a in actions):
        raise TemplateError("template_action_unknown")
    if len(set(actions)) != len(actions):
        raise TemplateError("template_action_unknown")
    return out | {
        "priority": priority,
        "visibility": data["visibility"],
        "ttl_minutes": ttl,
        "audience": audience,
        "company_ids": ids,
        "actions": list(actions),
        "active": bool(data.get("active", True)),
    }


def fill(text: str, values: dict) -> str:
    """The app's rule: a known variable takes its value; one without a value shows "—"."""

    def one(m: re.Match) -> str:
        v = values.get(m.group(1))
        return EMPTY if v is None or v == "" else str(v)

    return PLACEHOLDER.sub(one, text)


def render(template: dict, values: dict, lang: str) -> dict:
    lang = lang if lang in ("ar", "en") else "ar"
    return {
        "kind": template["kind"],
        "icon": template["icon"],
        "color": template["color"],
        "title": fill(template["title"].get(lang) or template["title"]["ar"], values),
        "subtitle": fill(template["subtitle"].get(lang) or template["subtitle"].get("ar", ""), values),
        "actions": list(template["actions"]),
    }


def applies(template: dict, company_id: int) -> bool:
    return template.get("active", True) and (template["audience"] == "all" or company_id in template["company_ids"])
