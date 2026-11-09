"""The order (`schemas/order-2.json`) in two sections: `type`, the product's requirements (its needs, objects and metrics, the
design version and the bindings), and `order`, this order of it (the brief, the mandate per metric, the answering policy, the
requirements in force and the accepted plan).

    order = Order.new("bracket", name="Engine bracket")
    n = order.add_need("Carries the handling loads", importance=5, group="Strength")
    o = order.add_object("pin hole", "hole")
    m = order.add_metric(heading="geometry", object=o, quantity="diameter", unit="mm",
                         value={"band": {"nominal": 8.3, "lower": 8.0, "upper": 8.6}}, needs=[n])
    order.set_mandate(m, {"form": "interval", "to": {"lower": 7.9, "upper": 8.7}})
    order.set_change(o, "free")

An id is never reused: a need, an object or a metric is dropped by marking it, never removed. The chain is need -> metric ->
object -> feature; the needs-metrics matrix is read from the metrics' `needs`.

A version saved as order 1 is read in its order-2 form, the face every interface uses (`Order.data`), and keeps its own bytes
and hash (`Order.raw`, `Order.content_hash`); `Order.from_v1` gives the order 2 with the notes of what it could not carry over.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re

from . import schema as S

SET_BY_HOME = ("revision", "previous", "saved")
ANSWERING = {"park": "a case the mandates do not cover parks at the frame for your word",
             "decline": "a case the mandates do not cover is declined by the requester on the evidence of exhausted means"}
CHANGE = {"free": "the design may change around it", "fixed": "an interface the design keeps"}
HELD = {"form": "held"}
TOP = ("lineage", "title", "parent", "group", "tags", "revision", "previous", "saved")
TYPE = ("product", "design", "needs", "objects", "metrics", "headings", "bindings")


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
    """An order as a document with the helpers the interfaces share. `data` is the document in its order-2 form; `raw` the
    document as read, which differs from `data` only for a version saved as order 1 (`form` 1)."""

    def __init__(self, data: dict, validate: bool = True):
        if validate:
            S.validate_order(data)
        self.raw = data
        self.form = 1 if data.get("schema") == "order/1" else 2
        if self.form == 1:
            self.data, self.notes = migrate(data)
        else:
            self.data, self.notes = data, []

    # ------------------------------------------------------------------ making

    @classmethod
    def new(cls, lineage: str, name: str | None = None, purpose: str = "", group: str | None = None) -> "Order":
        data = {"schema": "order/2", "lineage": lineage, "title": name or lineage, "parent": None, "tags": [],
                "type": {"product": {"name": name or lineage, "purpose": purpose, "picture": None}, "design": None,
                         "needs": [], "objects": [], "metrics": [], "headings": {}, "bindings": []},
                "order": {"brief": {"text": "", "objective": None, "quantity": None}, "mandates": {}, "answering": "park",
                          "in_force": [], "accepted": None}}
        if group:
            data["group"] = group
        return cls(data)

    @classmethod
    def from_v1(cls, data: dict) -> "Order":
        """An order-1 document as an order 2, with `notes`: what it named that order 2 says elsewhere and the owner states."""
        migrated, notes = migrate(data)
        order = cls(migrated)
        order.notes = notes
        return order

    def copy(self) -> "Order":
        return Order(copy.deepcopy(self.data), validate=False)

    @property
    def lineage(self) -> str:
        return self.data["lineage"]

    @property
    def type(self) -> dict:
        """The type section: the product's requirements."""
        return self.data["type"]

    @property
    def instance(self) -> dict:
        """The order section: this order of the product."""
        return self.data["order"]

    def content(self) -> dict:
        """The order without what the home sets on save: what tells two versions apart."""
        return {k: v for k, v in self.data.items() if k not in SET_BY_HOME}

    def content_hash(self) -> str:
        """The hash of the content as read: a version saved as order 1 keeps its own."""
        return sha256(canonical({k: v for k, v in self.raw.items() if k not in SET_BY_HOME}))

    # ------------------------------------------------------------------ lookups

    def need(self, nid: str) -> dict | None:
        return next((n for n in self.type["needs"] if n["id"] == nid), None)

    def obj(self, oid: str | None) -> dict | None:
        return next((o for o in self.type["objects"] if o["id"] == oid), None)

    def metric(self, mid: str) -> dict | None:
        return next((m for m in self.type["metrics"] if m["id"] == mid), None)

    def needs(self, dropped: bool = False) -> list[dict]:
        return [n for n in self.type["needs"] if dropped or not n.get("dropped")]

    def objects(self, dropped: bool = False) -> list[dict]:
        return [o for o in self.type["objects"] if dropped or not o.get("dropped")]

    def metrics(self, dropped: bool = False) -> list[dict]:
        return [m for m in self.type["metrics"] if dropped or not m.get("dropped")]

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

    def mandates(self) -> dict[str, dict]:
        """The order's mandates by metric id; a metric not among them is held."""
        return self.instance.setdefault("mandates", {})

    def mandate(self, metric) -> dict:
        """A metric's mandate in this order (the metric or its id): held where the order gives none."""
        mid = metric["id"] if isinstance(metric, dict) else metric
        return self.mandates().get(mid) or dict(HELD)

    def set_mandate(self, metric, mandate: dict) -> None:
        """A metric's mandate written to the order; held is written as no mandate."""
        mid = metric["id"] if isinstance(metric, dict) else metric
        if (mandate or HELD).get("form", "held") == "held":
            self.mandates().pop(mid, None)
        else:
            self.mandates()[mid] = dict(mandate)

    def brief(self) -> dict:
        """The order's intent: its text, objective and quantity."""
        b = self.instance.get("brief") or {}
        return {"text": b.get("text") or "", "objective": b.get("objective"), "quantity": b.get("quantity")}

    def answering(self) -> str | None:
        """The owner's answering policy: park or decline; None where it is not stated."""
        return self.instance.get("answering")

    def change(self, obj) -> str:
        """An object's change (the object or its id): free, or fixed where nothing is said."""
        o = obj if isinstance(obj, dict) else self.obj(obj)
        return (o or {}).get("change") or "fixed"

    def set_change(self, oid: str, change: str) -> None:
        if change not in CHANGE:
            raise ValueError(f"an object is fixed or free, not {change!r}")
        o = self.obj(oid)
        if o is None:
            raise KeyError(f"{oid} is not in {self.lineage}")
        o["change"] = change

    def free(self) -> list[dict]:
        """The objects the design may change around."""
        return [o for o in self.objects() if self.change(o) == "free"]

    def in_force(self) -> list[dict]:
        return list(self.instance.get("in_force") or [])

    def accepted(self) -> dict | None:
        return self.instance.get("accepted")

    def objects_named(self, metric: dict) -> list[str]:
        """The objects a metric names: its object, where its load acts and what holds the part, its datums, what carries it."""
        out = [metric.get("object")]
        u = metric.get("under") or {}
        out += [u.get("at")] + list(u.get("held_by") or []) + list(u.get("datums") or [])
        out += list(metric.get("carried_by") or [])
        return [o for o in dict.fromkeys(out) if o]

    def binding(self, oid: str, design: str | None = None) -> dict | None:
        design = design or self.type.get("design")
        return next((b for b in self.type.get("bindings", []) if b["object"] == oid and b["design"] == design), None)

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
        nid = self._next(self.type["needs"], "N")
        self.type["needs"].append({"id": nid, "text": text, "importance": importance, "group": group})
        return nid

    def add_object(self, name: str, kind: str, count: int = 1, datum: str | None = None, text: str = "", place=None,
                   change: str = "fixed") -> str:
        oid = self._next(self.type["objects"], "O")
        o = {"id": oid, "name": name, "kind": kind, "count": count, "datum": datum, "text": text, "change": change}
        if place is not None:
            o["place"] = place
        self.type["objects"].append(o)
        return oid

    def add_metric(self, cls: str = "demand", mandate: dict | None = None, **fields) -> str:
        """A metric with its fields (`cls` is its class, demand or wish) and its mandate in this order, held where none is given;
        its needs kept in the needs' order."""
        mid = self._next(self.type["metrics"], "M")
        m = {"id": mid, "class": "demand", "heading": None, "text": "", "object": None, "quantity": None, "unit": None,
             "under": None, "value": None, "needs": [], "source": [], "verified_by": None, "carried_by": []}
        m.update(fields)
        m["class"] = cls
        self.sort_needs(m)
        self.type["metrics"].append(m)
        if mandate is not None:
            self.set_mandate(mid, mandate)
        return mid

    def sort_needs(self, metric: dict) -> None:
        """A metric's needs in the order of the needs list, so that the matrix reads the same either way."""
        rank = {n["id"]: i for i, n in enumerate(self.type["needs"])}
        metric["needs"] = sorted(dict.fromkeys(metric.get("needs", [])), key=lambda n: rank.get(n, len(rank)))

    def drop(self, item_id: str) -> None:
        """Mark a need, an object or a metric dropped; its id stays. A dropped metric's mandate goes with it."""
        item = self.need(item_id) or self.obj(item_id) or self.metric(item_id)
        if item is None:
            raise KeyError(f"{item_id} is not in {self.lineage}")
        item["dropped"] = True
        if item_id.startswith("M"):
            self.mandates().pop(item_id, None)

    def validate(self) -> "Order":
        S.validate_order(self.data)
        return self


