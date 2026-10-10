"""The rule-block engine: a scheme version is an ordered list of blocks, run once each, top to bottom (the order is the
priority the office approved, never inferred). Each block may carry a condition (facts from a fixed list, combined
with AND), a priority group (within a group only the first block whose condition holds applies) and a behaviour on
the driver's approved exceptions. Every block writes payslip lines with what it read, its formula and its result;
what it did not do is in the trace, with the reason.

At the end, as decision D says: penalties never take the month below zero when the version floors at zero; what they
could not take is a line of its own (uncovered_penalty), shown for review, never silent.

Pure: the month's facts come in, lines come out. Money is exact decimals rounded to the fils, half up."""

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from app.core.errors import AppError
from app.modules.payroll.calculators import ZERO, money
from app.modules.payroll.rules.catalog import (
    BUILTIN_SOURCES,
    EXCEPTION_KINDS,
    FACT_NEEDS,
    FACTS,
    KEY,
    SETS_INVALID,
    TYPES,
    Param,
)

MAX_BLOCKS = 60
ACCEPTED = ("accepted_excuse", "exception_day")  # the exceptions that excuse attendance


@dataclass(frozen=True)
class MonthException:
    """An approved exception of the driver's month: an accepted excuse, a company data error with its corrected
    figures, or a day approved as an exception. Entered in month review (or imported), with a note and who approved."""

    kind: str
    days: int = 0  # how many days (or marks, late counts) it covers; 0: all of them
    corrections: dict = field(default_factory=dict)  # company_error: {fact: corrected value}
    excuses: tuple = ()  # what it excuses, each on its own: star_day | marks | lateness | absence | valid_days


@dataclass(frozen=True)
class Facts:
    """A driver's month as the blocks read it: the approved figures, the month inputs and his contract."""

    orders: int | None = None
    valid_days: int | None = None
    working_days: int | None = None
    hours: Decimal | None = None
    star_day_failed: bool | None = None
    attendance_marks: int | None = None
    late_count: int | None = None
    absent_days: int | None = None
    batches: tuple[tuple[int, int], ...] | None = None  # (batch, orders): a month may have several batch rows
    batch_level: int | None = None  # one batch for the whole month (the statement's figure)
    tasks: dict | None = None  # task type -> count
    basic_salary: Decimal | None = None  # his contract's basic salary
    personal_rate: Decimal | None = None  # a price per order agreed with him (his scheme assignment)
    fields: dict = field(default_factory=dict)  # the platform's own fields: monthly values, totals of daily ones
    exceptions: tuple[MonthException, ...] = ()


@dataclass
class Line:
    code: str  # a salary-sheet column (columns.py)
    amount: Decimal  # earnings positive, penalties negative
    why: dict  # what it read
    formula: str = ""
    block: int | None = None  # the block's position, from 1
    type: str | None = None


@dataclass
class Outcome:
    items: list[Line]
    pay: Decimal
    penalties: Decimal
    uncovered: Decimal
    trace: list[dict]
    problems: list[str] = field(default_factory=list)  # what the blocks could not price (the line is flagged)


# ------------------------------------------------------------------ validation


def _bad(code: str, position: int | None = None, **params):
    return AppError(422, code, **({"position": position} if position else {}), **params)


def _money(v) -> str:
    try:
        d = Decimal(str(v))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError from None
    if not d.is_finite() or d < 0 or d >= Decimal("1000000000") or d != d.quantize(Decimal("0.001")):
        raise ValueError
    return str(d.quantize(Decimal("0.001")))


def _int(v, low: int | None = None, high: int | None = None) -> int:
    if isinstance(v, bool) or not isinstance(v, int | float | str | Decimal):
        raise ValueError
    d = Decimal(str(v))
    if not d.is_finite() or d != d.to_integral_value() or d < 0 or d > 1000000:
        raise ValueError
    if (low is not None and d < low) or (high is not None and d > high):
        raise ValueError
    return int(d)


