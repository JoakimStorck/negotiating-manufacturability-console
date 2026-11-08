"""The tool connected to a standing frame, against a frame stubbed here (`stub_frame`): the client and its four ways of going
wrong, the overview's empty state from presence with `down` on the frame's clock, the catalogue, a run read from the frame's
events equal to the same run read from its folder, played back and followed, an order placed, and the command line."""
import json
from datetime import timedelta

import httpx
import pytest
from fastapi.testclient import TestClient

from am_order import runs as R
from am_order.cli import main
from am_order.frame import Frame, FrameError, Reading, part_state, read_token
from am_order.picture import overview
from am_order.web.app import create_app
from stub_frame import StubFrame, presence, record_events, run_document
from test_runs import T0, at, make_run

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")
# the frame's clock stands years from the tool's, so that anything read on the tool's clock shows
FRAME_AT = "2031-05-04T10:00:00Z"
RUN = "h1-bracket-mass/open-01"


@pytest.fixture
def folder(tmp_path):
    return make_run(tmp_path / "runs" / "h1-bracket-mass" / "open-01")


@pytest.fixture
def stub(folder):
    s = StubFrame(presence(FRAME_AT, parked_run="bracket-mass@2"))
    s.add_run(run_document(folder, RUN, ("h1-bracket-mass", "open-01"), {"lineage": "bracket-mass", "revision": 3, "sha256": "b" * 64}),
              record_events(folder), {"requester": {"kind": "model", "name": "claude-haiku-5-5"}})
    return s


def frame_of(stub: StubFrame, token: str | None = "s3cret") -> Frame:
    return Frame("http://frame.test", token, client=TestClient(stub.app(), base_url="http://frame.test"))


@pytest.fixture
def tool(home, stub, tmp_path):
    app = create_app(home, tmp_path / "logs", tmp_path / "runs", frame=frame_of(stub))
    return TestClient(app)


def down_frame() -> Frame:
    def refuse(request):
        raise httpx.ConnectError("connection refused", request=request)
    return Frame("http://127.0.0.1:9", "s3cret", client=httpx.Client(base_url="http://127.0.0.1:9", transport=httpx.MockTransport(refuse)))


# ------------------------------------------------------------------------ the client

def test_the_token_is_read_from_a_file_or_the_environment(tmp_path, monkeypatch):
    f = tmp_path / "token"
    f.write_text("# the frame workshop-1\njoakim=abc123\n", encoding="utf-8")
    assert read_token(f) == "abc123"
    f.write_text("abc456\n", encoding="utf-8")
    assert read_token(f) == "abc456"
    monkeypatch.setenv("AM_FRAME_TOKEN", "from-env")
    assert read_token(None) == "from-env"
    assert "abc" not in repr(Frame("http://frame.test", "abc456"))


def test_the_client_reads_the_contracts_and_validates_them(stub):
    frame = frame_of(stub)
    assert frame.presence()["frame"]["name"] == "workshop-1"
    assert [r["id"] for r in frame.runs()["runs"]] == [RUN]
    doc = frame.events(RUN, 0)
    assert doc["last"] == len(doc["events"]) and doc["run"]["status"] == "done"
    assert frame.events(RUN, doc["last"])["events"] == []
    # the skew is the frame's clock less the tool's: years here
    assert frame.contact.skew > timedelta(days=365)
    stub.broken = "presence"
    with pytest.raises(FrameError) as e:
        frame.presence()
    assert e.value.kind == "refused" and any("down_after" in r for r in e.value.reasons)


def test_a_refused_token_is_said_in_the_frames_words_and_never_shown(stub):
    with pytest.raises(FrameError) as e:
        frame_of(stub, "wrong-token").presence()
    assert e.value.kind == "unauthorized" and "frame-tokens" in str(e.value) and "wrong-token" not in str(e.value)
    with pytest.raises(FrameError) as e:
        frame_of(stub, None).runs()
    assert "missing" in str(e.value)


def test_a_frame_that_does_not_answer_is_a_state_not_an_error():
    frame = down_frame()
    with pytest.raises(FrameError) as e:
        frame.presence()
    assert e.value.kind == "unreachable" and frame.contact.since is not None


def test_down_is_inferred_on_the_frames_clock():
    doc = presence(FRAME_AT)
    states = {p["id"]: part_state(p, doc) for p in doc["parts"]}
    # the roles' sign of life is the frame's `at`: present, however far the tool's clock stands from the frame's
    assert states["requester"] == "present" and states["process_planner"] == "present"
    assert states["virtual-nominal"] == "down"           # seen 300 s before `at`, the limit 30 s
    assert states["core-one-1"] == "unavailable"


