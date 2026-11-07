"""The runs of am-llm as the tool reads them: a record made here in the record's own tables (the tool never imports am-llm),
catalogued, read into events, its state asked at times through the run, and the runs pages served."""
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from am_order import Home
from am_order import runs as R
from am_order.picture import overview
from am_order.web.app import create_app

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")
T0 = datetime(2026, 11, 3, 4, 46, 50, tzinfo=timezone.utc)


def at(seconds: float) -> str:
    return (T0 + timedelta(seconds=seconds)).isoformat().replace("+00:00", "Z")


SCHEMA = """
CREATE TABLE message (id TEXT PRIMARY KEY, case_id TEXT, type TEXT, from_level TEXT, from_role TEXT, from_actor TEXT, to_level TEXT,
    to_role TEXT, time TEXT, in_reply_to TEXT, body TEXT, validation TEXT, reasons TEXT DEFAULT '[]', received TEXT);
CREATE TABLE call (id TEXT PRIMARY KEY, tool TEXT, inputs TEXT, result TEXT, error INTEGER DEFAULT 0, time TEXT, seconds REAL, run_id TEXT,
    turn INTEGER, cites TEXT, cache TEXT);
CREATE TABLE run (id TEXT PRIMARY KEY, role TEXT, actor TEXT, model TEXT, settings TEXT, prompt TEXT, case_id TEXT, started TEXT, ended TEXT,
    outcome TEXT, usage TEXT, context_sha256 TEXT);
CREATE TABLE design (id TEXT PRIMARY KEY, lineage TEXT, version INTEGER, parent TEXT, made_by_role TEXT, made_by_actor TEXT, time TEXT,
    content_sha256 TEXT, record TEXT, model_sha256 TEXT, source TEXT, material TEXT, parameters TEXT, brief_call TEXT);
CREATE TABLE plan (id TEXT PRIMARY KEY, lineage TEXT, version INTEGER, run_id TEXT, case_id TEXT, design_id TEXT, machine_class TEXT,
    placement TEXT, class_settings TEXT, content_sha256 TEXT, plan_sha256 TEXT, shim TEXT, call_id TEXT, time TEXT);
CREATE TABLE case_state (case_id TEXT PRIMARY KEY, phase TEXT, negotiation TEXT, sender_role TEXT, recipient_role TEXT,
    binding_assignment TEXT, design_id TEXT, mandate TEXT, accepted_plan TEXT, status TEXT, referred INTEGER DEFAULT 0,
    requirement_version INTEGER, proposed_version INTEGER, messages INTEGER, last_message TEXT);
"""