def _param(p: Param, raw, *, sources: set[str] | None):
    if p.kind == "money":
        return _money(raw)
    if p.kind == "int":
        return _int(raw, p.low, p.high)
    if p.kind == "bool":
        if not isinstance(raw, bool):
            raise ValueError
        return raw
    if p.kind == "choice":
        if raw not in p.options:
            raise ValueError
        return raw
    if p.kind == "source":
        if raw in BUILTIN_SOURCES:
            return raw
        if not isinstance(raw, str) or not KEY.match(raw) or (sources is not None and raw not in sources):
            raise ValueError
        return raw
    if p.kind == "key":
        if not isinstance(raw, str) or not KEY.match(raw):
            raise ValueError
        return raw
    if p.kind == "rows":
        if not isinstance(raw, list) or not raw or len(raw) > 50:
            raise ValueError
        rows = []
        for r in raw:
            if not isinstance(r, dict) or set(r) - {x.name for x in p.rows}:
                raise ValueError
            rows.append({x.name: _param(x, r.get(x.name), sources=sources) for x in p.rows})
        first = p.rows[0].name
        if len({str(r[first]) for r in rows}) != len(rows):
            raise ValueError  # a threshold, a batch or a task type twice
        if p.rows[0].kind == "int":
            rows.sort(key=lambda r: r[first])
        return rows
    raise ValueError


def _wanted(p: Param, params: dict) -> bool:
    if p.when is None:
        return True
    other, values = p.when
    return str(params.get(other)) in values.split("|")


def _condition(raw, position: int, *, sources: set[str] | None) -> list[dict]:
    if raw in (None, []):
        return []
    if not isinstance(raw, list) or len(raw) > 10:
        raise _bad("rule_condition_invalid", position)
    out = []
    for c in raw:
        if not isinstance(c, dict) or set(c) - {"fact", "op", "value", "key"}:
            raise _bad("rule_condition_invalid", position)
        fact, op = c.get("fact"), c.get("op")
        if not isinstance(fact, str) or not isinstance(op, str) or fact not in FACTS or op not in FACTS[fact]:
            raise _bad("rule_condition_invalid", position)
        clause = {"fact": fact, "op": op}
        try:
            if fact == "field":
                key = c.get("key")
                if not isinstance(key, str) or not KEY.match(key) or (sources is not None and key not in sources):
                    raise ValueError
                clause["key"] = key
            if fact == "has_exception":
                if not isinstance(c.get("value"), str) or c["value"] not in (*EXCEPTION_KINDS, "any"):
                    raise ValueError
                clause["value"] = c["value"]
            elif op not in ("is_true", "is_false"):
                clause["value"] = _int(c.get("value"))
        except (ValueError, InvalidOperation, TypeError):
            raise _bad("rule_condition_invalid", position) from None
        out.append(clause)
    return out


