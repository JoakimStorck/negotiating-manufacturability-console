"""What changed between two orders, item by item: the change record's lines and the comparison of two versions or two products.

Each change is {what, id, text}: `what` is one of metric, need, object, value, mandate, binding, group, tags, picture, title,
product, brief, heading, design; `id` the item it concerns.
"""
from __future__ import annotations

import json

from .order import Order, plain

METRIC_FIELDS = ("class", "heading", "text", "object", "quantity", "unit", "under", "needs", "source", "verified_by", "carried_by")


def value_text(value: dict | None, unit: str | None = None) -> str:
    """A metric's value in words: at most 0.6, 8 to 8.6 mm (nominal 8.3), holds: ..."""
    if not value:
        return "no value"
    u = f" {unit}" if unit and unit not in ("-", "1") else ""
    (form, v), = list(value.items())[:1]
    if form == "at_most":
        return f"at most {_n(v)}{u}"
    if form == "at_least":
        return f"at least {_n(v)}{u}"
    if form == "band":
        nominal = f" (nominal {_n(v['nominal'])})" if v.get("nominal") is not None else ""
        return f"{_n(v['lower'])} to {_n(v['upper'])}{u}{nominal}"
    if form == "equals":
        return f"equals {_n(v)}{u}"
    return f"holds: {v}"


def mandate_text(mandate: dict | None, unit: str | None = None) -> str:
    m = mandate or {"form": "held"}
    if m["form"] == "held":
        return "held"
    if m["form"] == "release":
        return "release"
    to = m.get("to")
    if to == "as_needed":
        return "interval, as needed"
    u = f" {unit}" if unit and unit not in ("-", "1") else ""
    if isinstance(to, dict):
        return f"interval to {_n(to['lower'])} to {_n(to['upper'])}{u}"
    return f"interval to {_n(to)}{u}"


def _n(v) -> str:
    if isinstance(v, list):
        return " x ".join(_n(x) for x in v)
    if isinstance(v, float):
        return f"{v:g}" if abs(v) >= 1e-4 or v == 0 else f"{v:.3g}"
    return str(v)


def _j(v) -> str:
    return json.dumps(plain(v), ensure_ascii=False, sort_keys=True)


