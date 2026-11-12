"""The runs of am-llm as the tool reads them: a record made here in the record's own tables (the tool never imports am-llm),
catalogued, read into events, its state asked at times through the run, and the runs pages served."""
import json
import re
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
CREATE TABLE turn (run_id TEXT, seq INTEGER, kind TEXT, time TEXT, model TEXT, text TEXT, thinking TEXT, usage TEXT, cost REAL, seconds REAL,
    body TEXT DEFAULT '{}', PRIMARY KEY (run_id, seq));
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
    db.execute("INSERT INTO run (id, role, actor, model, prompt, started, ended, outcome) VALUES (?,?,?,?,?,?,?,?)",
               ("run-1", "process_planner", "agent", model, json.dumps({"text": "New in case-1: msg-1 (assignment from design_engineer)"}), at(2), at(120), "done"))
    # the model's turns: it thinks, then its calls follow, then the results; the record writes a turn as it ends
    for seq, kind, t, secs, thinking in ((1, "model", 3, 1, "Read the design first."), (2, "results", 3.2, 0.2, None),
                                         (3, "model", 10, 6, "Three plans to compare on time."), (4, "results", 16, 6, None),
                                         (5, "model", 40, 20, "The -Z orientation is the candidate. " + "It stands on the plate with the lugs up, which keeps the underside clean. " * 8), (6, "results", 43, 3, None),
                                         (7, "model", 100, 50, "Report the binding constraint."), (8, "results", 100.1, 0.1, None)):
        db.execute("INSERT INTO turn (run_id, seq, kind, time, seconds, thinking) VALUES (?,?,?,?,?,?)", ("run-1", seq, kind, at(t), secs, thinking))
    for cid, tool, t, secs, turn, inputs in (("call-r1", "read_design", 3, 0.2, 1, {"design": "bracket-mass@v1"}), ("call-a1", "analyse", 10, 2, 3, {"plan": "plan-1@v1"}),
                                             ("call-a2", "analyse", 12, 2, 3, {"plan": "plan-1@v2"}), ("call-a3", "analyse", 14, 2, 3, {"plan": "plan-1@v3"}),
                                             ("call-p1", "plan_candidate", 40, 3, 5, {"design": "bracket-mass@v1", "orientation": "-Z"})):
        db.execute("INSERT INTO call (id, tool, inputs, result, time, seconds, run_id, turn) VALUES (?,?,?,?,?,?,?,?)", (cid, tool, json.dumps(inputs), "{}", at(t), secs, "run-1", turn))
    db.execute("INSERT INTO message (id, case_id, type, from_level, from_role, from_actor, to_level, to_role, time, body, validation, reasons, received) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
               ("msg-2", "case-1", "report", "coordination", "process_planner", "agent", "design", "design_engineer", at(100),
                json.dumps({"binding_constraint": {"description": "mass binds"}}), "refused", json.dumps([{"rule": 4, "name": "quantities"}]), at(100)))
    db.execute("INSERT INTO message (id, case_id, type, from_level, from_role, from_actor, to_level, to_role, time, body, validation, received) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
               ("msg-3", "case-1", "report", "coordination", "process_planner", "agent", "design", "design_engineer", at(110),
                json.dumps({"binding_constraint": {"description": "mass binds at the time-best settings"}}), "valid", at(110)))
    db.execute("INSERT INTO run (id, role, actor, model, started, ended, outcome) VALUES (?,?,?,?,?,?,?)",
               ("run-2", "design_engineer", "agent", model, at(121), at(300), "done"))
    db.execute("INSERT INTO call (id, tool, inputs, result, time, seconds, run_id) VALUES (?,?,?,?,?,?,?)",
               ("call-reshape", "reshape", json.dumps({"design": "bracket-mass@v1", "lug_thickness": 4}), "{}", at(150), 1.0, "run-2"))
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
    assert pic["jumps"]["next_decision"] == "320.000000" and pic["jumps"]["previous_decision"] is None and pic["jumps"]["start"] == "0"
    assert "Design engineer → Requester: question" in [s["head"] for s in pic["sentences"]]
    assert R.picture_of(run, "bracket-mass@v2") == root / "h1-bracket-mass-20261103T044650Z" / "pictures" / "bracket-mass-v2-open-01.png"
    assert R.picture_of(run, "bracket-mass@v1") is None