# ------------------------------------------------------------------------ one reader, two sources

def picture(run, at_):
    st = R.state(run, at_)
    return st, overview(run, st)


def test_a_run_read_from_the_frame_is_the_run_read_from_its_folder(folder, stub):
    from_folder = R.read(folder.parents[1], "h1-bracket-mass/open-01")
    reading = Reading(frame_of(stub))
    kept, error = reading.read_run(RUN)
    assert error is None
    from_frame = R.from_events(kept["run"], kept["events"])

    def ev(run):
        return [(e.time, e.kind, e.sender, e.recipient, e.type, e.text, e.valid, e.decision, e.ref) for e in run.events]

    def bars(run):
        return [(b.role, b.actor, b.model, b.start, b.end, b.id, b.prompt,
                 [(t.seq, t.start, t.end, t.seconds, t.thinking, t.text, t.results_end, [(a.start, a.end, a.word, a.count, a.detail) for a in t.acts])
                  for t in b.turns], [(a.start, a.end, a.family, a.word, a.count, a.detail) for a in b.acts]) for b in run.bars]

    assert ev(from_frame) == ev(from_folder)
    assert bars(from_frame) == bars(from_folder)
    assert (from_frame.designs, from_frame.roles, from_frame.decision_makers, from_frame.mandate, from_frame.accepted_plan, from_frame.order) == \
           (from_folder.designs, from_folder.roles, from_folder.decision_makers, from_folder.mandate, from_folder.accepted_plan, from_folder.order)
    assert (from_frame.start, from_frame.end, from_frame.live) == (from_folder.start, from_folder.end, from_folder.live)
    for s in range(-5, 620, 7):
        t = T0 + timedelta(seconds=s)
        a, pa = picture(from_frame, t)
        b, pb = picture(from_folder, t)
        assert (set(a.awake), {r: (x.word, x.start) for r, x in a.activity.items()}, a.waiting, {r: x.ref or x.text for r, x in a.latest.items()},
                a.design, a.traffic, a.seen, a.outcome) == \
               (set(b.awake), {r: (x.word, x.start) for r, x in b.activity.items()}, b.waiting, {r: x.ref or x.text for r, x in b.latest.items()},
                b.design, b.traffic, b.seen, b.outcome), s
        assert pa == pb, s


def test_a_live_run_is_followed_after_the_last_number_and_a_done_run_is_not_read_again(stub):
    events = stub.runs[RUN]["events"]
    stub.served[RUN] = 20
    reading = Reading(frame_of(stub))
    kept, _ = reading.read_run(RUN)
    assert kept["run"]["status"] == "running" and kept["last"] == events[19]["seq"]
    live = R.from_events(kept["run"], kept["events"], reading.frame.contact.frame_now())
    assert live.live and live.now.year == 2031
    # the clock of a live run with nothing asked is the frame's now, not the tool's
    assert R.parse_at(live, None) == live.end
    stub.served[RUN] = 30
    kept, _ = reading.read_run(RUN)
    assert [e["seq"] for e in kept["events"]] == [e["seq"] for e in events[:30]]
    del stub.served[RUN]
    kept, _ = reading.read_run(RUN)
    assert kept["run"]["status"] == "done" and [e["seq"] for e in kept["events"]] == [e["seq"] for e in events]
    asked = [a for a in stub.asked if a.startswith(f"/runs/{RUN}/events")]
    assert asked == [f"/runs/{RUN}/events?after=0", f"/runs/{RUN}/events?after={events[19]['seq']}",
                     f"/runs/{RUN}/events?after={events[29]['seq']}"]
    reading.read_run(RUN)
    assert len([a for a in stub.asked if a.startswith(f"/runs/{RUN}/events")]) == 3


