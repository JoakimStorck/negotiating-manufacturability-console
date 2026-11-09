"""The contracts: every example validates; a document out of form is refused with the place named."""
import json

import pytest

from am_order import Order, SchemaError, validate_events, validate_features, validate_order, validate_presence, validate_runs
from am_order.schema import schema
from conftest import EXAMPLES, REFERENCE


def test_every_example_validates():
    for lineage in REFERENCE:
        folder = EXAMPLES / "own" / lineage
        validate_order(json.loads((folder / "order.json").read_text(encoding="utf-8")))
        for version in (folder / "versions").glob("*.json"):
            validate_order(json.loads(version.read_text(encoding="utf-8")))
    lists = sorted((EXAMPLES / "features").glob("*/features-1.json"))
    assert len(lists) >= 8
    for path in lists:
        validate_features(json.loads(path.read_text(encoding="utf-8")))


def test_a_document_out_of_form_is_refused():
    order = Order.new("x").data
    order["type"]["metrics"].append({"id": "M1", "value": {"between": 3}})
    with pytest.raises(SchemaError) as e:
        validate_order(order)
    assert "type/metrics/0/value" in str(e.value)
    order["type"]["metrics"] = []
    for bad in ({"answering": "ask"}, {"mandates": {"m1": {"form": "held"}}}, {"may_change": ["shape"]}):
        with pytest.raises(SchemaError):
            validate_order({**order, "order": {**order["order"], **bad}})
    with pytest.raises(SchemaError):                                       # order 1's fields are not order 2's
        validate_order({**order, "brief": {"may_relax": []}})
    with pytest.raises(SchemaError):
        validate_order({**Order.new("x").data, "lineage": "Not A Lineage"})
    with pytest.raises(SchemaError):
        validate_features({"schema": "features/1"})


def test_order_2_validates_its_own_examples_and_order_1_stays_readable():
    examples = schema("order-2.json")["examples"]
    assert examples and any(e["order"]["in_force"] for e in examples) and any(e["order"]["accepted"] is None for e in examples)
    for example in examples:
        validate_order(example)
    for version in (EXAMPLES / "own" / "bracket-mass" / "versions").glob("*.json"):
        d = json.loads(version.read_text(encoding="utf-8"))
        if d["schema"] == "order/1":
            validate_order(d)                                              # by order-1.json
            with pytest.raises(SchemaError):
                validate_order({**d, "schema": "order/2"})


def test_every_order_1_version_migrates_to_an_order_2_that_validates_with_its_notes():
    """The migration's notes name exactly what may_change named that the tool cannot carry: the design's parameters."""
    named = {"plate": ["thickness"], "l-bracket": [], "bracket-ge": ["lug_thickness", "fillet_radius", "underside_angle"],
             "bracket-mass": ["lug_thickness", "fillet_radius", "underside_angle"]}
    seen = 0
    for lineage in REFERENCE:
        for version in (EXAMPLES / "own" / lineage / "versions").glob("*.json"):
            d = json.loads(version.read_text(encoding="utf-8"))
            if d["schema"] != "order/1":
                continue
            seen += 1
            order = Order.from_v1(d)
            validate_order(order.data)
            carried = [p for p in d["brief"]["may_change"] if p not in ("shape",)]
            assert carried == named[lineage]
            assert order.notes == ([f"may_change named {', '.join(carried)}: state which objects are free"] if carried else [])
            assert (order.change(order.part()) == "free") == ("shape" in d["brief"]["may_change"])
            assert order.mandates() == {m["id"]: m["mandate"] for m in d["metrics"] if m.get("mandate", {"form": "held"})["form"] != "held"}
            assert order.answering() == "park" and order.in_force() == [] and order.accepted() is None
    assert seen == 5


