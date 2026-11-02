"""The order: a product's needs, objects and metrics, its brief and its bindings (`schemas/order-1.json`).

    order = Order.new("bracket", name="Engine bracket")
    n = order.add_need("Carries the handling loads", importance=5, group="Strength")
    o = order.add_object("pin hole", "hole")
    m = order.add_metric(heading="geometry", object=o, quantity="diameter", unit="mm",
                         value={"band": {"nominal": 8.3, "lower": 8.0, "upper": 8.6}}, needs=[n])

An id is never reused: a need, an object or a metric is dropped by marking it, never removed. The chain is need -> metric ->
object -> feature; the needs-metrics matrix is read from the metrics' `needs`.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re

from . import schema as S

SET_BY_HOME = ("revision", "previous", "saved")


def plain(value):
    """A document with every whole float written as an integer, so that 108.0 and 108 are one value wherever it comes from (a
    workbook, a form, a script)."""
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, dict):
        return {k: plain(v) for k, v in value.items()}
    if isinstance(value, list):
        return [plain(v) for v in value]
    return value


def canonical(data: dict) -> bytes:
    """The bytes an order is hashed and stored as."""
    return (json.dumps(plain(data), indent=1, sort_keys=True, ensure_ascii=False) + "\n").encode()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def slug(text: str) -> str:
    """A name in the form a design's feature names take: lowercase words joined by hyphens."""
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s or "object"


class Order:
    """An order as a document with the helpers the interfaces share. `data` is the document itself."""

    def __init__(self, data: dict, validate: bool = True):
        self.data = data
        if validate:
            S.validate_order(data)

    # ------------------------------------------------------------------ making

    @classmethod
    def new(cls, lineage: str, name: str | None = None, purpose: str = "", group: str | None = None) -> "Order":
        data = {"schema": "order/1", "lineage": lineage, "title": name or lineage,
                "product": {"name": name or lineage, "purpose": purpose, "picture": None},
                "parent": None, "tags": [], "design": None, "needs": [], "objects": [], "metrics": [],
                "headings": {}, "brief": {"objective": None, "quantity": None, "may_change": [], "may_relax": []}, "bindings": []}
        if group:
            data["group"] = group
        return cls(data)

    def copy(self) -> "Order":
        return Order(copy.deepcopy(self.data), validate=False)

    @property
    def lineage(self) -> str:
        return self.data["lineage"]

    def content(self) -> dict:
        """The order without what the home sets on save: what tells two versions apart."""
        return {k: v for k, v in self.data.items() if k not in SET_BY_HOME}

    def content_hash(self) -> str:
        return sha256(canonical(self.content()))

    # ------------------------------------------------------------------ lookups

    def need(self, nid: str) -> dict | None:
        return next((n for n in self.data["needs"] if n["id"] == nid), None)

    def obj(self, oid: str | None) -> dict | None:
        return next((o for o in self.data["objects"] if o["id"] == oid), None)

    def metric(self, mid: str) -> dict | None:
        return next((m for m in self.data["metrics"] if m["id"] == mid), None)

    def needs(self, dropped: bool = False) -> list[dict]:
        return [n for n in self.data["needs"] if dropped or not n.get("dropped")]

    def objects(self, dropped: bool = False) -> list[dict]:
        return [o for o in self.data["objects"] if dropped or not o.get("dropped")]

    def metrics(self, dropped: bool = False) -> list[dict]:
        return [m for m in self.data["metrics"] if dropped or not m.get("dropped")]

    def part(self) -> dict | None:
        """The object that is the part as a whole."""
        return next((o for o in self.objects() if o["kind"] == "part"), None)

    def envelope(self) -> dict | None:
        """The size metric on the part: quantity `envelope`."""
        part = self.part()
        return next((m for m in self.metrics() if m.get("quantity") == "envelope" and (part is None or m.get("object") == part["id"])), None)

    def by_name(self, name: str) -> dict | None:
        return next((o for o in self.objects() if o["name"] == name), None)

    def importance(self, metric: dict) -> int | None:
        """A metric's importance: the highest of its needs'."""
        values = [n.get("importance") for n in (self.need(x) for x in metric.get("needs", [])) if n and n.get("importance")]
        return max(values) if values else None

    def mandate(self, metric: dict) -> dict:
        return metric.get("mandate") or {"form": "held"}

    def objects_named(self, metric: dict) -> list[str]:
        """The objects a metric names: its object, where its load acts and what holds the part, its datums, what carries it."""
        out = [metric.get("object")]
        u = metric.get("under") or {}
        out += [u.get("at")] + list(u.get("held_by") or []) + list(u.get("datums") or [])
        out += list(metric.get("carried_by") or [])
        return [o for o in dict.fromkeys(out) if o]

    def binding(self, oid: str, design: str | None = None) -> dict | None:
        design = design or self.data.get("design")
        return next((b for b in self.data.get("bindings", []) if b["object"] == oid and b["design"] == design), None)

    def features_of(self, oid: str, design: str | None = None) -> list[str]:
        b = self.binding(oid, design)
        return [f["name"] for f in b["features"]] if b else []

    def place(self, obj: dict) -> list[dict]:
        """An object's places as a list of regions (empty when it is not placed)."""
        p = obj.get("place")
        if p is None:
            return []
        return list(p) if isinstance(p, list) else [p]

    # ------------------------------------------------------------------ adding

    def _next(self, items: list[dict], prefix: str) -> str:
        n = max((int(i["id"][1:]) for i in items), default=0) + 1
        return f"{prefix}{n}"

    def add_need(self, text: str, importance: int | None = None, group: str = "") -> str:
        nid = self._next(self.data["needs"], "N")
        self.data["needs"].append({"id": nid, "text": text, "importance": importance, "group": group})
        return nid

    def add_object(self, name: str, kind: str, count: int = 1, datum: str | None = None, text: str = "", place=None) -> str:
        oid = self._next(self.data["objects"], "O")
        o = {"id": oid, "name": name, "kind": kind, "count": count, "datum": datum, "text": text}
        if place is not None:
            o["place"] = place
        self.data["objects"].append(o)
        return oid

    def add_metric(self, cls: str = "demand", **fields) -> str:
        """A metric with its fields (`cls` is its class, demand or wish); its needs kept in the needs' order."""
        mid = self._next(self.data["metrics"], "M")
        m = {"id": mid, "class": "demand", "heading": None, "text": "", "object": None, "quantity": None, "unit": None,
             "under": None, "value": None, "needs": [], "source": [], "verified_by": None, "carried_by": [], "mandate": {"form": "held"}}
        m.update(fields)
        m["class"] = cls
        self.sort_needs(m)
        self.data["metrics"].append(m)
        return mid

    def sort_needs(self, metric: dict) -> None:
        """A metric's needs in the order of the needs list, so that the matrix reads the same either way."""
        rank = {n["id"]: i for i, n in enumerate(self.data["needs"])}
        metric["needs"] = sorted(dict.fromkeys(metric.get("needs", [])), key=lambda n: rank.get(n, len(rank)))

    def drop(self, item_id: str) -> None:
        """Mark a need, an object or a metric dropped; its id stays."""
        item = self.need(item_id) or self.obj(item_id) or self.metric(item_id)
        if item is None:
            raise KeyError(f"{item_id} is not in {self.lineage}")
        item["dropped"] = True

    def validate(self) -> "Order":
        S.validate_order(self.data)
        return self
