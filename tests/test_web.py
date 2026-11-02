"""The web app, driven as a person drives it: a new product against a library part's feature list, its refusals seen and cleared,
proposals confirmed and rejected, saved, revised, compared; the interaction log written and read back. And the products page on
the examples, an own product refused, `am-order serve` itself."""
import html
import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.request
from collections import Counter
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from am_order import Home
from am_order.web.app import create_app

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")
P = "/products/artifact"
DESIGN = "nist-am-artifact@v1"


def refusals(html: str) -> list[str]:
    """The refusals the page shows in its checks panel: 'rule item'."""
    aside = html.split('<aside id="refusals">', 1)[1] if '<aside id="refusals">' in html else ""
    return re.findall(r'<div class="refusal"><b>([a-z]+)</b> ([A-Za-z0-9_]+):', aside)


def metric_form(**kw) -> dict:
    form = {"class": "demand", "heading": "geometry", "text": "", "object": "", "quantity": "", "unit": "", "comparator": "", "value": "",
            "lower": "", "nominal": "", "upper": "", "load_type": "", "magnitude": "", "load_unit": "", "direction": "", "at": "",
            "under_name": "", "under_text": "", "source": "", "verified_by": "", "mandate": "held", "far": ""}
    form.update(kw)
    return form


def course(client: TestClient) -> dict:
    """A new product, as a person makes it in the app; returns what each step showed."""
    seen = {}
    r = client.post("/products", data={"lineage": "artifact", "name": "Test artifact", "group": "trials",
                                       "purpose": "A test artifact that shows how well the lab's printer makes holes and flat faces"})
    assert r.status_code == 200 and "Test artifact" in r.text
    seen["created"] = refusals(r.text)
    for text, imp, group in (("Locates on the centre pin", 5, "Fits the fixture"), ("Shows how well holes are made", 4, "Shows accuracy"),
                             ("Stands flat on the table", 3, "Fits the fixture")):
        r = client.post(f"{P}/needs", data={"text": text, "importance": str(imp), "group": group})
    for name, kind, count, datum, place in (("artifact", "part", 1, "", "box 0 0 0 141.5 141.5 17"), ("central hole", "hole", 1, "", ""),
                                             ("lateral hole", "hole", 2, "", ""), ("base", "face", 1, "A", "")):
        r = client.post(f"{P}/objects", data={"name": name, "kind": kind, "count": str(count), "datum": datum, "text": "", "place": place})
    assert r.status_code == 200
    # metrics heading by heading
    for heading, text in (("geometry", "fits the printer's bed"), ("geometry", "the central hole"), ("geometry", "the lateral holes"),
                          ("geometry", "the base flat"), ("production", "printed in an hour"), ("material", "in PLA")):
        r = client.post(f"{P}/metrics", data={"heading": heading, "text": text}, follow_redirects=True)
    assert r.url.path == f"{P}/metrics/M6"
    client.post(f"{P}/metrics/M1", data=metric_form(text="fits the printer's bed", object="O1", quantity="envelope", unit="mm",
                                                    comparator="at_most", value="141.5, 141.5, 17", source="standard: NIST AM test artifact",
                                                    verified_by="calliper", carried_by="O1"))
    r = client.post(f"{P}/metrics/M2", data=metric_form(text="the central hole", object="O2", quantity="diameter", comparator="band",
                                                        lower="9.9", nominal="10", upper="10.1", needs="N1", source="requester: the fixture's pin",
                                                        verified_by="pin gauge", carried_by="O2", mandate="interval", far="9.95, 10.05"))
    seen["metric without a unit"] = [x for x in refusals(r.text) if x[1] == "M2"]
    r = client.post(f"{P}/metrics/M2", data=metric_form(text="the central hole", object="O2", quantity="diameter", unit="mm", comparator="band",
                                                        lower="9.9", nominal="10", upper="10.1", needs="N1", source="requester: the fixture's pin",
                                                        verified_by="pin gauge", carried_by="O2", mandate="interval", far="9.95, 10.05"))
    seen["interval inside the ideal"] = [x for x in refusals(r.text) if x[1] == "M2"]
    r = client.post(f"{P}/metrics/M2", data=metric_form(text="the central hole", object="O2", quantity="diameter", unit="mm", comparator="band",
                                                        lower="9.9", nominal="10", upper="10.1", needs="N1", source="requester: the fixture's pin",
                                                        verified_by="pin gauge", carried_by="O2", mandate="interval", far="9.8, 10.2"))
    seen["M2 cleared"] = [x for x in refusals(r.text) if x[1] == "M2"]
    client.post(f"{P}/metrics/M3", data={**metric_form(text="the lateral holes", object="O3", quantity="position", unit="mm", comparator="at_most",
                                                       value="0.2", source="requester: the side fixtures", verified_by="CMM against datum A"),
                                         "datums": "O4", "carried_by": "O3"})
    client.post(f"{P}/metrics/M4", data=metric_form(text="the base flat", object="O4", quantity="flatness", unit="mm", comparator="at_most",
                                                    value="0.1", needs="N3", source="requester", verified_by="surface plate", carried_by="O4"))
    r = client.post(f"{P}/metrics/M5", data=metric_form(**{"class": "wish"}, heading="production", text="printed in an hour", object="O1",
                                                        quantity="production_time", unit="min", comparator="at_most", value="60",
                                                        source="project: the lab's day", verified_by="the print's log", carried_by="O1"))
    seen["a wish held"] = [x for x in refusals(r.text) if x[1] == "M5"]
    client.post(f"{P}/metrics/M5", data=metric_form(**{"class": "wish"}, heading="production", text="printed in an hour", object="O1",
                                                    quantity="production_time", unit="min", comparator="at_most", value="60",
                                                    source="project: the lab's day", verified_by="the print's log", carried_by="O1", mandate="release"))
    r = client.post(f"{P}/metrics/M6", data=metric_form(heading="material", text="in PLA", object="O1", quantity="material", unit="-",
                                                        comparator="equals", value="Prusament PLA", source="project: the lab's stock",
                                                        verified_by="the filament's label", carried_by="O1"))
    before = refusals(r.text)
    seen["before the matrix"] = sorted({x for x in before if x[0] in ("covered", "complete")})
    # the matrix by its cells
    r = client.post(f"{P}/matrix", data={"need": "N2", "metric": "M3", "on": "1"})
    r = client.post(f"{P}/matrix", data={"need": "N2", "metric": "M2", "on": "1"})
    seen["covered cleared"] = [x for x in refusals(r.text) if x[0] == "covered"]
    # the headings nothing applies to
    statements = {f"h_{h}": "Nothing applies to a test artifact." for h in
                  ("kinematics", "forces", "energy", "signals", "safety", "ergonomics", "quality_control", "assembly", "transport", "operation",
                   "maintenance", "recycling", "costs", "schedules")}
    r = client.post(f"{P}/headings", data=statements)
    seen["after the headings"] = refusals(r.text)
    # the binding against the library part's feature list
    r = client.post(f"{P}/binding", data={"action": "bind", "design": DESIGN})
    assert 'src="/features/nist-am-artifact@v1/picture.png"' in r.text and "model.3mf" in r.text
    seen["bound by name"] = "central-hole" in r.text and "declared" in r.text
    seen["proposals before"] = refusals(r.text)
    r = client.post(f"{P}/binding", data={"action": "confirm", "object": "O3", "feature": "lateral-hole-d3"})
    r = client.post(f"{P}/binding", data={"action": "confirm", "object": "O3", "feature": "lateral-hole-d6"})
    r = client.post(f"{P}/binding", data={"action": "reject", "object": "O4", "feature": "surface-6"})
    r = client.post(f"{P}/binding", data={"action": "confirm", "object": "O4", "feature": "surface-1"})
    r = client.post(f"{P}/binding", data={"action": "confirm", "object": "O2", "feature": "central-hole"})
    seen["after the binding"] = refusals(r.text)
    r = client.post(f"{P}/save")
    seen["saved"] = re.search(r"saved as revision \d+", r.text).group(0)
    # revised: a value tightened, a mandate widened, a need dropped, a metric added
    client.post(f"{P}/metrics/M2", data=metric_form(text="the central hole", object="O2", quantity="diameter", unit="mm", comparator="band",
                                                    lower="9.95", nominal="10", upper="10.05", needs=["N1", "N2"], source="requester: the fixture's pin",
                                                    verified_by="pin gauge", carried_by="O2", mandate="interval", far="9.8, 10.2"))
    client.post(f"{P}/metrics/M4", data=metric_form(text="the base flat", object="O4", quantity="flatness", unit="mm", comparator="at_most",
                                                    value="0.1", needs="N3", source="requester", verified_by="surface plate", carried_by="O4",
                                                    mandate="interval", far="0.2"))
    r = client.post(f"{P}/needs/N3", data={"action": "drop"})
    seen["a dropped need still cited"] = [x for x in refusals(r.text) if x[0] in ("named", "necessary")]
    r = client.post(f"{P}/metrics/M4", data=metric_form(text="the base flat", object="O4", quantity="flatness", unit="mm", comparator="at_most",
                                                        value="0.1", source="requester", verified_by="surface plate", carried_by="O4",
                                                        mandate="interval", far="0.2"))
    r = client.post(f"{P}/metrics/M4", data=metric_form(text="the base flat", object="O4", quantity="flatness", unit="mm", comparator="at_most",
                                                        value="0.1", source="standard: ISO 1101, the face as datum A", verified_by="surface plate",
                                                        carried_by="O4", mandate="interval", far="0.2"))
    r = client.post(f"{P}/metrics", data={"heading": "geometry", "text": "the central hole round"}, follow_redirects=True)
    r = client.post(f"{P}/metrics/M7", data=metric_form(text="the central hole round", object="O2", quantity="roundness", unit="mm",
                                                        comparator="at_most", value="0.05", needs="N2", source="requester", verified_by="CMM",
                                                        carried_by="O2"))
    seen["before the second save"] = refusals(r.text)
    r = client.post(f"{P}/save")
    seen["saved again"] = re.search(r"saved as revision \d+", r.text).group(0)
    r = client.get(f"{P}/history?a=1&b=2")
    seen["changes"] = [html.unescape(c) for c in re.findall(r"<li>([^<]+)</li>", r.text.split("<h2>The change record", 1)[0])]
    r = client.get("/compare?a=artifact@1&b=artifact")
    seen["compare"] = "From artifact@1 to artifact" in r.text
    return seen


