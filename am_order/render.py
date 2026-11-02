"""The tables of an order, in HTML and Markdown (the workbook in `export.py`):

- `requirements`: the requirements list (Pahl & Beitz): demands and wishes under the checklist's headings, each with its source;
- `needs`: the customer needs (Ulrich & Eppinger), with their importance, grouped under the primary needs;
- `metrics`: the metrics, each with its importance, the highest of its needs';
- `matrix`: the needs-metrics matrix;
- `specification`: the target specification, the ideal values, with the mandate only where asked;
- `traceability`: the chain need -> metric -> object -> feature, and how each metric is verified.

    text = render(order, "markdown")                      # every table
    html = render(order, "html", ["matrix"], mandate=True)
"""
from __future__ import annotations

import html as H

from . import vocab as V
from .diff import mandate_text, value_text
from .order import Order

TABLES = ("requirements", "needs", "metrics", "matrix", "specification", "traceability")
TITLES = {"requirements": "Requirements list", "needs": "Customer needs", "metrics": "Metrics", "matrix": "Needs-metrics matrix",
          "specification": "Target specification", "traceability": "Traceability"}


def _order(order) -> Order:
    return order if isinstance(order, Order) else Order(order, validate=False)


def _source(m: dict) -> str:
    return "; ".join(s["kind"] + (f": {s['ref']}" if s.get("ref") else "") for s in m.get("source", []))


def metric_name(order: Order, m: dict) -> str:
    o = order.obj(m.get("object"))
    q = (m.get("quantity") or "").replace("_", " ")
    under = m.get("under") or {}
    cond = f" under {under['name']}" if under.get("name") else f" under the {under['type']}" if under.get("type") else ""
    return f"{q} of the {o['name']}{cond}" if o else q


def _unit(m: dict) -> str:
    u = m.get("unit") or ""
    return "–" if u in ("-", "1") else u


def table(order, name: str, mandate: bool = False) -> tuple[list[str], list[list[str]]]:
    """The columns and rows of one table, as text."""
    order = _order(order)
    metrics = order.metrics()
    if name == "requirements":
        rows = []
        for h in V.headings():
            for m in [m for m in metrics if m.get("heading") == h["id"]]:
                rows.append([m["id"], "D" if m.get("class") == "demand" else "W", h["name"], m.get("text") or metric_name(order, m),
                             value_text(m.get("value"), m.get("unit")), _source(m)])
        stated = order.data.get("headings") or {}
        for h in V.headings():
            if stated.get(h["id"]) and not any(m.get("heading") == h["id"] for m in metrics):
                rows.append(["", "", h["name"], stated[h["id"]], "(the owner's statement)", "owner"])
        return ["#", "D/W", "Heading", "Requirement", "Value", "Source"], rows
    if name == "needs":
        rows = [[n["id"], n.get("group", ""), n["text"], str(n.get("importance") or "")] for n in
                sorted(order.needs(), key=lambda n: (n.get("group", ""), int(n["id"][1:])))]
        return ["#", "Primary need", "Need", "Importance"], rows
    if name == "metrics":
        rows = [[m["id"], ", ".join(m.get("needs", [])), metric_name(order, m), str(order.importance(m) or ""), _unit(m)] for m in metrics]
        return ["#", "Needs", "Metric", "Importance", "Unit"], rows
    if name == "matrix":
        cols = [m["id"] for m in metrics]
        rows = [[f"{n['id']} {n['text']}"] + ["•" if n["id"] in m.get("needs", []) else "" for m in metrics] for n in order.needs()]
        return ["Need"] + cols, rows
    if name == "specification":
        rows = []
        for m in metrics:
            row = [m["id"], metric_name(order, m), _unit(m), value_text(m.get("value"), None)]
            if mandate:
                row.append(mandate_text(order.mandate(m), None))
            rows.append(row)
        return ["#", "Metric", "Unit", "Ideal value"] + (["Mandate"] if mandate else []), rows
    if name == "traceability":
        rows = []
        design = order.data.get("design")
        for m in metrics:
            for oid in m.get("carried_by") or [m.get("object")]:
                o = order.obj(oid)
                if o is None:
                    continue
                feats = "the design" if o["kind"] == "part" and design else \
                    ", ".join(f["name"] + ("" if f["confirmed"] else " (unconfirmed)") for f in (order.binding(oid) or {}).get("features", []))
                rows.append([", ".join(m.get("needs", [])), m["id"], f"{oid} {o['name']}", feats or "unbound", m.get("verified_by") or ""])
        return ["Needs", "Metric", "Object", "Features" + (f" of {design}" if design else ""), "Verified by"], rows
    raise KeyError(f"no table {name!r}; one of {TABLES}")


def markdown_table(columns: list[str], rows: list[list[str]]) -> str:
    esc = lambda s: str(s).replace("|", "\\|").replace("\n", " ")
    out = ["| " + " | ".join(esc(c) for c in columns) + " |", "| " + " | ".join("---" for _ in columns) + " |"]
    out += ["| " + " | ".join(esc(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def html_table(columns: list[str], rows: list[list[str]], cls: str = "") -> str:
    head = "".join(f"<th>{H.escape(str(c))}</th>" for c in columns)
    body = "".join("<tr>" + "".join(f"<td>{H.escape(str(c))}</td>" for c in r) + "</tr>" for r in rows)
    return f'<table class="{cls}"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>'


def render(order, fmt: str = "markdown", tables=TABLES, mandate: bool = False) -> str:
    """The tables in Markdown or HTML, each under its title."""
    order = _order(order)
    parts = []
    for name in tables:
        cols, rows = table(order, name, mandate)
        if fmt == "markdown":
            parts.append(f"### {TITLES[name]}\n\n" + markdown_table(cols, rows))
        elif fmt == "html":
            parts.append(f"<h3>{TITLES[name]}</h3>\n" + html_table(cols, rows, name))
        else:
            raise ValueError(f"format {fmt!r}: markdown or html")
    return "\n\n".join(parts) + "\n"
