"""ICU message syntax as the driver app's gen-l10n reads it (apostrophes are plain text, no escaping): text,
{name}, {name, number|date|time[, style]}, {name, plural|selectordinal, [offset:n] selector{message} ...} and
{name, select, value{message} ... other{message}}. A translation must parse, and use exactly the arguments of the
source text: a broken string would break the screen showing it, so it is refused when saved and ignored by the app."""

import re

NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
PLURAL_SELECTORS = {"zero", "one", "two", "few", "many", "other"}
SIMPLE_TYPES = {"number", "date", "time"}
MAX_DEPTH = 6


class IcuError(ValueError):
    def __init__(self, reason: str, at: int) -> None:
        super().__init__(f"{reason} at {at}")
        self.reason, self.at = reason, at


class _Parser:
    def __init__(self, text: str) -> None:
        self.s, self.i = text, 0
        self.args: dict[str, str] = {}  # name -> kind (simple, number, plural, select, ...)

    def fail(self, reason: str):
        raise IcuError(reason, self.i)

    def ws(self) -> None:
        while self.i < len(self.s) and self.s[self.i].isspace():
            self.i += 1

    def message(self, depth: int, nested: bool) -> None:
        if depth > MAX_DEPTH:
            self.fail("too_deep")
        while self.i < len(self.s):
            c = self.s[self.i]
            if c == "{":
                self.i += 1
                self.argument(depth)
            elif c == "}":
                if nested:
                    return
                self.fail("unexpected_close")
            else:
                self.i += 1
        if nested:
            self.fail("unclosed")

    def name(self) -> str:
        self.ws()
        m = NAME.match(self.s, self.i)
        if not m:
            self.fail("bad_name")
        self.i = m.end()
        return m.group(0)

    def expect(self, ch: str) -> None:
        self.ws()
        if self.i >= len(self.s) or self.s[self.i] != ch:
            self.fail("expected_" + {"{": "open", "}": "close", ",": "comma"}.get(ch, ch))
        self.i += 1

    def argument(self, depth: int) -> None:
        name = self.name()
        self.ws()
        if self.i < len(self.s) and self.s[self.i] == "}":
            self.i += 1
            self._arg(name, "simple")
            return
        self.expect(",")
        kind = self.name()
        if kind in SIMPLE_TYPES:
            self._arg(name, kind)
            self.ws()
            if self.i < len(self.s) and self.s[self.i] == ",":
                self.i += 1
                start = self.i
                while self.i < len(self.s) and self.s[self.i] not in "{}":
                    self.i += 1
                if not self.s[start : self.i].strip():
                    self.fail("bad_style")
            self.expect("}")
        elif kind in ("plural", "selectordinal", "select"):
            self._arg(name, "select" if kind == "select" else "plural")
            self.expect(",")
            self.options(kind, depth)
        else:
            self.fail("bad_type")

    def options(self, kind: str, depth: int) -> None:
        seen: set[str] = set()
        self.ws()
        if kind != "select" and self.s.startswith("offset:", self.i):
            self.i += len("offset:")
            self.ws()
            m = re.compile(r"\d+").match(self.s, self.i)
            if not m:
                self.fail("bad_offset")
            self.i = m.end()
        while True:
            self.ws()
            if self.i >= len(self.s):
                self.fail("unclosed")
            if self.s[self.i] == "}":
                self.i += 1
                break
            if kind != "select" and self.s[self.i] == "=":
                m = re.compile(r"=\d+").match(self.s, self.i)
                if not m:
                    self.fail("bad_selector")
                selector, self.i = m.group(0), m.end()
            else:
                selector = self.name()
                if kind != "select" and selector not in PLURAL_SELECTORS:
                    self.fail("bad_selector")
            if selector in seen:
                self.fail("duplicate_selector")
            seen.add(selector)
            self.expect("{")
            self.message(depth + 1, nested=True)
            self.i += 1  # the option's closing brace
        if "other" not in seen:
            self.fail("missing_other")

    def _arg(self, name: str, kind: str) -> None:
        known = self.args.get(name)
        if known and known != kind and "simple" not in (known, kind):
            self.fail("argument_kinds")
        if not known or known == "simple":
            self.args[name] = kind


def parse(text: str) -> dict[str, str]:
    """The arguments of a message (name -> kind); IcuError when it does not parse."""
    p = _Parser(text)
    p.message(0, nested=False)
    return p.args


def arguments(text: str) -> set[str]:
    try:
        return set(parse(text))
    except IcuError:
        return set()


def check(text: str, reference: str | None) -> str | None:
    """None when `text` is a valid message using exactly the arguments of `reference` (the source text), else the
    reason: "invalid:<what>@<position>", "missing:{a}, {b}" or "unknown:{c}"."""
    if not text or not text.strip():
        return "empty"
    try:
        args = parse(text)
    except IcuError as e:
        return f"invalid:{e.reason}@{e.at}"
    if reference is None:
        return None
    try:
        expected = parse(reference)
    except IcuError:
        expected = {}
    missing, unknown = sorted(set(expected) - set(args)), sorted(set(args) - set(expected))
    if missing:
        return "missing:" + ", ".join(f"{{{n}}}" for n in missing)
    if unknown:
        return "unknown:" + ", ".join(f"{{{n}}}" for n in unknown)
    for name, kind in expected.items():
        if kind in ("plural", "select") and args[name] not in (kind, "simple"):
            return f"kind:{{{name}}}"
    return None