@pytest.fixture
def app(home_dir, tmp_path):
    return create_app(Home(home_dir), tmp_path / "log")


def test_a_new_product_by_a_person(app, tmp_path, home_dir):
    seen = course(TestClient(app))
    assert ("unambiguous", "M2") in seen["metric without a unit"]
    assert seen["interval inside the ideal"] == [("consistent", "M2")] and seen["M2 cleared"] == []
    assert seen["a wish held"] == [("consistent", "M5")]
    assert ("covered", "N2") in seen["before the matrix"] and ("complete", "transport") in seen["before the matrix"]
    assert seen["covered cleared"] == [] and seen["after the headings"] == []
    assert seen["bound by name"] and ("bound", "O3") in seen["proposals before"] and ("bound", "O4") in seen["proposals before"]
    assert seen["after the binding"] == [] and seen["saved"] == "saved as revision 1"
    assert ("named", "M4") in seen["a dropped need still cited"]
    assert seen["before the second save"] == [] and seen["saved again"] == "saved as revision 2"
    changes = " | ".join(seen["changes"])
    for expected in ("value M2: 9.9 to 10.1 mm (nominal 10) -> 9.95 to 10.05 mm (nominal 10)", "mandate M4: held -> interval to 0.2 mm",
                     "need N3 dropped", "metric M7 added: roundness at most 0.05 mm"):
        assert expected in changes
    assert seen["compare"]
    order = Home(home_dir).load("artifact")
    assert order.binding("O4")["rejected"] == ["surface-6"] and order.features_of("O3") == ["lateral-hole-d3", "lateral-hole-d6"]
    # the interaction log, read back
    log = [json.loads(line) for path in (tmp_path / "log").glob("*.jsonl") for line in path.read_text(encoding="utf-8").splitlines()]
    assert len({e["session"] for e in log}) == 1 and all(set(e) >= {"time", "session", "page", "action", "refusals"} for e in log)
    actions = Counter(e["action"].split(" ")[0] for e in log)
    assert actions["save"] == 2 and actions["edit"] >= 8 and actions["confirm"] == 4 and actions["reject"] == 1
    assert log[-3]["action"] == "save" and log[-3]["refusals"] == []
    summary = summarise(log)
    assert summary["cleared"] == summary["seen"]


