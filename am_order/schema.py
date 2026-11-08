"""The contracts, each versioned by its file name: with a design system the order (`schemas/order-1.json`) and the feature list
(`schemas/features-1.json`), against which every read and every save validates; with am-llm's standing frame its presence
(`schemas/presence-1.json`) and a run's events (`schemas/events-1.json`), sketched before the frame is built and validated as the
frame serves them. Every schema carries an example of its form."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator

HERE = Path(__file__).parent / "schemas"
ORDER = "order-1.json"
FEATURES = "features-1.json"
PRESENCE = "presence-1.json"
EVENTS = "events-1.json"


class SchemaError(ValueError):
    """A document that does not have the contract's form; `errors` names each place."""

    def __init__(self, what: str, errors: list[str]):
        self.errors = errors
        super().__init__(f"{what} does not have the form of its schema: " + "; ".join(errors[:5]) + (" ..." if len(errors) > 5 else ""))


@lru_cache(maxsize=None)
def schema(name: str) -> dict:
    return json.loads((HERE / name).read_text(encoding="utf-8"))


@lru_cache(maxsize=None)
def _validator(name: str) -> Draft202012Validator:
    return Draft202012Validator(schema(name))


def errors(document: dict, name: str) -> list[str]:
    out = []
    for e in sorted(_validator(name).iter_errors(document), key=lambda e: list(e.absolute_path)):
        where = "/".join(str(p) for p in e.absolute_path) or "(the document)"
        out.append(f"{where}: {e.message}")
    return out


def validate_order(order: dict) -> dict:
    found = errors(order, ORDER)
    if found:
        raise SchemaError(f"the order {order.get('lineage')!r}" if isinstance(order, dict) else "the order", found)
    return order


def validate_features(features: dict) -> dict:
    found = errors(features, FEATURES)
    if found:
        raise SchemaError(f"the feature list {features.get('design')!r}" if isinstance(features, dict) else "the feature list", found)
    return features


def validate_presence(presence: dict) -> dict:
    found = errors(presence, PRESENCE)
    if found:
        raise SchemaError("the frame's presence", found)
    return presence


def validate_events(events: dict) -> dict:
    found = errors(events, EVENTS)
    if found:
        raise SchemaError(f"the events of the run {(events.get('run') or {}).get('id')!r}" if isinstance(events, dict) else "the events", found)
    return events
