"""Modules may talk to each other only through service, events and schemas."""

import ast
import pathlib

APP = pathlib.Path(__file__).resolve().parents[1] / "app"
MODULES = APP / "modules"
PUBLIC = {"service", "events", "schemas"}
READ_ALL = {"reports"}  # reports may read from every module


def _imports(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            yield node.module, [alias.name for alias in node.names]
        elif isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name, []


def test_modules_use_only_public_interfaces():
    violations = []
    for file in MODULES.rglob("*.py"):
        owner = file.relative_to(MODULES).parts[0]
        if owner in READ_ALL:
            continue
        for module, names in _imports(file):
            parts = module.split(".")
            if parts[:2] != ["app", "modules"] or len(parts) < 3 or parts[2] == owner:
                continue
            targets = [parts[3]] if len(parts) > 3 else names  # from app.modules.fleet import service
            bad = [t for t in targets if t not in PUBLIC]
            if bad:
                violations.append(f"{file.relative_to(MODULES)} -> {module} {bad}")
    assert not violations, "imports that break module boundaries:\n" + "\n".join(violations)


CLIENT_NAMES = ("ajwad", "أجواد")  # client differences live in settings, never in code


def test_no_client_names_in_code():
    hits = [
        str(f.relative_to(APP))
        for f in APP.rglob("*.py")
        if any(name in f.read_text(encoding="utf-8").lower() for name in CLIENT_NAMES)
    ]
    assert not hits, "client-specific code found:\n" + "\n".join(hits)
