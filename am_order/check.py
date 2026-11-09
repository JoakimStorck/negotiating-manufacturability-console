"""The checks: each requirement as stated against the qualities of ISO/IEC/IEEE 29148, and the list against Pahl & Beitz's
checklist, the needs-metrics matrix, the objects' places and the binding.

    refusals = check(order, features=None, previous=None)

Each refusal names its rule and what it concerns (a metric, a need, an object or a heading) and says in the owner's words what
to fix. A save is refused while any check fails; the draft is kept.

| Rule | What it asks |
| --- | --- |
| singular | one quantity and one value per metric |
| unambiguous | a unit the quantity admits, a value its comparator admits, the class given |
| verifiable | every demand names how it is verified |
| necessary | every metric cites a need, or a source other than the requester |
| covered | every need is measured by a metric that is not dropped |
| traceable | a save keeps every id of the version before; every demand not dropped is carried by an object |
| consistent | an interval on the relaxed side of the ideal; a `holds` metric held or released; a wish released; no two metrics alike |
| complete | every checklist heading has a metric or the owner's statement that nothing applies |
| named | every object, need and load object a metric names exists and is not dropped |
| placed | a placed object within the envelope; a hole or slot clear of a wall; as many places as the count |
| bound | with a design named, every object a carried metric names bound to as many features as its count |
| delegated | the order's mandates each on a metric of the type that stands; the answering policy stated; a free part with a design bound |

The rules read the type's requirements and, for the mandates, the order's (`order.mandate`).
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass

from . import vocab as V
from .order import Order

RULES = ("singular", "unambiguous", "verifiable", "necessary", "covered", "traceable", "consistent", "complete", "named", "placed",
         "bound", "delegated")
TOLERANCE = 1e-6


@dataclass(frozen=True)
class Refusal:
    rule: str
    item: str                 # a metric, need or object id, a heading id, or the product
    text: str

    def to_dict(self) -> dict:
        return asdict(self)

    def __str__(self) -> str:
        return f"{self.rule} ({self.item}): {self.text}"


def _order(order) -> Order:
    return order if isinstance(order, Order) else Order(order, validate=False)


def describe(order: Order, m: dict) -> str:
    """A metric in words: its id, its quantity and its object."""
    o = order.obj(m.get("object"))
    q = m.get("quantity") or "no quantity"
    return f"{m['id']} ({q.replace('_', ' ')}{' of the ' + o['name'] if o else ''})"


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


# -------------------------------------------------------------------- the rules, one function each

def singular(order: Order, **_) -> list[Refusal]:
    out = []
    for m in order.metrics():
        d = describe(order, m)
        if not m.get("quantity"):
            out.append(Refusal("singular", m["id"], f"{d} states no quantity: choose the one quantity it measures."))
        value = m.get("value") or {}
        if not value:
            out.append(Refusal("singular", m["id"], f"{d} states no value: give the one value the part must meet."))
        elif len(value) > 1:
            out.append(Refusal("singular", m["id"], f"{d} states {len(value)} values ({', '.join(sorted(value))}): keep one, "
                                                    "and state the other as a metric of its own."))
    return out


def unambiguous(order: Order, **_) -> list[Refusal]:
    out = []
    for m in order.metrics():
        d, q = describe(order, m), V.quantity(m.get("quantity"))
        if m.get("class") not in V.CLASSES:
            out.append(Refusal("unambiguous", m["id"], f"{d} is neither a demand nor a wish: say which it is."))
        if m.get("quantity") and q is None:
            out.append(Refusal("unambiguous", m["id"], f"{d}: the quantity {m['quantity']!r} is not one the tool knows; choose one of "
                                                       f"{', '.join(sorted(V.quantities()))}."))
            continue
        if q is None:
            continue
        if not m.get("unit"):
            out.append(Refusal("unambiguous", m["id"], f"{d} has no unit: give its unit, {_one_of(q['units'])}."))
        elif m["unit"] not in q["units"]:
            out.append(Refusal("unambiguous", m["id"], f"{d} is in {m['unit']!r}, which a {m['quantity'].replace('_', ' ')} is not measured in: "
                                                       f"use {_one_of(q['units'])}."))
        value = m.get("value") or {}
        if len(value) == 1:
            (form, v), = value.items()
            if form not in q["values"]:
                out.append(Refusal("unambiguous", m["id"], f"{d} is stated as {form.replace('_', ' ')}, which a "
                                                           f"{m['quantity'].replace('_', ' ')} does not take: state it as {_one_of(q['values'], 'or')}."))
            else:
                why = _value_problem(form, v, q)
                if why:
                    out.append(Refusal("unambiguous", m["id"], f"{d}: {why}"))
        out += _under_problems(order, m, d)
    return out


def _one_of(items, word: str = "or") -> str:
    items = [str(i).replace("_", " ") for i in items]
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + f" {word} " + items[-1]


def _value_problem(form: str, v, q: dict) -> str | None:
    dims = q.get("dims", 1)
    if form in ("at_most", "at_least"):
        if dims == 3:
            if not (isinstance(v, list) and len(v) == 3 and all(_num(x) and x > 0 for x in v)):
                return "give the three sizes, length, width and height, each above zero."
        elif not _num(v):
            return f"give one number for {form.replace('_', ' ')}."
    elif form == "band":
        lo, hi, nom = v.get("lower"), v.get("upper"), v.get("nominal")
        if not (_num(lo) and _num(hi)) or lo >= hi:
            return "give the band's lower end below its upper end."
        if nom is not None and not lo <= nom <= hi:
            return f"the nominal {nom:g} lies outside the band {lo:g} to {hi:g}: put it within."
    elif form == "equals":
        if q["units"] == ["-"]:
            if not isinstance(v, str) or not v.strip():
                return "name what it must be, in words."
        elif not _num(v):
            return "give the number it must equal."
    elif form == "holds":
        if not isinstance(v, str) or not v.strip():
            return "say in words what must hold."
    return None


def _under_problems(order: Order, m: dict, d: str) -> list[Refusal]:
    u = m.get("under") or {}
    if not u.get("type"):
        return []
    out = []
    units = V.loads().get(u["type"], {}).get("units", [])
    if not _num(u.get("magnitude")) or u["magnitude"] <= 0:
        out.append(Refusal("unambiguous", m["id"], f"{d}: the {u['type']} it is measured under has no magnitude: give it, above zero."))
    if u.get("unit") not in units:
        out.append(Refusal("unambiguous", m["id"], f"{d}: the {u['type']} is in {u.get('unit')!r}: use {_one_of(units)}."))
    if u["type"] in ("force", "torque"):
        dv = u.get("direction")
        if not dv or not any(abs(x) > 0 for x in dv):
            out.append(Refusal("unambiguous", m["id"], f"{d}: the {u['type']} has no direction: give it as x, y, z in the part's coordinates."))
    if not u.get("at"):
        out.append(Refusal("unambiguous", m["id"], f"{d}: say at which object the {u['type']} acts."))
    if not u.get("held_by"):
        out.append(Refusal("unambiguous", m["id"], f"{d}: say which object holds the part while the {u['type']} acts."))
    return out


def verifiable(order: Order, **_) -> list[Refusal]:
    return [Refusal("verifiable", m["id"], f"{describe(order, m)} is a demand but says nothing of how it is verified: name the "
                                           "measurement or the test (a gauge, a load test, the record).")
            for m in order.metrics() if m.get("class") == "demand" and not (m.get("verified_by") or "").strip()]


def necessary(order: Order, **_) -> list[Refusal]:
    out = []
    for m in order.metrics():
        if m.get("needs"):
            continue
        others = [s for s in m.get("source", []) if s["kind"] != "requester"]
        if not others:
            out.append(Refusal("necessary", m["id"], f"{describe(order, m)} cites no need and no source but the requester: say which need "
                                                     "it measures, or the standard, project or reference that asks for it."))
    return out


def covered(order: Order, **_) -> list[Refusal]:
    measured = {n for m in order.metrics() for n in m.get("needs", [])}
    return [Refusal("covered", n["id"], f"Need {n['id']} ({n['text']!r}) is measured by no metric: tick it in the matrix against the "
                                        "metric that measures it, add a metric, or drop the need.")
            for n in order.needs() if n["id"] not in measured]


def traceable(order: Order, previous: Order | None = None, **_) -> list[Refusal]:
    out = []
    if previous is not None:
        for kind, items, now in (("need", previous.type["needs"], order.need), ("object", previous.type["objects"], order.obj),
                                 ("metric", previous.type["metrics"], order.metric)):
            for item in items:
                if now(item["id"]) is None:
                    out.append(Refusal("traceable", item["id"], f"The {kind} {item['id']} of the version before is gone: an id is kept; "
                                                                f"mark it dropped instead of removing it."))
    for m in order.metrics():
        if m.get("class") == "demand" and not m.get("carried_by"):
            out.append(Refusal("traceable", m["id"], f"{describe(order, m)} is carried by no object: say which objects of the part carry it."))
    return out


def consistent(order: Order, **_) -> list[Refusal]:
    out = []
    seen = {}
    for m in order.metrics():
        d, mandate = describe(order, m), order.mandate(m)
        value = m.get("value") or {}
        form = next(iter(value), None) if len(value) == 1 else None
        if m.get("class") == "wish" and mandate["form"] != "release":
            out.append(Refusal("consistent", m["id"], f"{d} is a wish, which the requester may always give up: set its mandate to release."))
        if form == "holds" and mandate["form"] == "interval":
            out.append(Refusal("consistent", m["id"], f"{d} either holds or it does not, so it has no interval: hold it or release it."))
        elif mandate["form"] == "interval" and form is not None:
            why = _interval_problem(form, value[form], mandate.get("to"))
            if why:
                out.append(Refusal("consistent", m["id"], f"{d}: {why}"))
        if m.get("quantity") and m.get("object"):
            key = (m["quantity"], m["object"], _frozen(m.get("under")))
            if key in seen:
                out.append(Refusal("consistent", m["id"], f"{d} states the same quantity on the same object under the same conditions as "
                                                          f"{seen[key]}: keep one of them, or state the conditions that tell them apart."))
            else:
                seen[key] = m["id"]
    return out


def _frozen(v):
    if isinstance(v, dict):
        return tuple(sorted((k, _frozen(x)) for k, x in v.items() if k not in ("name", "text")))
    if isinstance(v, list):
        return tuple(_frozen(x) for x in v)
    return v


def _interval_problem(form: str, v, to) -> str | None:
    if to is None:
        return "the interval has no far end: give the marginal value, or as needed."
    if to == "as_needed":
        return None if form in ("at_most", "at_least") else "only a limit on one side (at most, at least) can be relaxed as needed."
    if form == "at_most":
        if isinstance(v, list):
            if not (isinstance(to, list) and len(to) == 3 and all(_num(t) and t >= x for t, x in zip(to, v)) and to != v):
                return "the far end must be at least the ideal in every size, and beyond it in one."
        elif not (_num(to) and to > v):
            return f"the ideal is at most {v:g}, so the far end lies above it; {to} does not."
    elif form == "at_least":
        if not (_num(to) and to < v):
            return f"the ideal is at least {v:g}, so the far end lies below it; {to} does not."
    elif form == "band":
        if not (isinstance(to, dict) and _num(to.get("lower")) and _num(to.get("upper")) and to["lower"] <= v["lower"] and to["upper"] >= v["upper"]
                and (to["lower"], to["upper"]) != (v["lower"], v["upper"])):
            return f"the far end is a wider band around the ideal {v['lower']:g} to {v['upper']:g}."
    elif form == "equals":
        if not (isinstance(to, dict) and _num(v) and to.get("lower", math.inf) <= v <= to.get("upper", -math.inf)):
            return "the far end of an exact value is a band around it."
    return None


def complete(order: Order, **_) -> list[Refusal]:
    used = {m.get("heading") for m in order.metrics()}
    stated = {k for k, v in (order.type.get("headings") or {}).items() if (v or "").strip()}
    out = []
    for h in V.headings():
        if h["id"] not in used and h["id"] not in stated:
            out.append(Refusal("complete", h["id"], f"The heading {h['name']} ({h['covers']}) has no metric: add one, or state that nothing "
                                                    "under it applies to the product."))
    for m in order.metrics():
        if m.get("heading") not in V.heading_ids():
            out.append(Refusal("complete", m["id"], f"{describe(order, m)} stands under no heading of the checklist: choose its heading."))
    return out


def named(order: Order, **_) -> list[Refusal]:
    out = []
    for m in order.metrics():
        d = describe(order, m)
        if not m.get("object"):
            out.append(Refusal("named", m["id"], f"{d} names no object: choose the object of the part it is measured on."))
        for oid in order.objects_named(m):
            o = order.obj(oid)
            if o is None:
                out.append(Refusal("named", m["id"], f"{d} names the object {oid}, which the product does not have: choose one of its objects."))
            elif o.get("dropped"):
                out.append(Refusal("named", m["id"], f"{d} names {oid} ({o['name']}), which is dropped: choose an object that stands."))
        for nid in m.get("needs", []):
            n = order.need(nid)
            if n is None:
                out.append(Refusal("named", m["id"], f"{d} cites the need {nid}, which the product does not have."))
            elif n.get("dropped"):
                out.append(Refusal("named", m["id"], f"{d} cites {nid} ({n['text']!r}), which is dropped: untick it in the matrix."))
    return out


def placed(order: Order, **_) -> list[Refusal]:
    out = []
    env = _envelope_box(order)
    placed_objects = [o for o in order.objects() if order.place(o)]
    for o in placed_objects:
        regions = order.place(o)
        if len(regions) != o.get("count", 1):
            out.append(Refusal("placed", o["id"], f"The object {o['id']} ({o['name']}) has {o.get('count', 1)} instances and "
                                                  f"{len(regions)} places: give one place per instance, or correct the count."))
        if env is not None and o["kind"] != "part":
            for i, r in enumerate(regions, 1):
                lo, hi = region_bounds(r)
                if any(lo[k] < env[0][k] - TOLERANCE or hi[k] > env[1][k] + TOLERANCE for k in range(3)):
                    out.append(Refusal("placed", o["id"], f"The object {o['id']} ({o['name']}){_nth(i, regions)} reaches outside the envelope "
                                                          f"{_box_text(env)}: move it within, or widen the envelope."))
    voids = [o for o in placed_objects if o["kind"] in V.VOID_KINDS]
    solids = [o for o in placed_objects if o["kind"] in V.SOLID_KINDS]
    for v in voids:
        for s in solids:
            if any(regions_overlap(a, b) for a in order.place(v) for b in order.place(s)):
                out.append(Refusal("placed", v["id"], f"The {v['kind']} {v['id']} ({v['name']}) cuts into the {s['kind']} {s['id']} "
                                                      f"({s['name']}), which must be material: move one of them."))
    return out


def _nth(i: int, regions: list) -> str:
    return f", instance {i}," if len(regions) > 1 else ""


def _box_text(box) -> str:
    lo, hi = box
    return "from (" + ", ".join(f"{x:g}" for x in lo) + ") to (" + ", ".join(f"{x:g}" for x in hi) + ") mm"


def _envelope_box(order: Order):
    part = order.part()
    if part is not None and order.place(part):
        r = order.place(part)[0]
        if "box" in r:
            return list(r["box"]["min"]), list(r["box"]["max"])
    env = order.envelope()
    if env is None:
        return None
    size = (env.get("value") or {}).get("at_most")
    if isinstance(size, list) and len(size) == 3:
        return [0.0, 0.0, 0.0], list(size)
    return None


def bound(order: Order, features: dict | None = None, **_) -> list[Refusal]:
    design = order.type.get("design")
    if not design:
        return []
    if features is None:
        return [Refusal("bound", "product", f"The order names the design {design}, whose feature list is not in the products home: "
                                            "add the feature list, or name another design.")]
    names = {f["name"] for f in features["features"] if f["status"] != "rejected"}
    out = []
    needed = {}
    for m in order.metrics():
        if m.get("carried_by"):
            for oid in order.objects_named(m):
                needed.setdefault(oid, m["id"])
    for oid, mid in needed.items():
        o = order.obj(oid)
        if o is None or o.get("dropped") or o["kind"] == "part":
            continue
        bound_to = order.features_of(oid, design)
        missing = [f for f in bound_to if f not in names]
        if missing:
            out.append(Refusal("bound", oid, f"The object {oid} ({o['name']}) is bound to {', '.join(missing)}, which {design} does not have: "
                                             "bind it again."))
        if len(bound_to) != o.get("count", 1):
            out.append(Refusal("bound", oid, f"The object {oid} ({o['name']}), which {mid} names, is bound to {len(bound_to)} of its "
                                             f"{o.get('count', 1)} features in {design}: confirm a proposal or choose the features."))
    return out


def delegated(order: Order, **_) -> list[Refusal]:
    """What the order delegates: every mandate on a metric of the type that stands, the answering policy stated, and a free part
    only with a design bound, since the shape is a design's to change."""
    out = []
    for mid in order.mandates():
        m = order.metric(mid)
        if m is None:
            out.append(Refusal("delegated", mid, f"The order gives a mandate on {mid}, which the product does not have: remove the mandate, "
                                                 "or give it on one of the product's metrics."))
        elif m.get("dropped"):
            out.append(Refusal("delegated", mid, f"The order gives a mandate on {describe(order, m)}, which is dropped: remove the mandate."))
    if order.answering() not in ("park", "decline"):
        out.append(Refusal("delegated", "order", "The order does not say what happens to a case its mandates do not cover: choose park "
                                                 "(it waits for your word) or decline (the requester declines on the evidence)."))
    part = order.part()
    if part is not None and order.change(part) == "free" and not order.type.get("design"):
        out.append(Refusal("delegated", part["id"], f"The part {part['id']} ({part['name']}) is free, so its shape may change, and no design "
                                                    "is bound: bind a design version, or make the part fixed."))
    return out


