"""The checks, a test per rule: each breaks the valid bracket in one place and reads the refusal as a person reads it."""
import pytest

from am_order import check
from am_order.check import RULES

pytestmark = pytest.mark.filterwarnings("ignore")


def refusals(order, features=None, previous=None, rule=None):
    found = check(order, features=features, previous=previous)
    return [r for r in found if rule is None or r.rule == rule]


def one(order, rule, **kw):
    found = refusals(order, rule=rule, **kw)
    assert len(found) == 1, [str(r) for r in check(order, **kw)]
    return found[0]


def test_the_reference_products_pass_every_check(home):
    for lineage in ("plate", "l-bracket", "bracket-ge", "bracket-mass"):
        order = home.load(lineage)
        assert check(order, features=home.features(order.type["design"])) == []


def test_singular(bracket):
    m = bracket.metric("M5")
    m["value"] = {"at_most": 0.2, "at_least": 0.05}
    r = one(bracket, "singular")
    assert r.item == "M5" and "states 2 values" in r.text and "a metric of its own" in r.text
    m["value"] = None
    assert "states no value" in one(bracket, "singular").text


def test_unambiguous_a_metric_without_a_unit(bracket):
    bracket.metric("M2")["unit"] = None
    r = one(bracket, "unambiguous")
    assert (r.item, r.text) == ("M2", "M2 (diameter of the pin hole) has no unit: give its unit, mm.")


def test_unambiguous_a_unit_a_value_and_the_class(bracket):
    bracket.metric("M2")["unit"] = "in"
    assert "use mm" in one(bracket, "unambiguous").text
    bracket.metric("M2")["unit"] = "mm"
    bracket.metric("M5")["value"] = {"band": {"lower": 0.1, "upper": 0.2}}
    assert "state it as at most" in one(bracket, "unambiguous").text
    bracket.metric("M5")["value"] = {"at_most": 0.2}
    bracket.metric("M2")["value"]["band"]["nominal"] = 9.0
    assert "outside the band" in one(bracket, "unambiguous").text
    bracket.metric("M2")["value"]["band"]["nominal"] = 8.3
    bracket.metric("M6")["under"]["unit"] = "kg"
    assert "use N or kN" in one(bracket, "unambiguous").text
    bracket.metric("M6")["under"]["unit"] = "N"
    bracket.metric("M5")["class"] = None
    assert "neither a demand nor a wish" in one(bracket, "unambiguous").text


def test_verifiable(bracket):
    bracket.metric("M5")["verified_by"] = ""
    r = one(bracket, "verifiable")
    assert r.item == "M5" and "says nothing of how it is verified" in r.text


def test_necessary(bracket):
    m = bracket.metric("M4")
    m["needs"] = []
    r = one(bracket, "necessary")
    assert r.item == "M4" and "cites no need and no source but the requester" in r.text
    m["source"].append({"kind": "standard", "ref": "ISO 1101"})
    assert refusals(bracket, rule="necessary") == []


def test_covered_a_need_no_metric_measures(bracket):
    bracket.metric("M5")["needs"] = []
    bracket.metric("M5")["source"].append({"kind": "project", "ref": "x"})
    r = one(bracket, "covered")
    assert (r.item, r.text) == ("N2", "Need N2 ('Sits flat on the frame') is measured by no metric: tick it in the matrix against the "
                                      "metric that measures it, add a metric, or drop the need.")


def test_traceable(home, bracket):
    previous = home.load("bracket-ge")
    bracket.type["metrics"] = [m for m in bracket.type["metrics"] if m["id"] != "M11"]
    r = one(bracket, "traceable", previous=previous)
    assert r.item == "M11" and "mark it dropped instead of removing it" in r.text
    bracket.metric("M12")["carried_by"] = []
    assert {x.item for x in refusals(bracket, rule="traceable", previous=previous)} == {"M11", "M12"}


def test_consistent_an_interval_on_the_wrong_side_of_the_ideal(bracket):
    bracket.set_mandate("M6", {"form": "interval", "to": 0.5})
    r = one(bracket, "consistent")
    assert (r.item, r.text) == ("M6", "M6 (utilisation of the pin hole): the ideal is at most 1, so the far end lies above it; 0.5 does not.")