def test_what_the_events_carry_beyond_the_folders_is_kept_beside_the_picture(stub):
    t0 = at(700)
    extra = [
        {"seq": 900, "time": t0, "kind": "plan", "source": {"table": "call", "row": "call-x"}, "id": "plan-1@v3", "case": "case-1",
         "design": "bracket-mass@v2", "machine_class": "fff-3axis-0.4", "verdict": "at_risk",
         "findings": [{"requirement": "req-14", "metric": "M8", "feature": "pin-hole", "status": "at_risk", "value": 0.838, "limit": 1.0,
                       "margin": 0.6, "unit": "1", "call": "call-x"}]},
        {"seq": 901, "time": t0, "kind": "dialogue", "source": {"table": "call", "row": "call-show"}, "id": "call-show", "case": "case-1",
         "tool": "show_design", "actor": "agent", "inputs": {"design": "bracket-mass@v2"},
         "findings": [{"requirement": "req-14", "metric": "M8", "feature": "pin-hole", "status": "at_risk", "value": 0.838, "limit": 1.0,
                       "margin": 0.6, "unit": "1", "call": "call-x"}],
         "certificate": {"text": "Since the brief 1 version made (by parameters 1); the lightest holding the rest is bracket-mass@v2.",
                         "versions": 1, "means": ["parameters"], "lightest": "bracket-mass@v2", "cites": ["call-x"]}},
        {"seq": 902, "time": t0, "kind": "dialogue", "source": {"table": "call", "row": "call-acc"}, "id": "call-acc", "case": "case-1",
         "tool": "accept_design", "actor": "agent", "inputs": {"shown": "call-show"},
         "relaxations": [{"requirement": "req-14", "metric": "M8", "what": "margin", "from": 0.6, "to": 0.838, "unit": "1", "within_mandate": True}]},
        {"seq": 903, "time": t0, "kind": "parked", "source": {"table": "call", "row": "call-park"}, "case": "case-1", "what": "showing",
         "dialogue": "call-show", "metrics": ["M13"]},
    ]
    run = dict(stub.runs[RUN]["run"], status="parked", ended=None, outcome=None)
    events = [e for e in stub.runs[RUN]["events"] if e["kind"] != "ended"] + extra
    r = R.from_events(run, events)
    assert r.is_parked and r.parked["metrics"] == ["M13"] and not r.live
    assert r.plans["plan-1@v3"]["verdict"] == "at_risk" and r.accepted_design == "bracket-mass@v2"
    st, pic = picture(r, T0 + timedelta(seconds=700))
    notes = [n for s in pic["sentences"] for n in s["notes"]]
    assert "the margin on M8 relaxed from 0.6 to 0.838 within its mandate" in notes
    assert "M8 at pin-hole at risk: 0.838 against the margin 0.6" in notes
    assert any(s["certificate"] and s["certificate"]["cites"] == ["call-x"] for s in pic["sentences"])


# ------------------------------------------------------------------------ the pages

def test_the_empty_state_shows_the_frame_its_roles_and_what_waits(tool):
    page = tool.get("/runs")
    assert page.status_code == 200
    t = page.text
    assert "The frame workshop-1" in t and "waiting for orders" in t
    assert "Requester" in t and "the scripted policy (reference)" in t and "claude-sonnet-5-5" in t and "no decision maker" in t
    assert 'class="state down"' in t and "virtual-nominal" in t and "no host is configured for its adapter" in t
    assert "parked for the owner&#39;s word" in t and "a showing from the design engineer waits for the requester" in t
    assert 'hx-get="/frame/presence" hx-trigger="every 3.0s"' in t
    fragment = tool.get("/frame/presence")
    assert fragment.status_code == 200 and fragment.text.lstrip().startswith('<div id="presence"') and "<html" not in fragment.text


def test_the_catalogue_shows_the_frames_runs_beside_the_folders(tool, home):
    t = tool.get("/runs").text
    assert "The frame's runs" in t and f'href="/frame/runs/{RUN}"' in t and "requester: claude-haiku-5-5" in t
    assert "The folders' runs" in t and "read from the folders under" in t


def test_a_run_page_from_the_frame(tool):
    page = tool.get(f"/frame/runs/{RUN}?at=300")
    assert page.status_code == 200
    t = page.text
    assert 'const base = "/frame/runs/h1-bracket-mass/open-01"' in t and "Read from" in t and "workshop-1" in t
    assert f'src="/frame/runs/{RUN}/picture/bracket-mass@v2"' in t
    assert 'data-skew="' in t and 'data-skew="0"' not in t
    view = tool.get(f"/frame/runs/{RUN}/view?at=300.5")
    assert view.status_code == 200 and view.text.lstrip().startswith('<div id="overview"')
    pic = tool.get(f"/frame/runs/{RUN}/picture/bracket-mass@v2")
    assert pic.status_code == 200 and pic.headers["content-type"] == "image/png"
    assert tool.get("/frame/runs/no-such-run").status_code == 404


