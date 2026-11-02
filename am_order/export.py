"""An order out and in: a workbook (xlsx), one sheet per table, round trip; and a ReqIF 1.2 export.

    export(order, "xlsx", path)          # the workbook
    order = import_xlsx(path)            # an edited workbook comes in as a draft, to be checked
    export(order, "reqif", path)         # the metrics as specification objects, the needs and the matrix as relations

The workbook's sheets: Product, Customer needs, Objects, Requirements list (every field of each metric, its value and its mandate
among them), Needs-metrics matrix (a tick per need and metric: the metrics' needs are read from it), Headings, Bindings; and,
regenerated on every export and not read back, Metrics, Target specification and Traceability. A workbook exported and imported
unchanged gives the same order.
"""
from __future__ import annotations

import io
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

from . import render as R
from . import vocab as V
from .order import Order, plain

READ_BACK = ("Product", "Customer needs", "Objects", "Requirements list", "Needs-metrics matrix", "Headings", "Bindings")
SHOWN = ("Metrics", "Target specification", "Traceability")
METRIC_COLUMNS = ["id", "class", "heading", "text", "object", "quantity", "unit", "comparator", "value", "lower", "nominal", "upper",
                  "under", "source", "verified_by", "carried_by", "mandate", "far end", "dropped"]


def _order(order) -> Order:
    return order if isinstance(order, Order) else Order(order, validate=False)


def _j(v) -> str | None:
    return None if v is None else json.dumps(v, ensure_ascii=False, sort_keys=True)


def _uj(v):
    return None if v in (None, "") else json.loads(v)


def _vec(v) -> str:
    return ", ".join(repr(float(x)) if isinstance(x, float) else str(x) for x in v)


def _unvec(text: str) -> list:
    return [float(x) if "." in x or "e" in x.lower() else int(x) for x in (t.strip() for t in str(text).split(","))]


def _list(v) -> str:
    return ", ".join(v or [])


def _unlist(v) -> list:
    return [x.strip() for x in str(v).split(",") if x.strip()] if v not in (None, "") else []


def export(order, fmt: str, path: Path | str | None = None) -> bytes:
    """The order as `xlsx` or `reqif`; written to `path` where given; returns the bytes."""
    order = _order(order)
    data = xlsx_bytes(order) if fmt == "xlsx" else reqif_bytes(order) if fmt == "reqif" else None
    if data is None:
        raise ValueError(f"format {fmt!r}: xlsx or reqif")
    if path is not None:
        Path(path).write_bytes(data)
    return data


# -------------------------------------------------------------------- the workbook