def make_run(folder: Path, *, running: bool = False, decision_free: bool = False) -> Path:
    """A run as the experiment runner leaves it: the JSON files and a record with a brief, two design versions (one before the
    run), an assignment, a refused and a valid report, a question to the requester and its answer, an acceptance, a status."""
    folder.mkdir(parents=True)
    (folder / "run.json").write_text(json.dumps({"created": at(0), "lineages": ["bracket-mass"], "settings": {"negotiation": "open", "held": "off"}}))
    if running:
        (folder / "status.json").write_text(json.dumps({"status": "running"}))
    else:
        (folder / "status.json").write_text(json.dumps({"status": "done", "ended": at(600)}))
        (folder / "result.json").write_text(json.dumps({"outcome": "stopped", "reason": "frame"} if decision_free else {"outcome": "accepted"}))
    db = sqlite3.connect(folder / "record.db")
    db.executescript(SCHEMA)
    model = "scripted:the reference's routine without a decision maker" if decision_free else "claude:claude-haiku-5-5"
    db.execute("INSERT INTO design (id, lineage, version, made_by_role, made_by_actor, time, content_sha256, record) VALUES (?,?,?,?,?,?,?,?)",
               ("bracket-mass@v1", "bracket-mass", 1, "design_engineer", "operator", at(-86400), "a", "{}"))
    db.execute("INSERT INTO design (id, lineage, version, made_by_role, made_by_actor, time, content_sha256, record) VALUES (?,?,?,?,?,?,?,?)",
               ("bracket-mass@v2", "bracket-mass", 2, "design_engineer", "agent", at(200), "b", "{}"))
    db.execute("INSERT INTO call (id, tool, inputs, result, time) VALUES (?,?,?,?,?)",
               ("call-brief", "brief", json.dumps({"lineage": "bracket-mass", "text": "A bracket that carries a hanging load"}), "{}", at(0)))
    requirements = [{"id": "req-1", "note": "order bracket-mass@3/M1"}]
    db.execute("INSERT INTO message (id, case_id, type, from_level, from_role, from_actor, to_level, to_role, time, body, validation, received) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
               ("msg-1", "case-1", "assignment", "design", "design_engineer", "operator", "coordination", "process_planner", at(1),
                json.dumps({"goal": "Plan the bracket", "basis": {"design": "bracket-mass@v1"}, "requirements": requirements}), "valid", at(1)))
    db.execute("INSERT INTO run (id, role, actor, model, started, ended, outcome) VALUES (?,?,?,?,?,?,?)",
               ("run-1", "process_planner", "agent", model, at(2), at(120), "done"))
    db.execute("INSERT INTO message (id, case_id, type, from_level, from_role, from_actor, to_level, to_role, time, body, validation, reasons, received) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
               ("msg-2", "case-1", "report", "coordination", "process_planner", "agent", "design", "design_engineer", at(100),
                json.dumps({"binding_constraint": {"description": "mass binds"}}), "refused", json.dumps([{"rule": 4, "name": "quantities"}]), at(100)))
    db.execute("INSERT INTO message (id, case_id, type, from_level, from_role, from_actor, to_level, to_role, time, body, validation, received) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
               ("msg-3", "case-1", "report", "coordination", "process_planner", "agent", "design", "design_engineer", at(110),
                json.dumps({"binding_constraint": {"description": "mass binds at the time-best settings"}}), "valid", at(110)))
    db.execute("INSERT INTO run (id, role, actor, model, started, ended, outcome) VALUES (?,?,?,?,?,?,?)",
               ("run-2", "design_engineer", "agent", model, at(121), at(300), "done"))
    db.execute("INSERT INTO call (id, tool, inputs, result, time, run_id) VALUES (?,?,?,?,?,?)",
               ("call-ask", "ask_requester", json.dumps({"design": "bracket-mass@v2", "question": "May the mass demand be raised?"}), "{}", at(250), "run-2"))
    db.execute("INSERT INTO run (id, role, actor, model, started, ended, outcome) VALUES (?,?,?,?,?,?,?)",
               ("run-3", "requester", "agent", model, at(301), at(330), "done"))
    db.execute("INSERT INTO call (id, tool, inputs, result, time, run_id) VALUES (?,?,?,?,?,?)",
               ("call-answer", "answer_requester", json.dumps({"question": "call-ask", "text": "Yes, to 22 g for the search."}), "{}", at(320), "run-3"))
    db.execute("INSERT INTO call (id, tool, inputs, result, time, run_id) VALUES (?,?,?,?,?,?)",
               ("call-accept", "accept_design", json.dumps({"design": "bracket-mass@v2", "text": "Accepted as shown."}), "{}", at(500), "run-3"))
    db.execute("INSERT INTO message (id, case_id, type, from_level, from_role, from_actor, to_level, to_role, time, body, validation, received) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
               ("msg-4", "case-1", "status", "coordination", "process_planner", "agent", "design", "design_engineer", at(590),
                json.dumps({"state": "accepted", "plan": "plan-1@v3"}), "valid", at(590)))
    db.execute("INSERT INTO case_state (case_id, phase, negotiation, sender_role, recipient_role, binding_assignment, design_id, mandate, accepted_plan, requirement_version, messages) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
               ("case-1", "execution", "open", "design_engineer", "process_planner", "msg-1", "bracket-mass@v2", json.dumps({"parameters": {}}), "plan-1@v3", 1, 4))
    db.commit()
    db.close()
    return folder


