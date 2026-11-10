"""The contract's examples, the frame's own documents and answers as am-llm wrote them (`tests/contract/`): each valid against its
schema, a file the frame serves its bytes as recorded and the feature list names them, and the stub answering each recorded request
with the recorded answer, so that the stub the other tests read cannot drift from the frame."""
import hashlib
import json

import pytest
from fastapi.testclient import TestClient

from am_order.schema import (validate_dialogue, validate_events, validate_features, validate_order, validate_presence, validate_runs,
                             validate_said)
from stub_frame import CONTRACT, HELD, StubFrame, body, example, examples, held_mass

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")
VALIDATE = {"presence-1": validate_presence, "runs-1": validate_runs, "events-1": validate_events, "features-1": validate_features,
            "order-1": validate_order, "dialogue-1 (dialogue/1)": validate_dialogue, "dialogue-1 (said/1)": validate_said}
INDEX = json.loads((CONTRACT / "index.json").read_text(encoding="utf-8"))["examples"]
SCENARIO = example("runs-delete-403")["request"]["path"].removeprefix("/runs/")       # an experiment's run, not an order's

# the state of the held mass order's run each example was recorded in
STATE = {"presence-empty": "empty", "presence-401": "empty", "roles-put-200": "empty", "roles-put-422": "empty", "orders-post-201": "empty",
         "orders-post-422": "empty", "presence-preparing": "preparing", "orders-post-409": "preparing", "dialogue-word-409-running": "preparing",
         "runs-delete-409": "preparing", "runs-preparing": "preparing", "dialogue-parked-again": "parked-again",
         "dialogue-word-accept-200": "parked-again", "dialogue-word-409-stale": "parked-again", "dialogue-word-409-question": "parked-again",
         "runs-parked-again": "parked-again", "events-parked-again": "parked-again", "presence-ended": "accepted", "runs-accepted": "accepted",
         "events-accepted": "accepted", "features-accepted": "accepted", "features-accepted-picture": "accepted",
         "features-accepted-model-stl": "accepted", "features-accepted-model-3mf": "accepted", "dialogue-accepted": "accepted",
         "dialogue-word-409-ended": "accepted", "runs-delete-200": "accepted"}


def test_the_examples_are_the_index_and_the_source_names_the_commit():
    assert examples() == sorted(p.stem for p in CONTRACT.glob("*.json") if p.stem != "index")
    beside = sorted(p.name for p in CONTRACT.iterdir() if p.suffix not in (".json", "") and p.name != "SOURCE")
    assert beside == sorted(INDEX[n]["bytes"] for n in INDEX if INDEX[n].get("bytes"))
    source = (CONTRACT / "SOURCE").read_text(encoding="utf-8")
    assert INDEX and source.split()[1] == json.loads((CONTRACT / "index.json").read_text())["version"]


@pytest.mark.parametrize("name", sorted(INDEX))
def test_every_example_is_valid_against_its_schema(name):
    e = example(name)
    assert e["status"] == INDEX[name]["status"] and f"{e['request']['method']} {e['request']['path']}" in INDEX[name]["request"]
    schema = INDEX[name]["schema"]
    if e.get("bytes"):                                        # a file the frame serves: its bytes as recorded, named by the feature list
        data = (CONTRACT / e["bytes"]).read_bytes()
        assert e["body"] is None and (e["content_type"], e["length"]) == (INDEX[name]["content_type"], INDEX[name]["length"]) == \
            (e["content_type"], len(data)) and e["sha256"] == hashlib.sha256(data).hexdigest()
        features = body("features-accepted")
        named = {f["file"]: f["sha256"] for f in [features["picture"]] + features["models"]}
        assert e["request"]["path"] == f"/runs/{HELD}/features/{features['design']}/{e['request']['path'].rsplit('/', 1)[1]}"
        assert named[e["request"]["path"].rsplit("/", 1)[1]] == e["sha256"]
        return
    if schema is None:
        assert e["status"] >= 400 or name.startswith(("orders-post", "runs-delete")), name
        assert isinstance(e["body"], dict)
        return
    VALIDATE[schema](e["body"])


def recorded(name: str) -> StubFrame:
    """The stub in the state the example was recorded in."""
    stub = held_mass(STATE.get(name, "parked"))
    if name == "roles-put-200":
        stub.presence = body("roles-put-200")                 # a maker placed again where it stands: nothing changes
    if name in ("dialogue-word-403", "runs-delete-403"):
        run = {**body("runs-accepted")["runs"][0], "id": SCENARIO, "order": None,
               "scenario": {"experiment": SCENARIO.split("/")[0], "condition": "open-01"}}
        stub.add_run({k: v for k, v in run.items() if k not in ("makers", "last")}, [], {})
    if name == "orders-post-409":
        stub.orders[HELD] = {"sha256": body("runs-parked")["runs"][0]["order"]["sha256"], "document": example("orders-post-201")["request"]["body"]}
    if name == "orders-post-201":
        stub.orders.clear()
    doc = example(name)["body"]
    if example(name)["status"] < 300 and isinstance(doc, dict) and doc.get("at"):
        stub.at = doc["at"]
    return stub


@pytest.mark.parametrize("name", sorted(INDEX))
def test_the_stub_answers_each_recorded_request_with_the_recorded_answer(name):
    e = example(name)
    q = e["request"]
    stub = recorded(name)
    client = TestClient(stub.app())
    headers = {k: v.replace("<token>", stub.token) for k, v in (q.get("headers") or {}).items()}
    kwargs = {"content": json.dumps(q["body"]).encode()} if "body" in q else {}
    answer = client.request(q["method"], q["path"], headers=headers, **kwargs)
    assert answer.status_code == e["status"], answer.text
    if e.get("bytes"):
        assert answer.headers["content-type"] == e["content_type"] and answer.content == (CONTRACT / e["bytes"]).read_bytes()
        return
    got = answer.json()
    if name.startswith("presence-") and name != "presence-401":
        assert got == e["body"]
    elif name == "orders-post-201":
        assert got == e["body"] and stub.presence["runs"][-1]["state"] == "placed"
    else:
        assert got == e["body"], name


def test_the_owners_words_take_the_run_through_its_parkings():
    stub = held_mass("parked")
    client = TestClient(stub.app())
    auth = {"Authorization": f"Bearer {stub.token}"}
    refuse = example("dialogue-word-refuse-200")
    said = client.post(refuse["request"]["path"], headers=auth, content=json.dumps(refuse["request"]["body"]))
    assert said.json() == refuse["body"]
    again = client.get(f"/runs/{HELD}/dialogue", headers=auth).json()
    assert again["waits"]["dialogue"] == body("dialogue-parked-again")["waits"]["dialogue"]
    stale = example("dialogue-word-409-stale")
    assert client.post(stale["request"]["path"], headers=auth, content=json.dumps(stale["request"]["body"])).status_code == 409
    accept = example("dialogue-word-accept-200")
    said = client.post(accept["request"]["path"], headers=auth, content=json.dumps(accept["request"]["body"]))
    assert said.json() == accept["body"]
    runs = client.get("/runs", headers=auth).json()["runs"]
    assert runs[0]["outcome"] == "accepted" and runs[0]["last"] == 509
    events = client.get(f"/runs/{HELD}/events", params={"after": 330}, headers=auth).json()
    assert [e["seq"] for e in events["events"]] == list(range(331, 510))