def test_the_jumps_step_through_every_event_and_between_decisions(root):
    run = R.read(root, "h1-bracket-mass-20261103T044650Z/open-01")
    # walking "next" from the start, as the links and the arrow keys do, visits every event time and never stands still
    at, visited = run.start - timedelta(seconds=1), []
    while (j := overview(run, R.state(run, at))["jumps"])["next"] is not None:
        at = R.parse_at(run, j["next"])
        visited.append(at)
    assert visited == sorted({e.time for e in run.events})
    # the clock a fraction of a millisecond before an event stands on it: the event is neither previous nor next
    answer = next(e for e in run.events if e.type == "answer")
    j = overview(run, R.state(run, answer.time - timedelta(microseconds=300)))["jumps"]
    assert R.parse_at(run, j["next"]) > answer.time and R.parse_at(run, j["previous"]) < answer.time
    # decisions both ways: at the acceptance the previous decision is the accept_design, at the answer there is none before
    accepted = next(e for e in run.events if e.type == "status")
    j = overview(run, R.state(run, accepted.time))["jumps"]
    assert j["previous_decision"] == "500.000000" and j["next_decision"] is None
    j = overview(run, R.state(run, answer.time))["jumps"]
    assert j["previous_decision"] is None and j["next_decision"] == "500.000000"


def test_the_activity_lines_show_what_a_role_does_between_its_words(root, client):
    run = R.read(root, "h1-bracket-mass-20261103T044650Z/open-01")
    planner = next(b for b in run.bars if b.role == "process_planner")
    # consecutive calls of one word are one act, from the first call to the end of the last
    assert [(a.word, a.count) for a in planner.acts] == [("thinking", 1), ("reading", 1), ("thinking", 1), ("analysing", 3), ("thinking", 1), ("planning", 1), ("thinking", 1)]
    assert planner.acts[3].start == T0 + timedelta(seconds=10) and planner.acts[3].end == T0 + timedelta(seconds=16)
    assert planner.acts[2].start == T0 + timedelta(seconds=4) and planner.acts[2].end == T0 + timedelta(seconds=10)   # the model's six seconds
    assert planner.acts[0].start == T0 + timedelta(seconds=2)                                                      # not before the waking
    # the state at a time knows the act, and the cell says it
    st = R.state(run, T0 + timedelta(seconds=12))
    assert st.activity["process_planner"].word == "analysing"
    pic = overview(run, st)
    cells = {n["role"]: n for n in pic["nodes"]}
    assert cells["process_planner"]["note"] == "analysing"
    assert overview(run, R.state(run, T0 + timedelta(seconds=150.5)))["nodes"][1]["note"] == "reshaping bracket-mass@v1"
    assert overview(run, R.state(run, T0 + timedelta(seconds=30)))["nodes"][2]["note"] == "thinking"
    assert overview(run, R.state(run, T0 + timedelta(seconds=45)))["nodes"][2]["note"] == "awake"
    # one line per role above the axis: the planner's waking as a bar, its acts on it, and the three messages it sent as marks
    lanes = {l["role"]: l for l in pic["axis"]["lanes"]}
    assert list(lanes) == ["requester", "design_engineer", "process_planner"]
    assert len(lanes["process_planner"]["bars"]) == 1 and len(lanes["process_planner"]["acts"]) == 7 and len(lanes["process_planner"]["marks"]) == 3
    assert lanes["process_planner"]["awake"] and not lanes["requester"]["awake"]
    assert [a["past"] for a in lanes["process_planner"]["acts"]] == [True, True, True, True, False, False, False]
    assert {a["colour"] for a in lanes["process_planner"]["acts"] if "thinking" in a["title"]} == {"#b9a7e2"}
    assert all(l["y"] < pic["axis"]["y"] for l in pic["axis"]["lanes"]) and pic["axis"]["top"] < pic["axis"]["lanes"][0]["y"] + 1
    page = client.get("/runs/h1-bracket-mass-20261103T044650Z/open-01?at=12")
    assert 'class="lane"' in page.text and "0:00:10–0:00:16 analysing ×3 · plan-1@v3" in page.text and "reshaping, planning" in page.text
    assert "0:00:04–0:00:10 thinking · 6 s" in page.text