def validate(blocks, *, sources: set[str] | None = None) -> list[dict]:
    """The blocks as stored, or 422 with the first problem and the block's position: an unknown type, a missing or
    wrong parameter, a price change without a condition, an order that cannot work (a price change before anything
    priced the orders, a condition on a state no earlier block sets), an exception behaviour the type does not take.
    `sources`: the fields the platform defines, when known (a block may only read those or the month's figures)."""
    if not isinstance(blocks, list) or not blocks:
        raise _bad("rule_blocks_empty")
    if len(blocks) > MAX_BLOCKS:
        raise _bad("rule_blocks_too_many", max=MAX_BLOCKS)
    known = None if sources is None else set(sources)
    out: list[dict] = []
    priced = sets_invalid = changes_price = False
    price_groups: list = []  # the priority group of each price change so far
    excused_by_block: set = set()  # the exception effects an exception-days block already applied
    for position, b in enumerate(blocks, start=1):
        if not isinstance(b, dict) or set(b) - {"type", "params", "condition", "on_exception", "group", "label"}:
            raise _bad("rule_block_unknown", position, type="?")
        t = TYPES.get(b.get("type")) if isinstance(b.get("type"), str) else None
        if t is None:
            raise _bad("rule_block_unknown", position, type=str(b.get("type"))[:40])
        raw = b.get("params") or {}
        if not isinstance(raw, dict) or set(raw) - {p.name for p in t.params}:
            raise _bad("rule_block_param", position, param=next(iter(set(raw) - {p.name for p in t.params}), "?"))
        params = {}
        for p in t.params:  # the choices first: a parameter may be wanted only for one of them
            value = raw.get(p.name)
            if value is None or value == "":
                value = p.default
            if p.kind == "choice" and value is not None:
                params[p.name] = value
        for p in t.params:
            value = raw.get(p.name)
            if value is None or value == "" or value == []:
                value = p.default
            if value is None:
                if p.required and _wanted(p, params):
                    raise _bad("rule_block_param", position, param=p.name)
                params.pop(p.name, None)
                continue
            try:
                params[p.name] = _param(p, value, sources=known)
            except (ValueError, InvalidOperation, TypeError):
                raise _bad("rule_block_param", position, param=p.name) from None
        condition = _condition(b.get("condition"), position, sources=known)
        if t.needs_condition and not condition:
            raise _bad("rule_block_condition_required", position)
        for c in condition:
            if c["fact"] == "month_invalid" and not sets_invalid:
                raise _bad("rule_block_order", position)  # nothing before it can make the month invalid
            if c["fact"] == "price_changed" and not changes_price:
                raise _bad("rule_block_order", position)
        if t.code == "price_change" and not priced:
            raise _bad("rule_block_order", position)  # nothing before it priced the orders
        if t.code == "special_day_violation" and params.get("when") == "month_invalid" and not sets_invalid:
            raise _bad("rule_block_order", position)
        on_exc = b.get("on_exception") or "none"
        if on_exc not in t.exceptions:
            raise _bad("rule_block_exception", position)
        group = b.get("group") or None
        if group is not None and (not isinstance(group, str) or not KEY.match(group)):
            raise _bad("rule_block_param", position, param="group")
        label = b.get("label") or None
        if label is not None and (not isinstance(label, str) or len(label) > 80):
            raise _bad("rule_block_param", position, param="label")
        if t.code == "price_change":
            # two price changes would both take from the price the orders had: only one of a priority group applies
            if price_groups and (group is None or any(g != group for g in price_groups)):
                raise _bad("rule_price_change_twice", position)
            price_groups.append(group)
        effect = {"count_valid": "count_valid", "neutralize": "excuse_attendance"}.get(on_exc)
        if t.code == "exception_days":
            effect = params["effect"]
            if effect in excused_by_block:
                raise _bad("rule_exception_twice", position)
            excused_by_block.add(effect)
        elif effect in excused_by_block:
            raise _bad("rule_exception_twice", position)  # an exception-days block above already counted them
        priced = priced or (t.prices_orders and params.get("source", "orders") == "orders")
        sets_invalid = sets_invalid or t.code in SETS_INVALID
        changes_price = changes_price or t.code == "price_change"
        out.append(
            {
                "type": t.code,
                "params": params,
                "condition": condition,
                "on_exception": on_exc,
                "group": group,
                "label": label,
            }
        )
    if not any(TYPES[b["type"]].category == "pay" for b in out):
        raise _bad("rule_pay_missing")
    return out


# ------------------------------------------------------------------ what the blocks read


def needs(blocks: list[dict], facts: Facts) -> list[str]:
    """The month's figures the blocks read that are missing: the line is flagged and blocks approval, nothing is
    guessed."""
    wanted: list[str] = []
    fixed_amount = False  # a fixed salary of an amount above: the daily wage of an absence is taken from it
    for b in blocks:
        t, p = TYPES[b["type"]], b["params"]
        names = list(t.needs)
        if "source" in {x.name for x in t.params}:
            names.append(p.get("source", "orders"))
        if b["type"] == "commitment_bonus" and p.get("require_clean", True):
            names += ["attendance_marks", "late_count", "absent_days"]
        if b["type"] == "fixed_salary":
            if p.get("mode") == "contract":
                names.append("basic_salary")
            else:
                fixed_amount = True
        if b["type"] == "absence" and p.get("mode") == "daily_wage" and not fixed_amount:
            names.append("basic_salary")
        if b["type"] == "invalid_days":
            names.append("valid_days")
            if p.get("mode") == "daily_wage":
                names.append("basic_salary")
        if b["type"] == "special_day_violation" and p.get("when") == "star_day_failed":
            names.append("star_day_failed")
        if b["type"] == "required_days" and not p.get("invalidates") and p.get("deduction", "none") == "none":
            names = [n for n in names if n != "valid_days"]  # for information only: nothing waits for it
        if b["type"] == "batch_rate" and facts.personal_rate is not None and p.get("personal_rate", True):
            names = ["orders"]
        for c in b["condition"]:
            if c["fact"] == "field":
                names.append(c["key"])
            elif c["fact"] in FACT_NEEDS:
                names.append(FACT_NEEDS[c["fact"]])
        for n in names:
            if n not in wanted:
                wanted.append(n)
    return [n for n in wanted if _raw(facts, n) is None]


