"""Nothing user-facing ships without its Arabic and English text, and role templates only use real permissions."""

import importlib.util
import json
import pathlib
import re

from app.core import permissions
from app.modules.org.schemas import SECTIONS

BACKEND = pathlib.Path(__file__).resolve().parents[1]
CATALOG = BACKEND / "app" / "modules" / "i18n" / "catalog"
LANGS = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in CATALOG.glob("*.json")}
PLACEHOLDER = re.compile(r"\{(\w+)\}")


def test_base_languages_have_identical_keys_and_placeholders():
    assert {"ar", "en"} <= LANGS.keys()
    ar, en = LANGS["ar"], LANGS["en"]
    assert ar.keys() == en.keys()
    for ns in ar:
        assert ar[ns].keys() == en[ns].keys(), ns
        for key, text in ar[ns].items():
            assert set(PLACEHOLDER.findall(text)) == set(PLACEHOLDER.findall(en[ns][key])), f"{ns}.{key}"
            assert text.strip() and en[ns][key].strip(), f"{ns}.{key}"


def test_every_permission_and_module_has_a_label():
    for lang, catalog in LANGS.items():
        assert catalog["permissions"].keys() == permissions.CATALOG.keys(), lang
        assert catalog["modules"].keys() == {m for m, _ in permissions.MODULES}, lang


def test_every_error_code_in_the_code_has_a_message():
    source = "\n".join(p.read_text(encoding="utf-8") for p in (BACKEND / "app").rglob("*.py"))
    codes = set(re.findall(r'AppError\(\s*\d{3},\s*"([a-z_]+)"', source)) | {"validation_error"}
    for lang, catalog in LANGS.items():
        missing = sorted(codes - catalog["errors"].keys())
        assert not missing, f"{lang}: {missing}"


def test_every_setting_has_a_label():
    for lang, catalog in LANGS.items():
        for section, model in SECTIONS.items():
            assert section in catalog["settings"], f"{lang}: {section}"
            for field in model.model_fields:
                assert f"{section}.{field}" in catalog["settings"], f"{lang}: {section}.{field}"


def test_role_templates_use_only_catalog_permissions():
    path = BACKEND / "migrations" / "versions" / "0003_role_templates.py"
    spec = importlib.util.spec_from_file_location("role_templates", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for code, _ar, _en, _system, all_permissions, perms in module.TEMPLATES:
        unknown = set(perms) - permissions.CATALOG.keys()
        assert not unknown, f"{code}: {unknown}"
        assert all_permissions or perms, code


def test_code_only_requires_catalog_permissions():
    source = "\n".join(p.read_text(encoding="utf-8") for p in (BACKEND / "app").rglob("*.py"))
    used = set(re.findall(r'require_permission\("([a-z_.]+)"\)', source))
    assert used and used <= permissions.CATALOG.keys(), used - permissions.CATALOG.keys()


def test_error_codes_mapped_from_constraints_have_a_message():
    source = "\n".join(p.read_text(encoding="utf-8") for p in (BACKEND / "app").rglob("*.py"))
    codes = set()
    for block in re.findall(r"[A-Z_]+_ERRORS = \{(.*?)\}", source, re.S):
        codes |= set(re.findall(r':\s*"([a-z_]+)"', block))
    assert codes
    for lang, catalog in LANGS.items():
        assert not codes - catalog["errors"].keys(), f"{lang}: {sorted(codes - catalog['errors'].keys())}"


def test_every_alert_kind_has_a_text_using_only_its_params():
    from app.modules.notifications.service import KINDS

    for lang, catalog in LANGS.items():
        assert catalog["alerts"].keys() == KINDS.keys(), lang
        for kind, spec in KINDS.items():
            used = set(PLACEHOLDER.findall(catalog["alerts"][kind]))
            assert used <= set(spec.params), f"{lang}: alerts.{kind} uses {used - set(spec.params)}"
            assert permissions.exists(spec.permission), kind


def test_statuses_and_flags_have_labels():
    from app.modules.fleet.service import MANUAL_STATUSES

    for lang, catalog in LANGS.items():
        assert set(MANUAL_STATUSES) | {"assigned"} == catalog["vehicle_status"].keys(), lang
        assert {"lower_than_previous", "daily_limit", "off_duty_km", "photo_reused"} == catalog["odometer_flags"].keys()