def test_the_turns_can_be_stepped_and_inspected(root, client):
    run = R.read(root, "h1-bracket-mass-20261103T044650Z/open-01")
    planner = next(b for b in run.bars if b.role == "process_planner")
    assert [t.seq for t in planner.turns] == [1, 3, 5, 7] and planner.turns[1].thinking == "Three plans to compare on time."
    assert [a.word for a in planner.turns[1].acts] == ["analysing"] and planner.turns[1].results_end == T0 + timedelta(seconds=16)
    assert planner.prompt == "New in case-1: msg-1 (assignment from design_engineer)"
    # stepping lands on the turns' ends, where the model's choice is known
    j = overview(run, R.state(run, T0 + timedelta(seconds=12)))["jumps"]
    assert j["previous_turn"] == "10.000000" and j["next_turn"] == "40.000000"
    # the panel at a time: the turns ended by then, and where the role stands
    at = lambda s: overview(run, R.state(run, T0 + timedelta(seconds=s)))["wakings"]
    w = at(12)[0]
    assert w["role"] == "process_planner" and [t["n"] for t in w["turns"]] == [1, 2] and w["now"] == "turn 2: the tools answer"
    assert w["turns"][1]["acts"][0]["word"] == "analysing" and w["turns"][1]["acts"][0]["count"] == 3
    assert at(30)[0]["now"] == "turn 3: thinking, 10 s so far"
    assert at(45)[0]["now"] == "at work for 2 s, nothing written yet"
    assert at(3.1)[0]["now"] == "turn 1: the tools answer"
    assert at(400) == []
    page = client.get("/runs/h1-bracket-mass-20261103T044650Z/open-01?at=12")
    assert "Process planner at work" in page.text and "Three plans to compare on time." in page.text and 'data-next-turn="40.000000"' in page.text
    assert "Woken by: New in case-1" in page.text and "the tools answer" in page.text
    assert "<details" not in page.text                                    # short summaries stand whole
    later = client.get("/runs/h1-bracket-mass-20261103T044650Z/open-01?at=45").text
    assert '<details class="more" id="more-process_planner-5-thinking"><summary>more</summary>' in later   # a long one folds, whole
    whole = re.sub(r"<[^>]+>", " ", later.replace("<summary>more</summary>", " "))
    assert len(re.findall(r"keeps\s+the\s+underside\s+clean", whole)) == 8                          # nothing is cut away
    assert "Nobody at work" in client.get("/runs/h1-bracket-mass-20261103T044650Z/open-01?at=400").text


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
    assert ">accepted<" in end and "event ▶</span>" in end                            # at the end there is no next event
    assert client.get("/runs/h1-bracket-mass-20261103T044650Z/open-01/picture/bracket-mass@v2").headers["content-type"] == "image/png"
    assert client.get("/runs/h1-bracket-mass-20261103T044650Z/open-01/picture/bracket-mass@v1").status_code == 404
    assert client.get("/runs/h1-bracket-mass-20261103T044650Z").status_code == 404
    assert client.get("/runs/../examples").status_code == 404


def test_runs_pages_without_a_root(home):
    page = TestClient(create_app(home)).get("/runs")
    assert page.status_code == 200 and "No runs root and no frame" in page.text


def test_the_player_fragment_carries_the_clock(client):
    view = client.get("/runs/h1-bracket-mass-20261103T044650Z/open-01/view?at=300.5")
    assert view.status_code == 200 and view.text.lstrip().startswith("<div id=\"overview\"") and "<html" not in view.text
    assert 'data-at="300.5"' in view.text and 'data-next="301.0"' in view.text and 'data-end="600.0"' in view.text and 'data-live=""' in view.text
    assert 'data-previous="300.000000"' in view.text and 'data-next-event="301.000000"' in view.text and 'data-next-decision="320.000000"' in view.text
    assert 'id="playhead"' in view.text and 'id="clock"' in view.text and 'id="next-in"' in view.text
    page = client.get("/runs/h1-bracket-mass-20261103T044650Z/open-01?at=300.5").text
    assert 'id="player"' in page and 'id="overview"' in page and "follow now" not in page
    live = client.get("/runs/h1-plate-20261101T000000Z/closed-01?at=900").text
    assert "follow now" in live and 'data-live="1"' in live and 'data-end="900.0"' in live     # live, the clock at now is the axis's end
    assert ">now</text>" in live and "following" in live