# -------------------------------------------------------------------- order 1 to order 2

def migrate(data: dict) -> tuple[dict, list[str]]:
    """An order-1 document in the form of order 2, and the notes of what it named that order 2 says elsewhere:

    - each metric's mandate goes to `order.mandates` (held, the default, is not written);
    - the brief's text, objective and quantity go to `order.brief`; `answering` is `park`;
    - every object is `fixed`, except the part object where `may_change` names `shape`, which is `free`;
    - `may_relax` is dropped where every metric it names has a mandate that is not held, and noted otherwise;
    - `may_change`'s design parameters and `material` are noted: which objects a parameter frees is the design's knowledge,
      and a material the design may change is a material metric not held, both for the owner to state."""
    d = copy.deepcopy(data)
    brief = d.get("brief") or {}
    metrics = d.get("metrics") or []
    may_change = list(brief.get("may_change") or [])
    out = {"schema": "order/2"}
    out.update({k: d[k] for k in TOP if k in d})
    t = {k: d[k] for k in TYPE if k in d}
    mandates = {}
    for m in t.get("metrics", []):
        mandate = m.pop("mandate", None)
        if mandate and mandate.get("form", "held") != "held" and not m.get("dropped"):
            mandates[m["id"]] = mandate
    part = next((o for o in t.get("objects", []) if o.get("kind") == "part" and not o.get("dropped")), None)
    for o in t.get("objects", []):
        o["change"] = "free" if o is part and "shape" in may_change else "fixed"
    out["type"] = t
    out["order"] = {"brief": {k: brief[k] for k in ("text", "objective", "quantity") if k in brief}, "mandates": mandates,
                    "answering": "park", "in_force": [], "accepted": None}
    notes = []
    parameters = [p for p in may_change if p not in ("shape", "material")]
    if parameters:
        notes.append(f"may_change named {', '.join(parameters)}: state which objects are free")
    if "material" in may_change:
        notes.append("may_change named material: give the material's metric a mandate that is not held where the design may change it")
    if "shape" in may_change and part is None:
        notes.append("may_change named shape, and the product has no part object: add the part and make it free")
    unheld = [m for m in (brief.get("may_relax") or []) if m not in mandates]
    if unheld:
        notes.append(f"may_relax named {', '.join(unheld)}, which no mandate delegates: give each the mandate it may be relaxed within")
    return out, notes
