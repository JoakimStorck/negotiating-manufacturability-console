"""The binding: declared by name or label, matched from an earlier version by place and kind, the rest proposed by words and kinds;
confirmed and rejected by the owner. The MFCAD parts give the share of labelled features the proposals rank first."""
import copy

import pytest

from am_order import Order, bind, confirm, proposals, reject
from am_order.bind import match, rank

MFCAD_WORDS = {"6sides": "hexagonal", "_": " "}


def test_declared_by_name_and_count(home):
    order = home.load("bracket-ge")
    order.type["bindings"] = []
    report = bind(order, home.features("bracket-ge@v4"))
    assert report["declared"]["O4"] == ["bolt-hole-1", "bolt-hole-2", "bolt-hole-3", "bolt-hole-4"]
    assert report["declared"]["O5"] == ["pin-hole"] and not report["proposals"]
    assert all(not f["confirmed"] for b in order.type["bindings"] for f in b["features"])


def _f(name, kind, point=None, direction=None, centroid=(0, 0, 0), key="axis", origin="declared"):
    f = {"name": name, "kind": kind, "origin": origin, "status": "confirmed", "centroid": list(centroid),
         "bbox": {"min": [0, 0, 0], "max": [1, 1, 1]}, "labels": [], "colour": "#000000"}
    if point is not None:
        f[key] = {"point": list(point), "direction": list(direction)}
    return f


# The design level's case (am-llm tests/test_design_intake.py): the plate re-exported with hole-1 filled and a new hole elsewhere.
PLATE_V1 = [_f("underside", "surface", (30, 21, 0), (0, 0, -1), key="normal"), _f("edge-long", "edge", (0, 0, 0), (1, 0, 0)),
            _f("hole-1", "hole", (14.5, 21, 0), (0, 0, 1)), _f("hole-2", "hole", (45.5, 21, 0), (0, 0, 1)),
            _f("top", "surface", (30, 21, 4), (0, 0, 1), key="normal"), _f("body", "zone", centroid=(30, 21, 2))]
PLATE_V2 = [_f("surface-1", "surface", (30.4, 21.2, 0), (0, 0, -1), key="normal", origin="recognised"),
            _f("surface-2", "surface", (30.1, 20.8, 4), (0, 0, 1), key="normal", origin="recognised"),
            _f("hole-1", "hole", (50, 10, 0), (0, 0, 1), origin="recognised"), _f("hole-2", "hole", (45.5, 21, 0), (0, 0, 1), origin="recognised")]


def test_matched_by_place_and_kind_as_the_design_level_matches():
    assert match(PLATE_V1, PLATE_V2) == {"surface-1": "underside", "surface-2": "top", "hole-2": "hole-2"}
    turned = copy.deepcopy(PLATE_V2)
    turned[3]["axis"]["direction"] = [1, 0, 0]                    # a hole along another axis is another hole
    assert "hole-2" not in match(PLATE_V1, turned)
    far = copy.deepcopy(PLATE_V2)
    far[3]["axis"]["point"] = [48, 21, 0]                          # beyond 2 mm
    assert "hole-2" not in match(PLATE_V1, far)


def test_an_earlier_binding_is_carried_and_the_rest_proposed():
    order = Order.new("p")
    hole = order.add_object("screw hole", "hole")
    flat = order.add_object("flat side", "face")
    v1 = {"design": "p@v1", "features": PLATE_V1}
    v2 = {"design": "p@v2", "features": PLATE_V2}
    bind(order, v1)
    confirm(order, hole, "hole-2")
    confirm(order, flat, "underside")
    report = bind(order, v2, previous=v1)
    assert report["matched"] == {hole: ["hole-2"], flat: ["surface-1"]}
    assert order.binding(flat, "p@v2")["features"][0] == {"name": "surface-1", "how": "matched", "confirmed": False, "from": "underside"}


def test_proposals_ranked_confirmed_and_rejected(home):
    features = home.features("nist-am-artifact@v1")
    order = Order.new("n")
    lateral = order.add_object("lateral hole", "hole", count=2, text="the two holes across the side")
    report = bind(order, features)
    ranked = [p["name"] for p in report["proposals"][lateral]]
    assert ranked[:2] == ["lateral-hole-d3", "lateral-hole-d6"]
    reject(order, lateral, "lateral-hole-d6")
    assert "lateral-hole-d6" not in [p["name"] for p in proposals(order, lateral, features)]
    confirm(order, lateral, "lateral-hole-d3")
    b = order.binding(lateral)
    assert b["features"] == [{"name": "lateral-hole-d3", "how": "proposed", "confirmed": True}] and b["rejected"] == ["lateral-hole-d6"]
    confirm(order, lateral, "lateral-hole-d6")                     # the owner changes their mind: the rejection is lifted
    assert order.binding(lateral)["rejected"] == [] and len(order.binding(lateral)["features"]) == 2


def mfcad_objects(features: dict, words: dict) -> tuple[Order, dict[str, set]]:
    """One object per labelled class, named in words, its count the class's instances; with the instances it should take."""
    order = Order.new("m")
    truth: dict[str, set] = {}
    classes: dict[str, list] = {}
    for f in features["features"]:
        for label in f["labels"]:
            classes.setdefault(label.split(":", 1)[1], []).append(f["name"])
    for cls, names in classes.items():
        name = words.get(cls) or cls.replace("6sides", "hexagonal").replace("_", " ")
        kind = "edge" if cls == "chamfer" else "slot"
        truth[order.add_object(name, kind, count=len(names))] = set(names)
    return order, truth


def mfcad_share(features: dict, words: dict | None = None) -> tuple[int, int]:
    """Of the labelled features, how many the proposals rank among the first `count` for their object."""
    order, truth = mfcad_objects(features, words or {})
    hits = total = 0
    for oid, names in truth.items():
        o = order.obj(oid)
        first = [r["name"] for r in rank(o, features)][: o["count"]]
        hits += len(names & set(first))
        total += len(names)
    return hits, total


SYNONYMS = {"rectangular_through_slot": "through groove", "6sides_pocket": "six-sided recess", "triangular_passage": "triangle opening",
            "rectangular_passage": "square opening", "chamfer": "bevelled edge"}

OTHER = {"rectangular_through_slot": "long cut", "6sides_pocket": "nut cavity", "triangular_passage": "three-cornered duct",
         "rectangular_passage": "box duct", "chamfer": "angled corner"}


@pytest.mark.parametrize("design", ["mfcad-simple@v1", "mfcad-complex@v1"])
def test_the_mfcad_parts_proposals_rank_the_labelled_features_first(home, design):
    features = home.features(design)
    hits, total = mfcad_share(features)
    assert total >= 3 and hits == total                            # the class's own words
    assert mfcad_share(features, SYNONYMS)[0] == total             # the words the tool knows as the same
    assert mfcad_share(features, OTHER)[0] <= total                # words it does not know: the thesis's question