def _raw(facts: Facts, name: str):
    if name == "batches":
        return facts.batches if facts.batches else (None if facts.batch_level is None else facts.batch_level)
    if name == "tasks":
        return facts.tasks
    if name in BUILTIN_SOURCES or name in ("star_day_failed", "basic_salary"):
        return getattr(facts, name)
    return facts.fields.get(name)


# ------------------------------------------------------------------ running


@dataclass
class _State:
    values: dict
    batches: list
    lines: list[Line] = field(default_factory=list)
    trace: list[dict] = field(default_factory=list)
    orders_lines: list[int] = field(default_factory=list)  # the lines that priced the month's orders
    invalid_by: set = field(default_factory=set)  # what made the month invalid: star_day, required_days
    price_changed: bool = False
    problems: list = field(default_factory=list)
    penalized: bool = False
    fixed_salary: Decimal | None = None
    groups: dict = field(default_factory=dict)


def _d(v) -> Decimal:
    return Decimal(str(v)) if v is not None else ZERO


def _n(v) -> str:
    """A number as the formula shows it."""
    d = _d(v)
    return str(d.quantize(Decimal("0.001"))) if d != d.to_integral_value() else str(int(d))


def _excusing(facts: Facts, what: str) -> list[MonthException]:
    return [e for e in facts.exceptions if e.kind in ACCEPTED and what in (e.excuses or ())]


def _excused(value, exceptions: list[MonthException]):
    """A count less what the exceptions excuse (one of them for no number of days: all of it)."""
    if value is None or not exceptions:
        return value
    if any(not e.days for e in exceptions):
        return 0
    return max(0, value - sum(int(e.days) for e in exceptions))


def _valid_extra(facts: Facts) -> int:
    """The days approved exceptions count as valid (only those that excuse valid days, by their number of days)."""
    return sum(max(0, int(e.days or 0)) for e in _excusing(facts, "valid_days"))


def _excuse(values: dict, facts: Facts) -> bool:
    """The attendance facts as the approved exceptions excuse them, each by what it names; True when the star day is
    excused (a number of days never excuses a missed star day)."""
    star = bool(_excusing(facts, "star_day"))
    if star and values.get("star_day_failed") is not None:
        values["star_day_failed"] = False
    for what, key in (("marks", "attendance_marks"), ("lateness", "late_count"), ("absence", "absent_days")):
        values[key] = _excused(values.get(key), _excusing(facts, what))
    return star


def _view(st: _State, facts: Facts, b: dict) -> dict:
    """What this block sees: the month's values, with its exception behaviour applied."""
    v = dict(st.values)
    invalid_by = set(st.invalid_by)
    if b["on_exception"] == "neutralize" and _excuse(v, facts):
        invalid_by.discard("star_day")
    if b["on_exception"] == "count_valid" and v.get("valid_days") is not None:
        v["valid_days"] = v["valid_days"] + _valid_extra(facts)
    v["month_invalid"] = bool(invalid_by)
    return v


def _value(v: dict, source: str):
    return v.get(source) if source in BUILTIN_SOURCES else v.get("fields", {}).get(source)