def test_the_migration_notes_material_and_may_relax():
    d = next(json.loads(p.read_text(encoding="utf-8")) for p in (EXAMPLES / "own" / "plate" / "versions").glob("*.json")
             if json.loads(p.read_text(encoding="utf-8"))["schema"] == "order/1")
    d["brief"]["may_change"] = ["material", "shape"]
    d["brief"]["may_relax"] = ["M5"]
    order = Order.from_v1(d)
    assert order.notes == ["may_change named material: give the material's metric a mandate that is not held where the design may change it",
                           "may_relax named M5, which no mandate delegates: give each the mandate it may be relaxed within"]
    assert order.change(order.part()) == "free"
    next(m for m in d["metrics"] if m["id"] == "M5")["mandate"] = {"form": "interval", "to": 0.85}
    assert Order.from_v1(d).notes[1:] == []                               # may_relax dropped: its metric has a mandate


def test_the_frames_contracts_validate_their_own_examples():
    for name, validate in (("presence-1.json", validate_presence), ("runs-1.json", validate_runs), ("events-1.json", validate_events)):
        examples = schema(name)["examples"]
        assert examples
        for example in examples:
            validate(example)


def test_down_is_the_readers_and_never_written():
    presence = json.loads(json.dumps(schema("presence-1.json")["examples"][0]))
    presence["parts"][0]["state"] = "down"
    with pytest.raises(SchemaError) as e:
        validate_presence(presence)
    assert "parts/0/state" in str(e.value)
    machine = json.loads(json.dumps(schema("presence-1.json")["examples"][0]))
    del machine["parts"][3]["machine"]
    with pytest.raises(SchemaError):
        validate_presence(machine)


def test_an_event_has_its_kinds_form_and_no_other():
    events = schema("events-1.json")["examples"][0]
    acceptance = json.loads(json.dumps(events))
    acceptance["events"][-1]["relaxations"][0].pop("to")
    with pytest.raises(SchemaError):
        validate_events(acceptance)
    unknown = json.loads(json.dumps(events))
    unknown["events"].append({"seq": 8, "time": "2026-11-20T09:15:02Z", "kind": "rumour"})
    with pytest.raises(SchemaError):
        validate_events(unknown)
    parked = json.loads(json.dumps(events))
    parked["run"]["status"] = "parked"
    parked["events"].append({"seq": 8, "time": "2026-11-20T09:15:02Z", "kind": "parked", "case": "c1", "what": "showing",
                             "dialogue": "k31", "metrics": ["M13"], "source": {"table": "call", "row": "k31"}})
    validate_events(parked)
    local = json.loads(json.dumps(events))
    catalogue = json.loads(json.dumps(schema("runs-1.json")["examples"][0]))
    catalogue["runs"][0]["makers"]["foreman"] = {"kind": "none"}
    with pytest.raises(SchemaError):
        validate_runs(catalogue)
    local["at"] = "2026-11-20T10:15:02+01:00"
    with pytest.raises(SchemaError):
        validate_events(local)


def test_a_runs_result_has_an_example_of_every_outcome_and_may_be_absent():
    catalogue = schema("runs-1.json")["examples"][0]
    outcomes = {(r.get("result") or {}).get("outcome") for r in catalogue["runs"]}
    assert {"accepted", "declined", "parked", "referred", "stopped", "error", None} <= outcomes
    without = json.loads(json.dumps(catalogue))
    for r in without["runs"]:
        r.pop("result", None)
    validate_runs(without)                                   # a run ended before the result was served
    unitless = json.loads(json.dumps(catalogue))
    accepted = next(r for r in unitless["runs"] if (r.get("result") or {}).get("outcome") == "accepted")
    accepted["result"]["plan"]["settings"]["layer_height"] = 0.15
    with pytest.raises(SchemaError):
        validate_runs(unitless)
    parked = schema("events-1.json")["examples"][1]
    assert parked["run"]["result"]["waits"]["metrics"] == ["M13"]
    validate_events(parked)
    # every outcome's result is as valid on events-1's run as on runs-1's
    for r in catalogue["runs"]:
        if r.get("result"):
            done = json.loads(json.dumps(schema("events-1.json")["examples"][0]))
            done["run"].update(status="done", result=r["result"])
            validate_events(done)
