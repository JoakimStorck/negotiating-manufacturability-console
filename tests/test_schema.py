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
    order["metrics"].append({"id": "M1", "value": {"between": 3}})
    with pytest.raises(SchemaError) as e:
        validate_order(order)
    assert "metrics/0/value" in str(e.value)
    with pytest.raises(SchemaError):
        validate_order({**Order.new("x").data, "lineage": "Not A Lineage"})
    with pytest.raises(SchemaError):
        validate_features({"schema": "features/1"})


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
