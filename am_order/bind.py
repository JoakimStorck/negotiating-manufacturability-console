"""The binding: each of the product's objects resolved to features of a design version, by the version's feature list. The tool
proposes and the owner decides; no model is called. An order without a design is complete and unbound.

- `declared`: a feature or a label bears the object's name (an object with `count` n takes n such features).
- `matched`: an earlier version's binding carried to the features at the same place with the same or a compatible kind (the rule
  of the design level's matching between versions: nearest first, within 2 mm, the directions within 0.1 of parallel, each
  earlier feature used once).
- `proposed`: for the rest, features ranked by the object's words against the features' names, kinds and labels; the owner
  confirms or rejects each one, and a rejected feature is not proposed for the object again.

    report = bind(order, features, previous=None)     # declared and matched written into the order; the proposals returned
    confirm(order, "O3", "pin-hole"); reject(order, "O3", "surface-2")
"""
from __future__ import annotations

import math
import re

from .order import Order, slug

TOLERANCE = 2.0           # mm between locations counted as the same place
AXIS_TOLERANCE = 0.1      # 1 - |cos| between directions counted as the same direction
COMPATIBLE = {("hole", "boss"), ("surface", "overhang"), ("surface", "bridge"), ("wall", "rib"), ("zone", "surface")}

# The design's kinds an object of each kind is likely to be.
KINDS = {"face": ("surface", "overhang", "bridge"), "hole": ("hole",), "slot": ("zone", "hole"), "edge": ("edge", "chamfer", "fillet"),
         "wall": ("wall", "rib", "boss", "fillet", "zone"), "part": ()}
# Words that name the same thing, each mapped to one form.
SYNONYMS = {"hexagonal": "6sides", "hexagon": "6sides", "six": "6sides", "sided": "sides", "6": "6sides", "bore": "hole",
            "opening": "hole", "pocket": "pocket", "recess": "pocket", "groove": "slot", "channel": "slot", "bevel": "chamfer",
            "rounding": "fillet", "radius": "fillet", "plane": "face", "surface": "face", "side": "face", "rectangle": "rectangular",
            "square": "rectangular", "triangle": "triangular", "through": "through", "mounting": "mount", "mount": "mount",
            "base": "bottom", "underside": "bottom", "bottom": "bottom", "lip": "edge", "rim": "edge", "flange": "wall", "rib": "wall",
            "web": "wall", "boss": "boss", "pin": "pin", "bolt": "bolt", "screw": "bolt"}
STOP = {"the", "a", "an", "of", "on", "in", "at", "to", "and", "for", "with", "by", "its", "it", "mfcad", "is", "that", "which"}


def tokens(text: str) -> set[str]:
    out = set()
    for w in re.findall(r"[a-z0-9]+", (text or "").lower()):
        if w in STOP or w.isdigit() and w != "6":
            continue
        if len(w) > 3 and w.endswith("s") and not w.endswith("ss") and w != "6sides":
            w = w[:-1]
        out.add(SYNONYMS.get(w, w))
    return out


def _base(name: str) -> str:
    return re.sub(r"-[0-9]+$", "", name)


def _label_names(feature: dict) -> list[str]:
    return [slug(lab.split(":", 1)[-1]) for lab in feature.get("labels", [])]


def _number(name: str) -> int:
    m = re.search(r"-([0-9]+)$", name)
    return int(m.group(1)) if m else 0


def declared(obj: dict, features: dict) -> list[str]:
    """The features that bear the object's name, by name or by label, numbered ones in their order."""
    s = slug(obj["name"])
    live = [f for f in features["features"] if f["status"] != "rejected"]
    exact = [f["name"] for f in live if f["name"] == s]
    numbered = sorted((f["name"] for f in live if _base(f["name"]) == s and f["name"] != s), key=_number)
    labelled = [f["name"] for f in live if s in _label_names(f) and f["name"] not in exact + numbered]
    found = exact + numbered + labelled
    return found[: obj.get("count", 1)] if len(found) >= obj.get("count", 1) else []


# -------------------------------------------------------------------- matched: the design level's rule, written anew