def xlsx_bytes(order: Order) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font

    d = order.data
    wb = Workbook()
    ws = wb.active
    ws.title = "Product"
    brief = d.get("brief") or {}
    rows = [("lineage", d["lineage"]), ("title", d.get("title")), ("name", d["product"].get("name")), ("purpose", d["product"].get("purpose")),
            ("picture", _j(d["product"].get("picture"))), ("parent", _j(d.get("parent"))), ("group", d.get("group")), ("tags", _j(d.get("tags"))),
            ("design", d.get("design")), ("brief text", brief.get("text")), ("brief objective", brief.get("objective")),
            ("brief quantity", brief.get("quantity")), ("brief may_change", _j(brief.get("may_change"))),
            ("brief may_relax", _j(brief.get("may_relax"))), ("revision", d.get("revision")), ("previous", d.get("previous")),
            ("saved", d.get("saved")), ("present", _j(sorted(d)))]
    ws.append(["field", "value"])
    for r in rows:
        ws.append(list(r))

    ws = wb.create_sheet("Customer needs")
    ws.append(["id", "group", "text", "importance", "dropped"])
    for n in d["needs"]:
        ws.append([n["id"], n.get("group"), n["text"], n.get("importance"), bool(n.get("dropped"))])

    ws = wb.create_sheet("Objects")
    ws.append(["id", "name", "kind", "count", "datum", "text", "place", "dropped"])
    for o in d["objects"]:
        ws.append([o["id"], o["name"], o["kind"], o.get("count"), o.get("datum"), o.get("text"), _j(o.get("place")), bool(o.get("dropped"))])

    ws = wb.create_sheet("Requirements list")
    ws.append(METRIC_COLUMNS)
    for m in d["metrics"]:
        value = m.get("value") or {}
        form = next(iter(value), None)
        v = value.get(form) if form else None
        lower = nominal = upper = None
        if form == "band":
            lower, nominal, upper, v = v.get("lower"), v.get("nominal"), v.get("upper"), None
        elif isinstance(v, list):
            v = _vec(v)
        mandate = m.get("mandate") or {"form": "held"}
        to = mandate.get("to")
        far = None if to is None else to if to == "as_needed" or isinstance(to, (int, float)) else _vec([to["lower"], to["upper"]]) \
            if isinstance(to, dict) else _vec(to)
        ws.append([m["id"], m.get("class"), m.get("heading"), m.get("text"), m.get("object"), m.get("quantity"), m.get("unit"), form, v,
                   lower, nominal, upper, _j(m.get("under")), _j(m.get("source")), m.get("verified_by"), _list(m.get("carried_by")),
                   mandate["form"], far, bool(m.get("dropped"))])
        if "mandate" not in m:
            ws.cell(ws.max_row, METRIC_COLUMNS.index("mandate") + 1).value = None

    ws = wb.create_sheet("Needs-metrics matrix")
    ws.append(["need"] + [m["id"] for m in d["metrics"]])
    for n in d["needs"]:
        ws.append([n["id"]] + ["x" if n["id"] in m.get("needs", []) else None for m in d["metrics"]])

    ws = wb.create_sheet("Headings")
    ws.append(["heading", "name", "statement"])
    for h in V.headings():
        ws.append([h["id"], h["name"], (d.get("headings") or {}).get(h["id"])])

    ws = wb.create_sheet("Bindings")
    ws.append(["object", "design", "feature", "how", "confirmed", "from", "rejected"])
    for b in d.get("bindings", []):
        for f in b["features"]:
            ws.append([b["object"], b["design"], f["name"], f["how"], f["confirmed"], f.get("from"), False])
        for name in b.get("rejected", []):
            ws.append([b["object"], b["design"], name, None, None, None, True])
        if not b["features"] and not b.get("rejected"):
            ws.append([b["object"], b["design"], None, None, None, None, None])

    for title, name in (("Metrics", "metrics"), ("Target specification", "specification"), ("Traceability", "traceability")):
        ws = wb.create_sheet(title)
        cols, rows = R.table(order, name, mandate=True)
        ws.append(cols)
        for r in rows:
            ws.append(r)
    ws = wb.create_sheet("About")
    ws.append([f"The order {d['lineage']}, written by am-order. The sheets {', '.join(READ_BACK)} are read back on import; "
               f"{', '.join(SHOWN)} are regenerated on every export. The matrix's ticks are the metrics' needs."])
    for sheet in wb.worksheets:
        for c in sheet[1]:
            c.font = Font(bold=True)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _rows(ws) -> list[dict]:
    it = ws.iter_rows(values_only=True)
    head = [h for h in next(it)]
    return [dict(zip(head, r)) for r in it if any(v is not None for v in r)]