def _holds(c: dict, v: dict, st: _State, facts: Facts) -> bool:
    fact, op = c["fact"], c["op"]
    if fact == "has_exception":
        kinds = {e.kind for e in facts.exceptions}
        found = bool(kinds) if c["value"] == "any" else c["value"] in kinds
        return found if op == "has" else not found
    if fact == "batch":
        return any(b == c["value"] and n for b, n in st.batches)
    value = (
        {
            "star_day_failed": v.get("star_day_failed"),
            "month_invalid": v.get("month_invalid"),
            "price_changed": st.price_changed,
            "penalized": st.penalized,
            "marks": v.get("attendance_marks"),
            "valid_days": v.get("valid_days"),
            "orders": v.get("orders"),
            "late_count": v.get("late_count"),
            "absent_days": v.get("absent_days"),
        }.get(fact)
        if fact != "field"
        else v.get("fields", {}).get(c["key"])
    )
    if op == "is_true":
        return bool(value)
    if op == "is_false":
        return not value
    x, y = _d(value), Decimal(c["value"])
    return {"gt": x > y, "gte": x >= y, "lt": x < y, "lte": x <= y, "eq": x == y}[op]


def _line(st: _State, b: dict, pos: int, code: str, amount: Decimal, why: dict, formula: str) -> Line:
    line = Line(code, money(amount), why, formula, pos, b["type"])
    st.lines.append(line)
    if line.amount < 0:
        st.penalized = True
    return line


def _rate_for(rows: list[dict], key: str, value) -> Decimal | None:
    """The row for this value, or the highest one below it (never a guess above)."""
    exact = next((r for r in rows if r[key] == value), None)
    if exact is not None:
        return Decimal(exact["rate"])
    below = [r for r in rows if value is not None and r[key] <= value]
    return Decimal(below[-1]["rate"]) if below else None


def _reduced_by(b: dict) -> str | None:
    facts = {c["fact"] for c in b["condition"]}
    if facts & {"star_day_failed", "month_invalid"}:
        return "star_day"
    if "marks" in facts:
        return "marks"
    return None