def summarise(log: list[dict]) -> dict:
    """Each refusal by its rule and item: the action that first showed it and the one after which it was gone."""
    first, gone, active = {}, {}, set()
    for i, e in enumerate(log):
        now = {(r["rule"], r["item"]) for r in e["refusals"]}
        if e["page"].startswith("/compare") or e["action"] == "view" and not now and active:
            continue
        for k in now - active:
            first.setdefault(k, i)
        for k in active - now:
            gone[k] = i
        active = now
    return {"actions": len(log), "seen": len(first), "cleared": len([k for k in first if k in gone and k not in active]),
            "by_rule": dict(Counter(k[0] for k in first)), "first": {f"{k[0]} {k[1]}": v for k, v in first.items()},
            "gone": {f"{k[0]} {k[1]}": v for k, v in gone.items()}}


def test_the_products_page_shows_the_four_in_their_group(app):
    html = TestClient(app).get("/").text
    group = html.split("<b>H1</b>", 1)[1].split("</ul>", 1)[0]
    assert all(f"?selected={p}" in group for p in ("plate", "l-bracket", "bracket-ge", "bracket-mass"))
    html = TestClient(app).get("/?selected=bracket-ge").text
    assert 'src="/products/bracket-ge/picture"' in html and "Derive into user" in html


