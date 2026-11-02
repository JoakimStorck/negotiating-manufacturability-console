"""Fixtures: the examples (`examples/`, written by am-llm) copied into a home of the test's own."""
import shutil
from pathlib import Path

import pytest

from am_order import Home

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"
REFERENCE = ("plate", "l-bracket", "bracket-ge", "bracket-mass")


@pytest.fixture
def home_dir(tmp_path) -> Path:
    target = tmp_path / "home"
    shutil.copytree(EXAMPLES, target)
    return target


@pytest.fixture
def home(home_dir) -> Home:
    return Home(home_dir)


@pytest.fixture
def own(home_dir) -> Home:
    return Home(home_dir, allow_own=True)


@pytest.fixture
def bracket(home):
    return home.load("bracket-ge")
