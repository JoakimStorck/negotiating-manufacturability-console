"""The contracts, each versioned by its file name: with a design system the order (`schemas/order-2.json`, and `schemas/order-1.json`
for the versions saved before it) and the feature list (`schemas/features-1.json`), against which every read and every save
validates, an order by the form its `schema` names; with am-llm's standing frame its presence
(`schemas/presence-1.json`), its runs (`schemas/runs-1.json`) and a run's events (`schemas/events-1.json`), sketched before the frame is built and validated as the
frame serves them; and the dialogue between the order's owner and the frame (`schemas/dialogue-1.json`: the dialogue the owner
reads, the word the owner gives, the frame's answer to it), one file of three documents told apart by `schema`. Every schema
carries an example of its form."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator

HERE = Path(__file__).parent / "schemas"
ORDER = "order-2.json"
ORDERS = {"order/1": "order-1.json", "order/2": "order-2.json"}
FEATURES = "features-1.json"
PRESENCE = "presence-1.json"
EVENTS = "events-1.json"
RUNS = "runs-1.json"
DIALOGUE = "dialogue-1.json"


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


@lru_cache(maxsize=None)
def _part(name: str, part: str) -> Draft202012Validator:
    """A validator of one document of a schema that holds several (`$defs/<part>`)."""
    whole = schema(name)
    return Draft202012Validator({"$schema": whole["$schema"], "$ref": f"#/$defs/{part}", "$defs": whole["$defs"]})


def errors(document: dict, name: str, part: str | None = None) -> list[str]:
    out = []
    validator = _part(name, part) if part else _validator(name)
    for e in sorted(validator.iter_errors(document), key=lambda e: list(e.absolute_path)):
        # where a value fits none of a choice's forms (`oneOf`, `anyOf`), the reason is the closest form's, named where it is
        while e.context:
            e = max(e.context, key=lambda x: (len(x.absolute_path), x.validator != "type"))
        where = "/".join(str(p) for p in e.absolute_path) or "(the document)"
        out.append(f"{where}: {e.message}")
    return out


def validate_order(order: dict) -> dict:
    """An order of either form, by its `schema`: order 2, or order 1 for a version saved before order 2."""
    name = ORDERS.get(order.get("schema"), ORDER) if isinstance(order, dict) else ORDER
    found = errors(order, name)
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


def validate_runs(runs: dict) -> dict:
    found = errors(runs, RUNS)
    if found:
        raise SchemaError("the frame's runs", found)
    return runs


def validate_events(events: dict) -> dict:
    found = errors(events, EVENTS)
    if found:
        raise SchemaError(f"the events of the run {(events.get('run') or {}).get('id')!r}" if isinstance(events, dict) else "the events", found)
    return events


def validate_dialogue(dialogue: dict) -> dict:
    """The dialogue a frame serves for a run (`dialogue/1`)."""
    found = errors(dialogue, DIALOGUE, "dialogue")
    if found:
        raise SchemaError(f"the dialogue of the run {(dialogue.get('run') or {}).get('id')!r}" if isinstance(dialogue, dict) else "the dialogue", found)
    return dialogue


def validate_word(word: dict) -> dict:
    """The owner's word on what waits (`word/1`)."""
    found = errors(word, DIALOGUE, "word")
    if found:
        raise SchemaError("the owner's word", found)
    return word


def validate_said(said: dict) -> dict:
    """The frame's answer to a word it took (`said/1`)."""
    found = errors(said, DIALOGUE, "said")
    if found:
        raise SchemaError("the frame's answer to the word", found)
    return said