def diff(a: Order | dict, b: Order | dict) -> list[dict]:
    """The changes from `a` to `b`."""
    a = a if isinstance(a, Order) else Order(a, validate=False)
    b = b if isinstance(b, Order) else Order(b, validate=False)
    out = []

    def add(what, item, text):
        out.append({"what": what, "id": item, "text": text})

    if a.data.get("title") != b.data.get("title"):
        add("title", "product", f"title: {a.data.get('title')!r} -> {b.data.get('title')!r}")
    pa, pb = a.data["product"], b.data["product"]
    for k in ("name", "purpose"):
        if pa.get(k) != pb.get(k):
            add("product", "product", f"product {k}: {pa.get(k)!r} -> {pb.get(k)!r}")
    if _j(pa.get("picture")) != _j(pb.get("picture")):
        add("picture", "product", f"picture: {_picture(pa.get('picture'))} -> {_picture(pb.get('picture'))}")
    if a.data.get("group") != b.data.get("group"):
        add("group", "product", f"group: {a.data.get('group')} -> {b.data.get('group')}")
    ta, tb = set(a.data.get("tags", [])), set(b.data.get("tags", []))
    if ta != tb:
        add("tags", "product", "tags: " + ", ".join([f"+{t}" for t in sorted(tb - ta)] + [f"-{t}" for t in sorted(ta - tb)]))
    if a.data.get("design") != b.data.get("design"):
        add("design", "product", f"design: {a.data.get('design')} -> {b.data.get('design')}")
    if _j(a.data.get("brief")) != _j(b.data.get("brief")):
        for k in sorted(set(a.data.get("brief") or {}) | set(b.data.get("brief") or {})):
            va, vb = (a.data.get("brief") or {}).get(k), (b.data.get("brief") or {}).get(k)
            if _j(va) != _j(vb):
                add("brief", "brief", f"brief {k}: {_j(va)} -> {_j(vb)}")
    ha, hb = a.data.get("headings") or {}, b.data.get("headings") or {}
    for k in sorted(set(ha) | set(hb)):
        if ha.get(k) != hb.get(k):
            add("heading", k, f"heading {k}: " + ("stated" if k not in ha else "statement withdrawn" if k not in hb else "statement changed"))

    for kind, la, lb in (("need", a.data["needs"], b.data["needs"]), ("object", a.data["objects"], b.data["objects"])):
        da, db = {x["id"]: x for x in la}, {x["id"]: x for x in lb}
        for i in db:
            if i not in da:
                add(kind, i, f"{kind} {i} added: {db[i].get('text') or db[i].get('name')!r}")
            elif db[i].get("dropped") and not da[i].get("dropped"):
                add(kind, i, f"{kind} {i} dropped")
            elif _j(da[i]) != _j(db[i]):
                keys = sorted(k for k in set(da[i]) | set(db[i]) if _j(da[i].get(k)) != _j(db[i].get(k)))
                add(kind, i, f"{kind} {i} changed: {', '.join(keys)}")
        for i in da:
            if i not in db:
                add(kind, i, f"{kind} {i} removed")

    ma, mb = {m["id"]: m for m in a.data["metrics"]}, {m["id"]: m for m in b.data["metrics"]}
    for i, m in mb.items():
        if i not in ma:
            add("metric", i, f"metric {i} added: {m.get('quantity')} {value_text(m.get('value'), m.get('unit'))}")
            continue
        o = ma[i]
        if m.get("dropped") and not o.get("dropped"):
            add("metric", i, f"metric {i} dropped")
            continue
        if _j(o.get("value")) != _j(m.get("value")):
            add("value", i, f"value {i}: {value_text(o.get('value'), o.get('unit'))} -> {value_text(m.get('value'), m.get('unit'))}")
        if _j(o.get("mandate") or {"form": "held"}) != _j(m.get("mandate") or {"form": "held"}):
            add("mandate", i, f"mandate {i}: {mandate_text(o.get('mandate'), o.get('unit'))} -> {mandate_text(m.get('mandate'), m.get('unit'))}")
        keys = [k for k in METRIC_FIELDS if _j(o.get(k)) != _j(m.get(k))]
        if keys:
            add("metric", i, f"metric {i} changed: {', '.join(keys)}")
    for i in ma:
        if i not in mb:
            add("metric", i, f"metric {i} removed")

    ba = {(x["object"], x["design"]): x for x in a.data.get("bindings", [])}
    bb = {(x["object"], x["design"]): x for x in b.data.get("bindings", [])}
    for key in sorted(set(ba) | set(bb)):
        xa, xb = ba.get(key), bb.get(key)
        if _j(xa) == _j(xb):
            continue
        fa = {f["name"]: f for f in (xa or {}).get("features", [])}
        fb = {f["name"]: f for f in (xb or {}).get("features", [])}
        parts = [f"+{n} ({f['how']}{', confirmed' if f['confirmed'] else ''})" for n, f in fb.items() if n not in fa]
        parts += [f"-{n}" for n in fa if n not in fb]
        parts += [f"{n} confirmed" for n, f in fb.items() if n in fa and f["confirmed"] and not fa[n]["confirmed"]]
        rej = set((xb or {}).get("rejected", [])) - set((xa or {}).get("rejected", []))
        parts += [f"{n} rejected" for n in sorted(rej)]
        add("binding", key[0], f"binding {key[0]} in {key[1]}: " + (", ".join(parts) or "changed"))
    return out


def _picture(p) -> str:
    if not p:
        return "none"
    if p["source"] == "design":
        return "the design's"
    return f"the owner's ({p['sha256'][:12]})"