def _apply(st: _State, facts: Facts, b: dict, pos: int, v: dict) -> str | None:
    """Runs one block whose condition holds; None when it applied, else the reason it did nothing."""
    t, p = b["type"], b["params"]
    if t == "per_order":
        source = p.get("source", "orders")
        n, rate = _d(_value(v, source)), Decimal(p["rate"])
        amount = money(n * rate)
        if source == "orders":
            _line(
                st, b, pos, "orders_pay", amount, {"orders": int(n), "rate": str(rate)}, f"{_n(n)} × {rate} = {amount}"
            )
            st.orders_lines.append(len(st.lines) - 1)
        else:
            why = {"source": source, "count": _n(n), "rate": str(rate)}
            _line(st, b, pos, "count_pay", amount, why, f"{_n(n)} × {rate} = {amount}")
        return None
    if t == "fixed_salary":
        contract = p["mode"] == "contract"
        amount = money(facts.basic_salary if contract else p["amount"])
        st.fixed_salary = amount
        _line(st, b, pos, "fixed_salary", amount, {"mode": p["mode"]}, f"{amount}")
        return None
    if t == "tiered_rate":
        source = p.get("source", "orders")
        n, tiers = _d(_value(v, source)), p["tiers"]
        if p["mode"] == "all":
            reached = [x for x in tiers if n >= x["from"]]
            rate = Decimal(reached[-1]["rate"]) if reached else ZERO
            amount, formula = money(n * rate), f"{_n(n)} × {rate} = {money(n * rate)}"
            why = {"orders": int(n), "rate": str(rate), "from": reached[-1]["from"] if reached else None}
        else:  # each tier's rate for the orders beyond its start, up to the next tier
            parts, total = [], ZERO
            for i, x in enumerate(tiers):
                top = Decimal(tiers[i + 1]["from"]) if i + 1 < len(tiers) else None
                units = max(ZERO, (min(n, top) if top is not None else n) - x["from"])
                if units:
                    total += units * Decimal(x["rate"])
                    parts.append(f"{_n(units)} × {x['rate']}")
            amount = money(total)
            formula = f"{' + '.join(parts) or '0'} = {amount}"
            why = {"orders": int(n), "progressive": True}
            rate = (amount / n).quantize(Decimal("0.001")) if n else ZERO
            why["rate"] = str(rate)
        code = "orders_pay" if source == "orders" else "count_pay"
        _line(st, b, pos, code, amount, why, formula)
        if source == "orders":
            st.orders_lines.append(len(st.lines) - 1)
        return None
    if t == "batch_rate":
        if facts.personal_rate is not None and p.get("personal_rate", True):
            n = sum(x for _, x in st.batches) if st.batches else int(_d(v.get("orders")))
            rate = Decimal(facts.personal_rate)
            amount = money(n * rate)
            why = {"orders": n, "rate": str(rate), "personal": True}
            _line(st, b, pos, "orders_pay", amount, why, f"{n} × {rate} = {amount}")
            st.orders_lines.append(len(st.lines) - 1)
            return None
        for batch, n in st.batches:
            if not any(r["batch"] == batch for r in p["rates"]):  # priced as the highest batch below it, flagged
                st.problems.append("batch_rate_missing")
                st.trace.append({"block": pos, "type": t, "info": "batch_rate_missing", "batch": batch})
            rate = _rate_for(p["rates"], "batch", batch) or ZERO
            amount = money(n * rate)
            why = {"orders": n, "rate": str(rate), "batch_level": batch}
            _line(st, b, pos, "orders_pay", amount, why, f"{n} × {rate} = {amount}")
            st.orders_lines.append(len(st.lines) - 1)
        return None if st.batches else "no_batches"
    if t == "per_task_type":
        tasks = facts.tasks or {}
        for r in p["rates"]:
            n, rate = int(tasks.get(r["task"], 0) or 0), Decimal(r["rate"])
            amount = money(n * rate)
            why = {"task": r["task"], "count": n, "rate": str(rate)}
            _line(st, b, pos, "tasks_pay", amount, why, f"{n} × {rate} = {amount}")
        return None
    if t == "monthly_bonus":
        amount = money(p["amount"])
        _line(st, b, pos, "monthly_bonus", amount, {}, f"{amount}")
        return None
    if t == "target_overage":
        source = p.get("source", "orders")
        n, top = _d(_value(v, source)), Decimal(p["threshold"])
        rate = Decimal(p["rate"])
        if n > top:
            amount = money((n - top) * rate)
            why = {"orders": int(n), "threshold": int(top), "rate": str(rate)}
            _line(st, b, pos, "target_bonus", amount, why, f"({_n(n)} − {_n(top)}) × {rate} = {amount}")
            return None
        if n < top and p.get("below_rate"):
            below = Decimal(p["below_rate"])
            amount = money((top - n) * below)
            why = {"orders": int(n), "threshold": int(top), "rate": str(below)}
            _line(st, b, pos, "target_shortfall", -amount, why, f"({_n(top)} − {_n(n)}) × {below} = −{amount}")
            return None
        return "at_threshold"
    if t == "tier_bonus":
        n = _d(_value(v, p.get("source", "orders")))
        reached = [x for x in p["tiers"] if n >= x["from"]]
        if not reached:
            return "below_tiers"
        if p["mode"] == "cumulative":
            amount = money(sum(Decimal(x["amount"]) for x in reached))
            formula = " + ".join(x["amount"] for x in reached) + f" = {amount}"
        else:
            amount = money(reached[-1]["amount"])
            formula = f"{_n(n)} ≥ {reached[-1]['from']} → {amount}"
        why = {"orders": int(n), "from": reached[-1]["from"]}
        _line(st, b, pos, "tier_bonus", amount, why, formula)
        return None
    if t == "commitment_bonus":
        if p.get("require_clean", True):
            dirty = {k: v.get(k) for k in ("attendance_marks", "late_count", "absent_days") if v.get(k)}
            if dirty:
                return "not_clean"
        amount = money(p["amount"])
        _line(st, b, pos, "commitment_bonus", amount, {}, f"{amount}")
        return None
    if t == "required_days":
        valid = v.get("valid_days")
        if valid is None:
            return "figure_missing"
        days = p["days"]
        if valid >= days:
            return "enough_days"
        if p.get("invalidates"):
            st.invalid_by.add("required_days")
        why = {"valid_days": valid, "required": days}
        if p["deduction"] == "fixed":
            amount = money(p["amount"])
            _line(st, b, pos, "required_days_deduction", -amount, why, f"{valid} < {days} → −{amount}")
        elif p["deduction"] == "per_day":
            amount = money((days - valid) * Decimal(p["amount"]))
            formula = f"({days} − {valid}) × {p['amount']} = −{amount}"
            _line(st, b, pos, "required_days_deduction", -amount, why, formula)
        else:
            st.trace.append({"block": pos, "type": t, "info": "below_required", **why})
        return None
    if t == "lateness":
        n = int(v.get("late_count") or 0)
        if not n:
            return "none_counted"
        amount = money(n * Decimal(p["amount"]))
        why = {"late": n, "rate": p["amount"]}
        _line(st, b, pos, "late_deduction", -amount, why, f"{n} × {p['amount']} = −{amount}")
        return None
    if t == "absence":
        n = int(v.get("absent_days") or 0)
        if not n:
            return "none_counted"
        if p["mode"] == "daily_wage":
            base = st.fixed_salary if st.fixed_salary is not None else money(facts.basic_salary)
            rate = money(base / p.get("divisor", 30))
            formula = f"{n} × ({base} ÷ {p.get('divisor', 30)} = {rate})"
        else:
            rate = Decimal(p["amount"])
            formula = f"{n} × {rate}"
        amount = money(n * rate)
        _line(st, b, pos, "absence_days_deduction", -amount, {"days": n, "rate": str(rate)}, f"{formula} = −{amount}")
        return None
    if t == "invalid_days":
        valid, worked = v.get("valid_days"), v.get("working_days")
        if valid is None:
            return "figure_missing"
        days = max(0, int(worked or 0) - valid)
        if not days:
            return "none_counted"
        if p["mode"] == "daily_wage":
            base = money(facts.basic_salary)
            rate = money(base / p.get("divisor", 30))
            formula = f"{days} × ({base} ÷ {p.get('divisor', 30)} = {rate})"
        else:
            rate = money(p["amount"])
            formula = f"{days} × {rate}"
        amount = money(days * rate)
        why = {"days": days, "working_days": int(worked or 0), "valid_days": valid, "rate": str(rate)}
        _line(st, b, pos, "invalid_days_deduction", -amount, why, f"{formula} = −{amount}")
        return None
    if t == "star_day":
        if not v.get("star_day_failed"):
            return "star_day_kept"
        st.invalid_by.add("star_day")
        st.trace.append({"block": pos, "type": t, "info": "month_invalid"})
        return None
    if t == "missing_orders":
        n, target = _d(_value(v, p.get("source", "orders"))), p["target"]
        short = max(ZERO, target - n)
        if not short:
            return "target_reached"
        rate = Decimal(p["rate"])
        amount = money(short * rate)
        why = {"target": target, "missing": int(short), "rate": str(rate)}
        _line(st, b, pos, "missing_target", -amount, why, f"({target} − {_n(n)}) × {rate} = −{amount}")
        return None
    if t == "attendance_marks":
        marks = int(v.get("attendance_marks") or 0)
        if p["mode"] == "per_mark":
            amount = money(marks * Decimal(p["amount"]))
            formula = f"{marks} × {p['amount']} = −{amount}"
        else:
            reached = [x for x in p["table"] if marks >= x["from"]]
            amount = money(reached[-1]["amount"]) if reached else ZERO
            formula = f"{marks} ≥ {reached[-1]['from']} → −{amount}" if reached else ""
        if not amount:
            return "none_counted"
        _line(st, b, pos, "marks_deduction", -amount, {"marks": marks}, formula)
        return None
    if t == "special_day_violation":
        hit = v.get("month_invalid") if p.get("when", "month_invalid") == "month_invalid" else v.get("star_day_failed")
        if not hit:
            return "month_valid"
        amount = money(p["amount"])
        _line(st, b, pos, "special_day_deduction", -amount, {"when": p.get("when", "month_invalid")}, f"−{amount}")
        return None
    if t == "price_change":
        if not st.orders_lines:
            return "nothing_priced"
        rate = Decimal(p["rate"])
        lines = [st.lines[i] for i in st.orders_lines]
        if p["mode"] == "replace":  # the orders' own lines now carry the new price
            for line in lines:
                n = line.why["orders"]
                old = line.why.get("base_rate", line.why["rate"])
                line.amount = money(n * rate)
                line.why = {**line.why, "rate": str(rate), "base_rate": old, "changed_by": pos}
                if _reduced_by(b):
                    line.why["reduced_by"] = _reduced_by(b)
                line.formula = f"{n} × {rate} = {line.amount} ({old} → {rate})"
        else:  # the base stays; the difference is a line of its own
            n = sum(line.why["orders"] for line in lines)
            base = sum((line.amount for line in lines), ZERO)
            new = money(n * rate)
            why = {"orders": n, "rate": str(rate), "base": str(base)}
            _line(st, b, pos, "price_change", new - base, why, f"{n} × {rate} − {base} = {money(new - base)}")
        st.price_changed = True
        return None
    if t == "expense":
        info = {"kind": p["kind"], "responsibility": p["responsibility"]}
        if p.get("amount") and p.get("approved") and p["kind"] != "advance":
            amount = money(p["amount"])
            _line(st, b, pos, "expense_deduction", -amount, info, f"−{amount}")
            return None
        st.trace.append({"block": pos, "type": t, "info": "informational", **info})
        return None
    if t == "exception_days":
        if p["effect"] == "count_valid":
            days = _valid_extra(facts)
            if not days:
                return "no_exception"
            if st.values.get("valid_days") is not None:
                st.values["valid_days"] += days
            st.trace.append({"block": pos, "type": t, "info": "count_valid", "days": days})
            return None
        if not any(_excusing(facts, w) for w in ("star_day", "marks", "lateness", "absence")):
            return "no_exception"
        if _excuse(st.values, facts):
            st.invalid_by.discard("star_day")
        st.trace.append({"block": pos, "type": t, "info": "excuse_attendance"})
        return None
    raise AppError(422, "rule_block_unknown", position=pos, type=t)