def test_consistent_a_holds_metric_with_an_interval(bracket):
    bracket.set_mandate("M12", {"form": "interval", "to": "as_needed"})
    r = one(bracket, "consistent")
    assert (r.item, r.text) == ("M12", "M12 (finish of the lug underside) either holds or it does not, so it has no interval: hold it or "
                                       "release it.")


def test_consistent_a_wish_and_two_metrics_alike(bracket):
    bracket.set_mandate("M13", {"form": "held"})
    assert "set its mandate to release" in one(bracket, "consistent").text
    bracket.set_mandate("M13", {"form": "release"})
    bracket.metric("M7")["under"] = dict(bracket.metric("M6")["under"])
    r = one(bracket, "consistent")
    assert r.item == "M7" and "the same quantity on the same object under the same conditions as M6" in r.text


def test_complete_a_heading_neither_covered_nor_stated(bracket):
    del bracket.type["headings"]["transport"]
    r = one(bracket, "complete")
    assert (r.item, r.text) == ("transport", "The heading Transport (limitations due to lifting gear, clearance, means of transport (height "
                                             "and weight), nature and conditions of despatch) has no metric: add one, or state that nothing "
                                             "under it applies to the product.")


def test_named(bracket):
    bracket.metric("M5")["object"] = "O99"
    assert "the object O99, which the product does not have" in one(bracket, "named").text
    bracket.metric("M5")["object"] = "O2"
    bracket.obj("O8")["dropped"] = True
    assert "names O8 (web), which is dropped" in one(bracket, "named").text


def test_placed(bracket):
    bolts = bracket.obj("O4")
    bolts["place"] = bolts["place"][:3]
    assert "has 4 instances and 3 places" in one(bracket, "placed").text
    bracket.obj("O4")["place"].append({"cylinder": {"point": [42, 50, 0], "direction": [0, 0, 1], "radius": 2.2, "length": 60}})
    assert "reaches outside the envelope" in one(bracket, "placed").text
    bracket.obj("O4")["place"][-1]["cylinder"]["length"] = 6
    bracket.obj("O8")["place"] = {"box": {"min": [40, 45, 0], "max": [44, 55, 10]}}
    r = one(bracket, "placed")
    assert r.item == "O4" and "cuts into the wall O8 (web), which must be material" in r.text


def test_bound(home, bracket):
    features = home.features("bracket-ge@v4")
    assert refusals(bracket, features, rule="bound") == []
    b = bracket.binding("O4")
    b["features"] = b["features"][:3]
    assert "is bound to 3 of its 4 features" in one(bracket, "bound", features=features).text
    assert "whose feature list is not in the products home" in one(bracket, "bound").text


def test_delegated(home, bracket):
    bracket.mandates()["M99"] = {"form": "release"}
    r = one(bracket, "delegated")
    assert (r.item, r.text) == ("M99", "The order gives a mandate on M99, which the product does not have: remove the mandate, or give it "
                                       "on one of the product's metrics.")
    del bracket.mandates()["M99"]
    bracket.metric("M11")["dropped"] = True
    bracket.mandates()["M11"] = {"form": "interval", "to": 1.0}
    assert "which is dropped: remove the mandate" in one(bracket, "delegated").text
    bracket.drop("M11")                                          # dropping a metric takes its mandate with it
    assert "M11" not in bracket.mandates() and refusals(bracket, rule="delegated") == []
    del bracket.instance["answering"]
    r = one(bracket, "delegated")
    assert r.item == "order" and "choose park (it waits for your word) or decline" in r.text
    bracket.instance["answering"] = "decline"
    bracket.set_change("O1", "free")
    assert refusals(bracket, rule="delegated") == []             # a free part with a design bound
    bracket.type["design"] = None
    r = one(bracket, "delegated")
    assert r.item == "O1" and "is free, so its shape may change, and no design is bound" in r.text


def test_the_new_rules_refuse_nothing_on_the_examples_and_the_rest_as_before(home):
    """Every version of the examples, order 1 and order 2: no refusal of the rule `delegated`, and the others as before (none)."""
    for lineage in ("plate", "l-bracket", "bracket-ge", "bracket-mass"):
        for v in home.history(lineage):
            order = home.load(f"{lineage}@{v['revision']}")
            assert check(order, features=home.features(order.type["design"])) == [], (lineage, v["revision"])


def test_every_rule_has_a_test():
    tested = {name.split("_")[1] for name in globals() if name.startswith("test_") and name.split("_")[1] in RULES}
    assert tested == set(RULES)
