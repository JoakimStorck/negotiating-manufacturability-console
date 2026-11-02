"""The two contracts: every example validates; a document out of form is refused with the place named."""
import json

import pytest

from am_order import Order, SchemaError, validate_features, validate_order
from conftest import EXAMPLES, REFERENCE


def test_every_example_validates():
    for lineage in REFERENCE:
        folder = EXAMPLES / "own" / lineage
        validate_order(json.loads((folder / "order.json").read_text()))
        for version in (folder / "versions").glob("*.json"):
            validate_order(json.loads(version.read_text()))
    lists = sorted((EXAMPLES / "features").glob("*/features-1.json"))
    assert len(lists) >= 8
    for path in lists:
        validate_features(json.loads(path.read_text()))


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