def import_xlsx(source) -> Order:
    """An order from a workbook, as a draft: the form is validated; the checks are the home's on save."""
    from openpyxl import load_workbook

    wb = load_workbook(io.BytesIO(source) if isinstance(source, bytes) else source, data_only=True)
    p = {r["field"]: r["value"] for r in _rows(wb["Product"])}
    present = set(_uj(p.get("present")) or [])
    d = {"schema": "order/1", "lineage": p["lineage"], "title": p.get("title"),
         "product": {"name": p.get("name"), "purpose": p.get("purpose") or "", "picture": _uj(p.get("picture"))},
         "parent": _uj(p.get("parent")), "tags": _uj(p.get("tags")) or [], "design": p.get("design")}
    if p.get("group"):
        d["group"] = p["group"]
    brief = {"objective": p.get("brief objective"), "quantity": p.get("brief quantity"),
             "may_change": _uj(p.get("brief may_change")) or [], "may_relax": _uj(p.get("brief may_relax")) or []}
    if p.get("brief text") is not None:
        brief["text"] = p["brief text"]
    d["brief"] = brief
    for k in ("revision", "previous", "saved"):
        if p.get(k) is not None or k in present:
            d[k] = p.get(k)
    d["needs"] = []
    for r in _rows(wb["Customer needs"]):
        n = {"id": r["id"], "text": r["text"] or "", "importance": r["importance"], "group": r["group"] or ""}
        if r["dropped"]:
            n["dropped"] = True
        d["needs"].append(n)
    d["objects"] = []
    for r in _rows(wb["Objects"]):
        o = {"id": r["id"], "name": r["name"], "kind": r["kind"], "count": r["count"] if r["count"] is not None else 1,
             "datum": r["datum"], "text": r["text"] or ""}
        if r["place"]:
            o["place"] = _uj(r["place"])
        if r["dropped"]:
            o["dropped"] = True
        d["objects"].append(o)
    ticks: dict[str, list[str]] = {}
    matrix = list(wb["Needs-metrics matrix"].iter_rows(values_only=True))
    if matrix:
        cols = list(matrix[0][1:])
        for row in matrix[1:]:
            for mid, cell in zip(cols, row[1:]):
                if cell not in (None, ""):
                    ticks.setdefault(mid, []).append(row[0])
    d["metrics"] = []
    for r in _rows(wb["Requirements list"]):
        form = r["comparator"]
        if form == "band":
            band = {"lower": r["lower"], "upper": r["upper"]}
            if r["nominal"] is not None:
                band["nominal"] = r["nominal"]
            value = {"band": band}
        elif form:
            v = r["value"]
            if isinstance(v, str) and form in ("at_most",) and "," in v:
                v = _unvec(v)
            value = {form: v}
        else:
            value = None
        m = {"id": r["id"], "class": r["class"], "heading": r["heading"], "text": r["text"] or "", "object": r["object"],
             "quantity": r["quantity"], "unit": r["unit"], "under": _uj(r["under"]), "value": value, "needs": ticks.get(r["id"], []),
             "source": _uj(r["source"]) or [], "verified_by": r["verified_by"], "carried_by": _unlist(r["carried_by"])}
        if r["mandate"]:
            mandate = {"form": r["mandate"]}
            far = r["far end"]
            if far is not None:
                if far == "as_needed" or isinstance(far, (int, float)):
                    mandate["to"] = far
                else:
                    parts = _unvec(far)
                    mandate["to"] = {"lower": parts[0], "upper": parts[1]} if form in ("band", "equals") else parts
            m["mandate"] = mandate
        if r["dropped"]:
            m["dropped"] = True
        d["metrics"].append(m)
    d["headings"] = {r["heading"]: r["statement"] for r in _rows(wb["Headings"]) if r.get("statement")}
    bindings: dict[tuple, dict] = {}
    for r in _rows(wb["Bindings"]):
        b = bindings.setdefault((r["object"], r["design"]), {"object": r["object"], "design": r["design"], "features": [], "rejected": []})
        if r["feature"] is None:
            continue
        if r["rejected"]:
            b["rejected"].append(r["feature"])
        else:
            f = {"name": r["feature"], "how": r["how"], "confirmed": bool(r["confirmed"])}
            if r["from"]:
                f["from"] = r["from"]
            b["features"].append(f)
    d["bindings"] = list(bindings.values())
    if present:
        d = {k: v for k, v in d.items() if k in present or k in ("schema", "lineage", "product", "needs", "objects", "metrics")}
    return Order(plain(d))


# -------------------------------------------------------------------- ReqIF 1.2

NS = "http://www.omg.org/spec/ReqIF/20110401/reqif.xsd"
ATTRIBUTES = {"Metric": ["id", "class", "heading", "text", "object", "quantity", "unit", "value", "under", "source", "verified_by",
                         "carried_by", "mandate", "importance", "dropped"],
              "Need": ["id", "text", "importance", "group", "dropped"],
              "Object": ["id", "name", "kind", "count", "datum", "text", "place", "dropped"]}
