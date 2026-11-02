"""The fixed vocabularies: the checklist's headings (Pahl & Beitz) and the quantities with their units and value forms.

The quantities are a table (`vocab/quantities.json`), extensible by adding a row; nothing in it is particular to a process.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

HERE = Path(__file__).parent / "vocab"
VALUE_FORMS = ("at_most", "at_least", "band", "equals", "holds")
OBJECT_KINDS = ("face", "hole", "slot", "edge", "wall", "part")
VOID_KINDS = ("hole", "slot")            # an object that is the absence of material
SOLID_KINDS = ("wall",)                  # an object that is material; a face and an edge bound it, the part holds everything
CLASSES = ("demand", "wish")
SOURCES = ("requester", "standard", "project", "reference")
MANDATES = ("held", "interval", "release")


@lru_cache(maxsize=1)
def _headings() -> dict:
    return json.loads((HERE / "headings.json").read_text())


@lru_cache(maxsize=1)
def _quantities() -> dict:
    return json.loads((HERE / "quantities.json").read_text())


def headings() -> list[dict]:
    """The checklist's headings in their order: [{id, name, covers}]."""
    return list(_headings()["headings"])


def heading_ids() -> list[str]:
    return [h["id"] for h in headings()]


def heading_name(hid: str | None) -> str:
    return next((h["name"] for h in headings() if h["id"] == hid), hid or "")


def quantities() -> dict:
    """{quantity: {text, units, values, dims?}}."""
    return dict(_quantities()["quantities"])


def quantity(name: str | None) -> dict | None:
    return _quantities()["quantities"].get(name) if name else None


def loads() -> dict:
    """{load type: {units}}."""
    return dict(_quantities()["loads"])