CHECKS = {"singular": singular, "unambiguous": unambiguous, "verifiable": verifiable, "necessary": necessary, "covered": covered,
          "traceable": traceable, "consistent": consistent, "complete": complete, "named": named, "placed": placed, "bound": bound,
          "delegated": delegated}


def check(order, features: dict | None = None, previous=None, rules=RULES) -> list[Refusal]:
    """Every refusal of the checks, in the order of the rules."""
    o = _order(order)
    prev = _order(previous) if previous is not None else None
    out = []
    for rule in rules:
        out += CHECKS[rule](o, features=features, previous=prev)
    return out


# -------------------------------------------------------------------- regions: bounds, containment, overlap

def _unit(v):
    n = math.sqrt(sum(x * x for x in v))
    return [x / n for x in v] if n > 0 else [0.0, 0.0, 1.0]


def region_bounds(region: dict):
    if "box" in region:
        return list(region["box"]["min"]), list(region["box"]["max"])
    c = region["cylinder"]
    d, p, r, L = _unit(c["direction"]), c["point"], c["radius"], c["length"]
    q = [p[k] + d[k] * L for k in range(3)]
    ext = [r * math.sqrt(max(0.0, 1 - d[k] ** 2)) for k in range(3)]
    return [min(p[k], q[k]) - ext[k] for k in range(3)], [max(p[k], q[k]) + ext[k] for k in range(3)]