RELATIONS = {"measures": ("Metric", "Need"), "concerns": ("Metric", "Object")}


def reqif_bytes(order: Order, now: str | None = None) -> bytes:
    """The order as ReqIF 1.2: the metrics, needs and objects as specification objects with their attributes as strings, the
    matrix as `measures` relations (metric to need) and each metric's object as a `concerns` relation; one specification, the
    requirements list, with the metrics under their headings."""
    d = order.data
    now = now or datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    ET.register_namespace("", NS)
    q = lambda tag: f"{{{NS}}}{tag}"
    ident = lambda *parts: "_" + "-".join([d["lineage"], *parts])
    root = ET.Element(q("REQ-IF"))
    header = ET.SubElement(ET.SubElement(root, q("THE-HEADER")), q("REQ-IF-HEADER"), {"IDENTIFIER": ident("header")})
    for tag, text in (("COMMENT", f"The order {d['lineage']}, revision {d.get('revision')}"), ("CREATION-TIME", now),
                      ("REQ-IF-TOOL-ID", "am-order"), ("REQ-IF-VERSION", "1.0"), ("SOURCE-TOOL-ID", "am-order"),
                      ("TITLE", d.get("title") or d["lineage"])):
        ET.SubElement(header, q(tag)).text = text
    content = ET.SubElement(ET.SubElement(root, q("CORE-CONTENT")), q("REQ-IF-CONTENT"))
    datatypes = ET.SubElement(content, q("DATATYPES"))
    ET.SubElement(datatypes, q("DATATYPE-DEFINITION-STRING"), {"IDENTIFIER": ident("string"), "LAST-CHANGE": now, "LONG-NAME": "text",
                                                               "MAX-LENGTH": "100000"})
    spec_types = ET.SubElement(content, q("SPEC-TYPES"))
    for kind, attrs in ATTRIBUTES.items():
        t = ET.SubElement(spec_types, q("SPEC-OBJECT-TYPE"), {"IDENTIFIER": ident("type", kind), "LAST-CHANGE": now, "LONG-NAME": kind})
        sa = ET.SubElement(t, q("SPEC-ATTRIBUTES"))
        for a in attrs:
            ad = ET.SubElement(sa, q("ATTRIBUTE-DEFINITION-STRING"), {"IDENTIFIER": ident("attr", kind, a), "LAST-CHANGE": now, "LONG-NAME": a})
            ET.SubElement(ET.SubElement(ad, q("TYPE")), q("DATATYPE-DEFINITION-STRING-REF")).text = ident("string")
    for rel in RELATIONS:
        ET.SubElement(spec_types, q("SPEC-RELATION-TYPE"), {"IDENTIFIER": ident("type", rel), "LAST-CHANGE": now, "LONG-NAME": rel})
    ET.SubElement(spec_types, q("SPECIFICATION-TYPE"), {"IDENTIFIER": ident("type", "list"), "LAST-CHANGE": now,
                                                        "LONG-NAME": "Requirements list"})
    objects = ET.SubElement(content, q("SPEC-OBJECTS"))

    def spec_object(kind: str, item: dict, extra: dict | None = None):
        so = ET.SubElement(objects, q("SPEC-OBJECT"), {"IDENTIFIER": ident(item["id"]), "LAST-CHANGE": now, "LONG-NAME": item["id"]})
        values = ET.SubElement(so, q("VALUES"))
        merged = {**item, **(extra or {})}
        for a in ATTRIBUTES[kind]:
            v = merged.get(a)
            if v is None:
                continue
            text = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False, sort_keys=True)
            av = ET.SubElement(values, q("ATTRIBUTE-VALUE-STRING"), {"THE-VALUE": text})
            ET.SubElement(ET.SubElement(av, q("DEFINITION")), q("ATTRIBUTE-DEFINITION-STRING-REF")).text = ident("attr", kind, a)
        ET.SubElement(ET.SubElement(so, q("TYPE")), q("SPEC-OBJECT-TYPE-REF")).text = ident("type", kind)

    for m in d["metrics"]:
        spec_object("Metric", m, {"importance": order.importance(m), "mandate": m.get("mandate") or {"form": "held"}})
    for n in d["needs"]:
        spec_object("Need", n)
    for o in d["objects"]:
        spec_object("Object", o)
    relations = ET.SubElement(content, q("SPEC-RELATIONS"))
    pairs = [("measures", m["id"], n) for m in d["metrics"] for n in m.get("needs", [])]
    pairs += [("concerns", m["id"], m["object"]) for m in d["metrics"] if m.get("object") and order.obj(m["object"])]
    for rel, src, tgt in pairs:
        r = ET.SubElement(relations, q("SPEC-RELATION"), {"IDENTIFIER": ident(rel, src, tgt), "LAST-CHANGE": now, "LONG-NAME": rel})
        ET.SubElement(ET.SubElement(r, q("SOURCE")), q("SPEC-OBJECT-REF")).text = ident(src)
        ET.SubElement(ET.SubElement(r, q("TARGET")), q("SPEC-OBJECT-REF")).text = ident(tgt)
        ET.SubElement(ET.SubElement(r, q("TYPE")), q("SPEC-RELATION-TYPE-REF")).text = ident("type", rel)
    specs = ET.SubElement(content, q("SPECIFICATIONS"))
    spec = ET.SubElement(specs, q("SPECIFICATION"), {"IDENTIFIER": ident("list"), "LAST-CHANGE": now, "LONG-NAME": "Requirements list"})
    ET.SubElement(ET.SubElement(spec, q("TYPE")), q("SPECIFICATION-TYPE-REF")).text = ident("type", "list")
    children = ET.SubElement(spec, q("CHILDREN"))
    for m in d["metrics"]:
        h = ET.SubElement(children, q("SPEC-HIERARCHY"), {"IDENTIFIER": ident("h", m["id"]), "LAST-CHANGE": now,
                                                           "LONG-NAME": V.heading_name(m.get("heading"))})
        ET.SubElement(ET.SubElement(h, q("OBJECT")), q("SPEC-OBJECT-REF")).text = ident(m["id"])
    ET.indent(root)
    return b'<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="utf-8")