def _location(f: dict):
    for k in ("axis", "normal"):
        if k in f:
            return f[k]["point"]
    return f.get("centroid")


def _direction(f: dict):
    for k in ("axis", "normal"):
        if k in f:
            v = f[k]["direction"]
            n = math.sqrt(sum(x * x for x in v))
            return [x / n for x in v]
    return None


def _same_kind(a: str, b: str) -> bool:
    return a == b or (a, b) in COMPATIBLE or (b, a) in COMPATIBLE


def match(previous: list[dict], current: list[dict], tolerance: float = TOLERANCE) -> dict[str, str]:
    """{current name: previous name} for features at the same place with the same or a compatible kind."""
    pairs = []
    for c in current:
        lc = _location(c)
        if lc is None:
            continue
        for p in previous:
            lp = _location(p)
            if lp is None or not _same_kind(p["kind"], c["kind"]):
                continue
            dist = math.dist(lc, lp)
            if dist > tolerance:
                continue
            dc, dp = _direction(c), _direction(p)
            if dc is not None and dp is not None and 1 - abs(sum(x * y for x, y in zip(dc, dp))) > AXIS_TOLERANCE:
                continue
            pairs.append((dist, 0 if p["kind"] == c["kind"] else 1, c["name"], p["name"]))
    out, used = {}, set()
    for _, _, cname, pname in sorted(pairs):
        if cname in out or pname in used:
            continue
        out[cname] = pname
        used.add(pname)
    return out


# -------------------------------------------------------------------- proposed: ranked by words and kinds

def rank(obj: dict, features: dict, taken: set[str] = frozenset(), rejected: set[str] = frozenset()) -> list[dict]:
    """The features for an object, best first: {name, score, why}."""
    words = tokens(obj["name"]) | tokens(obj.get("text", ""))
    kinds = KINDS.get(obj["kind"], ())
    out = []
    for f in features["features"]:
        if f["status"] == "rejected" or f["name"] in rejected:
            continue
        fw = tokens(f["name"].replace("-", " ")) | {w for lab in f.get("labels", []) for w in tokens(lab.split(":", 1)[-1].replace("_", " "))}
        fw |= tokens(f["kind"])
        shared = words & fw
        score = 2.0 * len(shared) / max(1, len(words)) + (1.0 if f["kind"] in kinds else 0.0)
        score += 0.25 if f["origin"] == "declared" else 0.0
        score -= 0.5 if f["name"] in taken else 0.0
        why = []
        if shared:
            why.append("words " + ", ".join(sorted(shared)))
        if f["kind"] in kinds:
            why.append(f"kind {f['kind']}")
        if f["name"] in taken:
            why.append("bound to another object")
        out.append({"name": f["name"], "score": round(score, 3), "why": "; ".join(why) or "nothing in common"})
    return sorted(out, key=lambda x: (-x["score"], _number(x["name"]), x["name"]))


# -------------------------------------------------------------------- the binding of an order

def _set(order: Order, oid: str, design: str, names: list[str], how: str, sources: dict | None = None) -> None:
    b = order.binding(oid, design)
    if b is None:
        b = {"object": oid, "design": design, "features": [], "rejected": []}
        order.data.setdefault("bindings", []).append(b)
    have = {f["name"] for f in b["features"]}
    for n in names:
        if n not in have:
            entry = {"name": n, "how": how, "confirmed": False}
            if sources and n in sources:
                entry["from"] = sources[n]
            b["features"].append(entry)