# ------------------------------------------------------------------------ the run's page laid out for what it shows

RUN_ID = "h1-bracket-mass-20261103T044650Z/open-01"


def test_the_organisation_takes_two_thirds_and_the_side_the_rest(client):
    page = client.get(f"/runs/{RUN_ID}?at=45").text
    assert ".top { flex: 1 1 auto; min-height: 0; display: grid; grid-template-columns: minmax(0, 2fr) minmax(0, 1fr);" in page
    assert '<div class="org">' in page and '<div class="side">' in page
    assert "@media (max-width: 1199px)" in page and ".top { grid-template-columns: minmax(0, 1fr); }" in page   # the side goes below
    # the cells drawn at the page's small size, the picture scaled to its area and never past its natural size by much
    assert 'font-size="11"' in page and 'font-size="12.5"' in page and "max-width: " in page
    assert 'class="legend"' in page and 'id="keys"' not in page                                   # the legend in the player's line


def test_the_side_holds_the_turns_or_the_result_and_nobody_at_work_is_one_line(client):
    awake = client.get(f"/runs/{RUN_ID}?at=45").text
    assert "Process planner at work" in awake and 'class="result' not in awake
    quiet = client.get(f"/runs/{RUN_ID}?at=120.5").text          # the planner asleep, the design engineer not yet awake
    assert '<p class="nobody muted">Nobody at work: the roles sleep; a message or an answer wakes the next.</p>' in quiet
    assert "<h2>Nobody at work</h2>" not in quiet
    end = client.get(f"/runs/{RUN_ID}").text
    assert '<div class="result accepted">' in end and "Nobody at work" not in end


def test_the_time_strip_is_as_high_as_it_needs(client, root):
    page = client.get(f"/runs/{RUN_ID}?at=45").text
    assert '<div class="strip" style="height: 114px">' in page                      # three roles: 18 + 3 × 18 + 12 + 30
    assert 'text-anchor="middle" font-size="11"' in page and 'font-size="13" font-weight="600" fill="#b3261e"' in page
    run = R.read(root, RUN_ID)
    run.roles = list(R.ROLES)
    from am_order.picture import strip_height
    assert strip_height(run) == 114 + 4 * 18                                        # seven roles: 18 px for each further role
    pic = overview(run, R.state(run, T0 + timedelta(seconds=45)))
    assert pic["height"] == 186 and all(l["h"] == 18 for l in pic["axis"]["lanes"])


def test_the_strip_is_drawn_in_percent_of_its_width(client):
    view = client.get(f"/runs/{RUN_ID}/view?at=300").text
    assert 'data-x0="0.0" data-x1="100.0"' in view
    head = re.search(r'<line id="playhead" x1="([0-9.]+)%"', view)
    assert head and 0 < float(head.group(1)) < 100
    late = client.get(f"/runs/{RUN_ID}/view?at=590").text
    assert 'id="clock"' in late and 'text-anchor="end"' in late.split('id="clock"')[1].split(">")[0]


def test_what_happened_last_shows_the_latest_first_and_the_page_keeps_the_readers_place(client):
    view = client.get(f"/runs/{RUN_ID}/view?at=600").text
    events = view.split("What happened last", 1)[1].split("</ul>", 1)[0]
    clocks = re.findall(r'<span class="clock">([0-9:]+)</span>', events)
    assert len(clocks) > 2 and clocks == sorted(clocks, reverse=True)
    page = client.get(f"/runs/{RUN_ID}?at=45").text
    assert "newSide.scrollTop = sideTop" in page and "P.turnsAtEnd" in page and ".side .wakings { max-height: 45vh; overflow-y: auto;" in page