def _start(facts: Facts) -> tuple[dict, list]:
    values = {k: getattr(facts, k) for k in (*BUILTIN_SOURCES, "star_day_failed")}
    values["fields"] = dict(facts.fields or {})
    for e in facts.exceptions:  # the company's data was wrong: the corrected figures replace it
        if e.kind == "company_error":
            for k, x in (e.corrections or {}).items():
                if k in values and k != "fields":
                    values[k] = x
                else:
                    values["fields"][k] = x
    batches = list(facts.batches or [])
    if not batches and facts.batch_level is not None:
        batches = [(facts.batch_level, int(values.get("orders") or 0))]
    return values, batches


def run(blocks: list[dict], facts: Facts, *, floor_at_zero: bool = True) -> Outcome:
    """The blocks in order, each once; then the floor (decision D)."""
    values, batches = _start(facts)
    st = _State(values=values, batches=batches)
    corrected = [e for e in facts.exceptions if e.kind == "company_error" and e.corrections]
    for e in corrected:
        st.trace.append({"block": None, "type": "exception", "info": "corrected", "fields": dict(e.corrections)})
    for pos, b in enumerate(blocks, start=1):
        group = b.get("group")
        if group and group in st.groups:
            st.trace.append({"block": pos, "type": b["type"], "skipped": "group_done", "by": st.groups[group]})
            continue
        v = _view(st, facts, b)
        if not all(_holds(c, v, st, facts) for c in b["condition"]):
            st.trace.append({"block": pos, "type": b["type"], "skipped": "condition_not_met"})
            continue
        before = len(st.lines)
        reason = _apply(st, facts, b, pos, v)
        if reason:
            st.trace.append({"block": pos, "type": b["type"], "skipped": reason})
            continue
        if group:
            st.groups[group] = pos
        st.trace.append({"block": pos, "type": b["type"], "applied": True, "lines": len(st.lines) - before})
    items = st.lines
    pay = sum((i.amount for i in items if i.amount > 0), ZERO)
    penalties = -sum((i.amount for i in items if i.amount < 0), ZERO)
    uncovered = ZERO
    if floor_at_zero and penalties > pay:
        uncovered, penalties = penalties - pay, pay
        items.append(Line("uncovered_penalty", money(uncovered), {"uncovered": str(money(uncovered))}, ""))
    return Outcome(items, money(pay), money(penalties), money(uncovered), st.trace, st.problems)