@pytest.fixture
def root(tmp_path) -> Path:
    r = tmp_path / "runs"
    make_run(r / "h1-bracket-mass-20261103T044650Z" / "open-01")
    make_run(r / "h1-bracket-mass-20261103T044650Z" / "default-01", decision_free=True)
    make_run(r / "h1-plate-20261101T000000Z" / "closed-01", running=True)
    (r / "h1-plate-20261101T000000Z" / "closed-01" / "run.json").write_text(json.dumps({"created": at(0), "lineages": ["plate"], "settings": {"negotiation": "closed"}}))
    pictures = r / "h1-bracket-mass-20261103T044650Z" / "pictures"
    pictures.mkdir()
    (pictures / "bracket-mass-v2-open-01.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    return r


def test_catalogue_groups_runs_by_experiment_newest_first(root):
    cat = R.catalogue(root)
    assert [x.name for x in cat] == ["h1-bracket-mass-20261103T044650Z", "h1-plate-20261101T000000Z"]
    bracket = cat[0]
    assert bracket.lineages == ["bracket-mass"]
    assert [r.condition for r in bracket.runs] == ["default-01", "open-01"]
    done = next(r for r in bracket.runs if r.condition == "open-01")
    assert (done.status, done.outcome, done.negotiation, done.minutes) == ("done", "accepted", "open", 10.0)
    live = cat[1].runs[0]
    assert (live.status, live.ended, live.outcome) == ("running", None, None)
    assert R.decision_makers(root / done.id) == {"process_planner": "claude-haiku-5-5", "design_engineer": "claude-haiku-5-5", "requester": "claude-haiku-5-5"}
    assert R.decision_makers(root / bracket.runs[0].id)["design_engineer"] == "none"
    assert R.catalogue(root / "nowhere") == []


def test_resolve_stays_under_the_root(root):
    assert R.resolve(root, "h1-bracket-mass-20261103T044650Z/open-01") is not None
    assert R.resolve(root, "h1-bracket-mass-20261103T044650Z") is None          # an experiment, not a run
    assert R.resolve(root, "../runs/h1-bracket-mass-20261103T044650Z/open-01") is None
    assert R.resolve(root, "/etc") is None
    assert R.read(root, "nothing/here") is None


def test_read_gives_the_events_in_time_order_from_the_runs_start(root):
    run = R.read(root, "h1-bracket-mass-20261103T044650Z/open-01")
    assert run.start == T0 and run.end == T0 + timedelta(seconds=600)
    assert run.order == ("bracket-mass", 3)
    assert run.accepted_plan == "plan-1@v3"
    assert run.roles == ["requester", "design_engineer", "process_planner"]
    kinds = [(e.kind, e.type) for e in run.events]
    assert ("design", "design") in kinds and all(e.time >= T0 for e in run.events)       # v1, made the day before, is not an event
    assert [e.time for e in run.events] == sorted(e.time for e in run.events)
    refused = next(e for e in run.events if not e.valid)
    assert refused.text.startswith("refused, rule 4 quantities")
    assert [e.type for e in run.decisions()] == ["answer", "acceptance", "status"]
    question = next(e for e in run.events if e.type == "question")
    assert (question.sender, question.recipient, question.text) == ("design_engineer", "requester", "May the mass demand be raised?")
    answer = next(e for e in run.events if e.type == "answer")
    assert answer.text == "Yes, to 22 g for the search."           # the answer's text, not the call id it answers


def test_state_at_a_time_is_what_the_rows_before_it_say(root):
    run = R.read(root, "h1-bracket-mass-20261103T044650Z/open-01")
    beginning = R.state(run, T0)
    assert beginning.design == "bracket-mass@v1" and beginning.awake == {} and beginning.next.time == T0 + timedelta(seconds=1)
    planning = R.state(run, T0 + timedelta(seconds=50))
    assert list(planning.awake) == ["process_planner"] and planning.design == "bracket-mass@v1"
    assert planning.traffic == {("requester", "design_engineer"): {"brief": 1}, ("design_engineer", "process_planner"): {"assignment": 1}}
    parked = R.state(run, T0 + timedelta(seconds=300.5))
    assert parked.awake == {} and parked.design == "bracket-mass@v2"
    assert parked.waiting == {"requester": "question from design engineer waits"}
    answered = R.state(run, T0 + timedelta(seconds=321))
    assert "requester" not in answered.waiting and list(answered.awake) == ["requester"]
    end = R.state(run, run.end)
    assert end.outcome == "accepted" and end.next is None and end.seen == len(run.events)
    assert end.traffic[("process_planner", "design_engineer")] == {"report": 1, "status": 1}      # the refused report is not traffic


def test_a_decision_free_run_shows_where_it_stopped(root):
    run = R.read(root, "h1-bracket-mass-20261103T044650Z/default-01")
    assert run.decision_makers["process_planner"] == "none"
    end = R.state(run, run.end)
    assert end.outcome == "stopped (frame)"


def test_the_overview_has_a_cell_per_role_the_traffic_and_the_axis(root):
    run = R.read(root, "h1-bracket-mass-20261103T044650Z/open-01")
    st = R.state(run, T0 + timedelta(seconds=300.5))
    pic = overview(run, st)
    cells = {n["role"]: n for n in pic["nodes"]}
    assert cells["requester"]["mode"] == "waiting" and cells["process_planner"]["mode"] == "idle"
    assert cells["requester"]["y"] < cells["design_engineer"]["y"] < cells["process_planner"]["y"]
    assert cells["design_engineer"]["maker"] == "claude-haiku-5-5"
    words = {e["words"] for e in pic["edges"]}
    assert "1 assignment" in words and "1 report" in words
    assert any(e["bold"] for e in pic["edges"])                        # the latest thing said, the question, is drawn bold
    ax = pic["axis"]
    assert len(ax["marks"]) == len(run.events) and ax["clock"] == "0:05:00" and ax["next"]["what"] == "woke"
    assert ax["x0"] < ax["head"] < ax["x1"]
    assert pic["jumps"]["next_decision"] == "320.000" and pic["jumps"]["start"] == "0"
    assert "Design engineer → Requester: question" in [s["head"] for s in pic["sentences"]]
    assert R.picture_of(run, "bracket-mass@v2") == root / "h1-bracket-mass-20261103T044650Z" / "pictures" / "bracket-mass-v2-open-01.png"
    assert R.picture_of(run, "bracket-mass@v1") is None


def test_parse_at_takes_seconds_or_a_time_and_defaults_to_the_end(root):
    run = R.read(root, "h1-bracket-mass-20261103T044650Z/open-01")
    assert R.parse_at(run, None) == run.end
    assert R.parse_at(run, "90") == T0 + timedelta(seconds=90)
    assert R.parse_at(run, at(45)) == T0 + timedelta(seconds=45)
    live = R.read(root, "h1-plate-20261101T000000Z/closed-01")
    assert live.live and live.end == T0 + timedelta(seconds=590)          # the last row the log knows


@pytest.fixture
def client(home, root):
    return TestClient(create_app(home, None, root))


def test_runs_pages(client, root):
    page = client.get("/runs").text
    assert "2 experiments, 3 runs" in page and "h1-bracket-mass-20261103T044650Z" in page and "1 accepted" in page and "1 stopped" in page
    assert client.get("/runs?product=plate").text.count("<tr>") == 2                     # the heading row and one experiment
    expanded = client.get("/runs?experiment=h1-bracket-mass-20261103T044650Z").text
    assert "design engineer: claude-haiku-5-5" in expanded and "design engineer: none" in expanded and "(frame)" in expanded
    run = client.get("/runs/h1-bracket-mass-20261103T044650Z/open-01?at=300.5")
    assert run.status_code == 200
    assert "question from design engineer waits" in run.text and "bracket-mass@v2" in run.text and "0:05:00" in run.text
    assert 'src="/runs/h1-bracket-mass-20261103T044650Z/open-01/picture/bracket-mass@v2"' in run.text
    assert "next in 1 s · woke" in run.text          # the requester wakes at 301
    end = client.get("/runs/h1-bracket-mass-20261103T044650Z/open-01").text
    assert ">accepted<" in end and "next event ▶</span>" in end                            # at the end there is no next event
    assert client.get("/runs/h1-bracket-mass-20261103T044650Z/open-01/picture/bracket-mass@v2").headers["content-type"] == "image/png"
    assert client.get("/runs/h1-bracket-mass-20261103T044650Z/open-01/picture/bracket-mass@v1").status_code == 404
    assert client.get("/runs/h1-bracket-mass-20261103T044650Z").status_code == 404
    assert client.get("/runs/../examples").status_code == 404


def test_runs_pages_without_a_root(home):
    page = TestClient(create_app(home)).get("/runs")
    assert page.status_code == 200 and "No runs root is set" in page.text