def read_reqif(data: bytes) -> dict:
    """A ReqIF file parsed back: {objects: {kind: [{id, attributes}]}, relations: [(type, source id, target id)]}."""
    root = ET.fromstring(data)
    q = lambda tag: f"{{{NS}}}{tag}"
    types = {t.get("IDENTIFIER"): t.get("LONG-NAME") for t in root.iter(q("SPEC-OBJECT-TYPE"))}
    rtypes = {t.get("IDENTIFIER"): t.get("LONG-NAME") for t in root.iter(q("SPEC-RELATION-TYPE"))}
    attrs = {a.get("IDENTIFIER"): a.get("LONG-NAME") for a in root.iter(q("ATTRIBUTE-DEFINITION-STRING"))}
    ids = {}
    out = {"objects": {}, "relations": []}
    for so in root.iter(q("SPEC-OBJECT")):
        kind = types[so.find(f"{q('TYPE')}/{q('SPEC-OBJECT-TYPE-REF')}").text]
        values = {attrs[av.find(f"{q('DEFINITION')}/{q('ATTRIBUTE-DEFINITION-STRING-REF')}").text]: av.get("THE-VALUE")
                  for av in so.iter(q("ATTRIBUTE-VALUE-STRING"))}
        ids[so.get("IDENTIFIER")] = values.get("id")
        out["objects"].setdefault(kind, []).append({"id": values.get("id"), "attributes": values})
    for r in root.iter(q("SPEC-RELATION")):
        out["relations"].append((rtypes[r.find(f"{q('TYPE')}/{q('SPEC-RELATION-TYPE-REF')}").text],
                                 ids[r.find(f"{q('SOURCE')}/{q('SPEC-OBJECT-REF')}").text], ids[r.find(f"{q('TARGET')}/{q('SPEC-OBJECT-REF')}").text]))
    return out