def test_a_run_page_when_the_frame_does_not_answer(home, tmp_path):
    t = TestClient(create_app(home, None, None, frame=down_frame()))
    page = t.get(f"/frame/runs/{RUN}")
    assert page.status_code == 503 and "has not answered since" in page.text
    runs = t.get("/runs")
    assert runs.status_code == 200 and "has not answered since" in runs.text and "the page shows what it last read" in runs.text


def test_the_page_keeps_what_it_last_read_when_the_frame_stops_answering(home, stub):
    frame = frame_of(stub)
    app = create_app(home, None, None, frame=frame)
    t = TestClient(app)
    assert "The frame workshop-1" in t.get("/runs").text
    frame.client = down_frame().client
    page = t.get("/runs").text
    assert "has not answered since" in page and "The frame workshop-1" in page


def test_a_refused_document_is_the_frames_fault(home, stub):
    stub.broken = "presence"
    page = TestClient(create_app(home, None, None, frame=frame_of(stub))).get("/runs").text
    assert "does not have the form of its schema (the frame&#39;s fault, not the tool&#39;s)" in page and "down_after" in page


def test_a_refused_token_on_the_page(home, stub):
    page = TestClient(create_app(home, None, None, frame=frame_of(stub, "wrong-token"))).get("/runs").text
    assert "refuses the token" in page and "frame-tokens" in page and "wrong-token" not in page


def test_an_order_placed_from_its_page(tool, stub, tmp_path):
    product = tool.get("/products/bracket-mass")
    assert 'hx-get="/products/bracket-mass/frame"' in product.text
    fragment = tool.get("/products/bracket-mass/frame")
    assert "Place revision 2 at the frame" in fragment.text and "bracket-mass@2" in fragment.text and "parked" in fragment.text
    placed = tool.post("/products/bracket-mass/place")
    assert placed.status_code == 201 and "Placed at the frame: the run bracket-mass@2 (placed)" in placed.text
    again = tool.post("/products/bracket-mass/place")
    assert again.status_code == 409 and "Not placed: the order version bracket-mass@2 is placed already" in again.text
    stub.refuse_with = ["(the document): 'schema' is a required property"]
    stub.orders.clear()
    refused = tool.post("/products/bracket-mass/place")
    assert refused.status_code == 422 and "&#39;schema&#39; is a required property" in refused.text
    log = [json.loads(line) for f in (tmp_path / "logs").glob("*.jsonl") for line in f.read_text().splitlines()]
    places = [e for e in log if e["action"] == "place"]
    assert len(places) == 3 and all(e["detail"]["capacity"] == "orderer" for e in places)
    assert "s3cret" not in json.dumps(log)


def test_an_order_not_confirmed_is_not_placed(tool):
    tool.post("/products", data={"lineage": "drafty", "name": "Drafty"})
    fragment = tool.get("/products/drafty/frame")
    assert "Not ready to be placed: the order has no saved version yet" in fragment.text
    refused = tool.post("/products/drafty/place")
    assert refused.status_code == 409 and "Not placed" in refused.text


# ------------------------------------------------------------------------ the command line

def test_the_command_line_reads_the_frame_and_places(stub, home_dir, tmp_path, capsys, monkeypatch):
    token = tmp_path / "token"
    token.write_text("me=s3cret\n", encoding="utf-8")
    app = stub.app()
    monkeypatch.setattr("am_order.cli._client", lambda url: TestClient(app, base_url=url))
    base = ["--home", str(home_dir), "--frame", "http://frame.test", "--token-file", str(token)]
    assert main(base + ["runs"]) == 0
    out = capsys.readouterr().out
    assert RUN in out and "done" in out and "accepted" in out
    assert main(base + ["runs", "show", RUN, "--at", "300"]) == 0
    out = capsys.readouterr().out
    assert "0:05:00" in out and "Design engineer" in out
    assert main(base + ["place", "bracket-mass"]) == 0
    assert "bracket-mass@2" in capsys.readouterr().out
    assert main(base + ["place", "bracket-mass@2"]) == 1
    assert "placed already" in capsys.readouterr().err
    token.write_text("me=wrong\n", encoding="utf-8")
    assert main(base + ["runs"]) == 1
    err = capsys.readouterr().err
    assert "refuses the token" in err and "wrong" not in err.replace("refuses", "")