def test_an_own_product_is_refused_and_a_derived_one_edited(app, home_dir):
    c = TestClient(app)
    r = c.post("/products/bracket-ge/metrics/M5", data=metric_form(object="O2", quantity="flatness", unit="mm", comparator="at_most", value="0.1"))
    assert r.status_code == 403 and "read only" in r.text
    r = c.post("/products/bracket-ge/derive", data={"lineage": "mine", "name": "Mine"})
    assert r.status_code == 200 and r.url.path == "/products/mine"
    c.post("/products/mine/manage", data={"action": "tag", "add": "trial"})
    c.post("/products/mine/manage", data={"action": "move", "group": "trials"})
    c.post("/products/mine/manage", data={"action": "archive"})
    f = Home(home_dir).facets("mine")
    assert (f["category"], f["group"], f["tags"]) == ("archive", "trials", ["engine bracket", "trial"])
    assert c.get("/products/bracket-ge/binding").status_code == 200
    assert c.get("/features/bracket-ge@v4/model.3mf").content[:2] == b"PK"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_serve_on_the_examples(home_dir):
    port = _free_port()
    proc = subprocess.Popen([sys.executable, "-m", "am_order", "--home", str(home_dir), "serve", "--port", str(port)],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env={**os.environ, "PYTHONUNBUFFERED": "1"})
    try:
        for _ in range(100):
            try:
                html = urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=1).read().decode()
                break
            except OSError:
                time.sleep(0.1)
        else:
            raise AssertionError("am-order serve did not answer")
        assert "<b>H1</b>" in html and all(f"?selected={p}" in html for p in ("plate", "l-bracket", "bracket-ge", "bracket-mass"))
    finally:
        proc.terminate()
        proc.wait(timeout=10)