def contains(region: dict, x) -> bool:
    if "box" in region:
        lo, hi = region["box"]["min"], region["box"]["max"]
        return all(lo[k] - TOLERANCE <= x[k] <= hi[k] + TOLERANCE for k in range(3))
    c = region["cylinder"]
    d = _unit(c["direction"])
    v = [x[k] - c["point"][k] for k in range(3)]
    t = sum(v[k] * d[k] for k in range(3))
    if t < -TOLERANCE or t > c["length"] + TOLERANCE:
        return False
    radial = [v[k] - t * d[k] for k in range(3)]
    return math.sqrt(sum(r * r for r in radial)) <= c["radius"] + TOLERANCE


def regions_overlap(a: dict, b: dict, n: int = 12) -> bool:
    """Whether two regions share volume: a grid of points inside the intersection of their bounds, tested in both."""
    alo, ahi = region_bounds(a)
    blo, bhi = region_bounds(b)
    lo = [max(alo[k], blo[k]) for k in range(3)]
    hi = [min(ahi[k], bhi[k]) for k in range(3)]
    if any(hi[k] - lo[k] <= 1e-3 for k in range(3)):
        return False
    for i in range(n):
        for j in range(n):
            for k in range(n):
                x = [lo[0] + (i + 0.5) * (hi[0] - lo[0]) / n, lo[1] + (j + 0.5) * (hi[1] - lo[1]) / n, lo[2] + (k + 0.5) * (hi[2] - lo[2]) / n]
                if contains(a, x) and contains(b, x):
                    return True
    return False