def bind(order: Order, features: dict, previous: dict | None = None) -> dict:
    """Bind the order's objects to the features of `features` (a feature list): `declared` and `matched` bindings written into
    the order (unconfirmed), the order's design set to the list's; returns {declared, matched, proposals, unbound}, the proposals
    ranked per object still short of its count. `previous`: the feature list of the version the order was bound to before."""
    design = features["design"]
    earlier = order.data.get("design")
    order.data["design"] = design
    report = {"design": design, "declared": {}, "matched": {}, "proposals": {}, "unbound": []}
    mapping = {}
    if previous is not None and earlier and earlier != design:
        mapping = {p: c for c, p in match(previous["features"], features["features"]).items()}
    for o in order.objects():
        if o["kind"] == "part":
            continue
        have = order.features_of(o["id"], design)
        if len(have) >= o.get("count", 1):
            continue
        names = declared(o, features)
        if names:
            _set(order, o["id"], design, names, "declared")
            report["declared"][o["id"]] = names
            continue
        if mapping:
            old = order.features_of(o["id"], earlier)
            carried = [mapping[n] for n in old if n in mapping]
            if carried:
                _set(order, o["id"], design, carried, "matched", {mapping[n]: n for n in old if n in mapping})
                report["matched"][o["id"]] = carried
                if len(carried) >= o.get("count", 1):
                    continue
        report["proposals"][o["id"]] = proposals(order, o["id"], features)
        if not report["proposals"][o["id"]]:
            report["unbound"].append(o["id"])
    return report


def proposals(order: Order, oid: str, features: dict, limit: int = 5) -> list[dict]:
    """The ranked features for an object not yet bound to as many as its count."""
    o = order.obj(oid)
    design = features["design"]
    b = order.binding(oid, design) or {}
    have = {f["name"] for f in b.get("features", [])}
    taken = {f["name"] for x in order.data.get("bindings", []) if x["design"] == design and x["object"] != oid for f in x["features"]}
    ranked = [r for r in rank(o, features, taken, set(b.get("rejected", []))) if r["name"] not in have]
    return [r for r in ranked if r["score"] > 0][:limit]


def confirm(order: Order, oid: str, name: str | None = None, design: str | None = None) -> None:
    """The owner confirms a proposal (adding it to the binding) or, without a name, every feature of the object's binding."""
    design = design or order.data.get("design")
    if name is not None:
        b = order.binding(oid, design)
        if b is None or name not in {f["name"] for f in b["features"]}:
            _set(order, oid, design, [name], "proposed")
            b = order.binding(oid, design)
        if name in b.get("rejected", []):
            b["rejected"].remove(name)
        for f in b["features"]:
            if f["name"] == name:
                f["confirmed"] = True
        return
    b = order.binding(oid, design)
    for f in (b or {}).get("features", []):
        f["confirmed"] = True


def reject(order: Order, oid: str, name: str, design: str | None = None) -> None:
    """The owner rejects a feature for an object: it leaves the binding and is not proposed again."""
    design = design or order.data.get("design")
    b = order.binding(oid, design)
    if b is None:
        b = {"object": oid, "design": design, "features": [], "rejected": []}
        order.data.setdefault("bindings", []).append(b)
    b["features"] = [f for f in b["features"] if f["name"] != name]
    b.setdefault("rejected", [])
    if name not in b["rejected"]:
        b["rejected"].append(name)


# -------------------------------------------------------------------- a skeleton from a feature list

def object_kind(feature: dict) -> str:
    words = tokens(" ".join(feature.get("labels", [])) + " " + feature["name"])
    if feature["kind"] == "hole":
        return "hole"
    if words & {"slot", "pocket", "passage", "step"}:
        return "slot"
    if feature["kind"] in ("surface", "overhang", "bridge"):
        return "face"
    if feature["kind"] in ("edge", "chamfer"):
        return "edge"
    return "wall"


def skeleton_objects(order: Order, features: dict) -> None:
    """The product's objects from a design's declared features (numbered ones as one object with its count), the part as a
    whole besides, each bound `declared`."""
    if order.part() is None:
        order.add_object("part", "part", text="the part as a whole")
    groups: dict[str, list[dict]] = {}
    for f in features["features"]:
        if f["origin"] == "declared" and f["status"] != "rejected":
            groups.setdefault(_base(f["name"]), []).append(f)
    for base, fs in groups.items():
        oid = order.add_object(base.replace("-", " "), object_kind(fs[0]), count=len(fs),
                               text=f"from the design's feature{'s' if len(fs) > 1 else ''} {', '.join(f['name'] for f in fs)}")
        names = declared(order.obj(oid), features)
        if names:
            _set(order, oid, features["design"], names, "declared")
