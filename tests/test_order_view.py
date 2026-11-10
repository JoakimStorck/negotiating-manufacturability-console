"""The order view, the orderer's, against the stub that serves the frame's own documents: the order's steps from stated to approved
with the next as one button, the order whole edited in its rows, the owner's word on a parked run (the showing, the relaxations
asked in words, the findings at risk, what is left unmet, the certificate; accept with R12's relaxations, refuse with conditions and
holds, decline with the reason), the frame's 409 and 422 in its words, the links between the run and its order, the approval, and
the command line."""
import html
import json
import re

import pytest
from fastapi.testclient import TestClient

from am_order import Home
from am_order.cli import main
from am_order.frame import Frame
from am_order.order import sha256
from am_order.web.app import create_app
from stub_frame import HELD, body, example, held_mass, renamed, served_files

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")
RUN = "bracket-mass@4"
REV = {"lineage": "bracket-mass", "revision": 4, "sha256": "51293041b1667402a070f5719a76770f7a0b8e7252d208563c579b7c6bdd2ac8"}
REV3 = {"lineage": "bracket-mass", "revision": 3, "sha256": "37180c0d1180a75d0c0d3f058831e25167ce31a63382c048d0c276c66ebe27be"}
VIEW = "/products/bracket-mass/order"
SINCE = body("dialogue-parked")["waits"]["since"]           # when the first showing began to wait, as the frame recorded it
WAITS = f"a showing waits since {SINCE[:10]} {SINCE[11:19]}Z"


def stub_at(stage: str, run_id: str = RUN, order: dict = REV):
    """The held mass order's run in a state of the examples, named as the home's revision 4 (the held case, order 2)."""
    return held_mass(stage, run_id, order)


def frame_of(stub) -> Frame:
    return Frame("http://frame.test", stub.token, client=TestClient(stub.app(), base_url="http://frame.test"))


def tool(home_dir, tmp_path, stub=None, allow_own: bool = True) -> TestClient:
    return TestClient(create_app(Home(home_dir, allow_own=allow_own), tmp_path / "logs", None, frame=frame_of(stub) if stub else None))


def reached(page: str) -> str:
    return re.search(r'<li class="[^"]*reached" data-step="([a-z]+)"', page).group(1)


def button(page: str) -> str:
    """The next step's one button: its text and where it goes."""
    nxt = page.split('<div class="next" id="next">', 1)[1].split("</div>", 1)[0]
    found = re.search(r'<form method="post" action="([^"]+)"[^>]*>.*?<button>([^<]+)</button>', nxt, re.S)
    if found:
        return f"{html.unescape(found.group(2))} -> POST {found.group(1)}"
    found = re.search(r'<a class="button" href="([^"]+)">([^<]+)</a>', nxt)
    return f"{html.unescape(found.group(2))} -> {found.group(1)}" if found else ""


def logged(tmp_path, action: str) -> list[dict]:
    return [json.loads(line) for f in (tmp_path / "logs").glob("*.jsonl") for line in f.read_text(encoding="utf-8").splitlines()
            if json.loads(line)["action"] == action]


# ------------------------------------------------------------------------ the steps and the one button

def test_the_steps_before_the_frame(home_dir, tmp_path):
    c = tool(home_dir, tmp_path)
    c.post("/products", data={"lineage": "fresh", "name": "Fresh"})
    page = c.get("/products/fresh/order").text
    assert reached(page) == "stated" and re.match(r"Fix \d+ refusals -> /products/fresh", button(page))
    assert "As orderer of fresh" in page
    # a change of a saved order: a draft, saved from here as the next revision
    c.post(VIEW, data={"brief_text": "Ten brackets, light.", "objective": "mass", "quantity": "12", "answering": "decline"})
    page = c.get(VIEW).text
    assert reached(page) == "stated" and button(page) == "Save revision 5 -> POST /products/bracket-mass/order/save"
    assert "As orderer of bracket-mass@4, its draft" in page
    saved = c.post("/products/bracket-mass/order/save").text
    assert "saved as revision 5" in saved and reached(saved) == "confirmed"
    assert "The tool is not connected to a frame" in saved and button(saved) == ""
    # checked: saved without a design; bound: a binding not confirmed
    h = Home(home_dir, allow_own=True)
    o = h.working("l-bracket")
    o.type["bindings"][0]["features"][0]["confirmed"] = False
    h.save(o)
    page = c.get("/products/l-bracket/order").text
    assert reached(page) == "bound" and button(page) == "Confirm 1 binding -> /products/l-bracket/binding"
    o = h.working("l-bracket")
    o.type["design"], o.type["bindings"] = None, []
    h.save(o)
    page = c.get("/products/l-bracket/order").text
    assert reached(page) == "checked" and button(page) == "Bind to a design -> /products/l-bracket/binding"
    links = dict(re.findall(r'data-step="([a-z]+)"><a href="([^"]+)"', page))
    assert links == {"stated": "/products/l-bracket"}           # the step reached is the button, not a link


def test_the_steps_at_the_frame_each_with_its_one_button(home_dir, tmp_path):
    # placed: the version placed from here, not yet a run
    stub = held_mass("empty")
    c = tool(home_dir, tmp_path, stub)
    page = c.get(VIEW).text
    assert reached(page) == "confirmed" and button(page) == "Place revision 4 -> POST /products/bracket-mass/order/place"
    placed = c.post("/products/bracket-mass/order/place").text
    assert "Placed at the frame: the run bracket-mass@4 (placed)" in placed
    assert reached(placed) == "placed" and button(placed) == "Follow the run -> /frame/runs/bracket-mass@4"
    expected = {"preparing": ("preparing", "Follow the run -> /frame/runs/bracket-mass@4"),
                "parked": ("word", f"Give your word: a showing waits since {SINCE[11:16]}Z -> /products/bracket-mass/order#word"),
                "accepted": ("accepted", "Approve for manufacturing -> POST /products/bracket-mass/order/approve")}
    for stage, (step, next_) in expected.items():
        page = tool(home_dir, tmp_path, stub_at(stage)).get(VIEW).text
        assert (reached(page), button(page)) == (step, next_), stage
    accepted = tool(home_dir, tmp_path, stub_at("accepted")).get(VIEW).text
    assert 'hx-confirm="Approve bracket-mass@4 for manufacturing, bound to the plan the run bracket-mass@4 accepted?' in accepted
    links = dict(re.findall(r'data-step="([a-z]+)"><a href="([^"]+)"', accepted))
    assert links["preparing"] == links["word"] == "/frame/runs/bracket-mass@4" and links["placed"] == "/products/bracket-mass/order#runs"


def test_a_version_changed_since_it_was_placed(home_dir, tmp_path):
    page = tool(home_dir, tmp_path, stub_at("parked", "bracket-mass@3", REV3)).get(VIEW).text
    assert reached(page) == "confirmed" and button(page) == "Changed since it was placed: place revision 4 -> POST /products/bracket-mass/order/place"


def test_a_declined_run_names_its_reason_and_the_way_back(home_dir, tmp_path):
    stub = stub_at("accepted")
    run = stub.runs[RUN]["run"]
    run.update(outcome="declined", reason="the part is no use above 16 g", result={**run["result"], "outcome": "declined", "plan": None,
                                                                                    "reason": "the part is no use above 16 g"})
    page = tool(home_dir, tmp_path, stub).get(VIEW).text
    assert button(page) == "Change the order and place it again -> /products/bracket-mass/order#the-order"
    assert "Declined by the requester: the part is no use above 16 g" in page


def test_the_header_badge_is_the_step_reached_on_every_product_page(home_dir, tmp_path):
    c = tool(home_dir, tmp_path, stub_at("parked"))
    for tab in ("", "/objects", "/metrics", "/binding", "/history"):
        assert '<a class="badge step" href="/products/bracket-mass/order"' in c.get(f"/products/bracket-mass{tab}").text
    assert re.search(r'class="badge step"[^>]*>Your word</a>', c.get("/products/bracket-mass").text)
    assert '<a href="/products/bracket-mass/order">Order</a>' in c.get("/products/bracket-mass").text


# ------------------------------------------------------------------------ the order whole, edited in its rows

def test_the_mandates_and_the_objects_edited_in_their_rows(home_dir, tmp_path):
    c = tool(home_dir, tmp_path)
    page = c.get(VIEW).text
    assert 'action="/products/bracket-mass/order/mandates/M13"' in page and 'action="/products/bracket-mass/order/objects/O8"' in page
    r = c.post("/products/bracket-mass/order/mandates/M13", data={"mandate": "interval", "far": "20"})
    assert r.status_code == 200 and "interval to 20 g" in r.text
    r = c.post("/products/bracket-mass/order/objects/O8", data={"change": "free"})
    assert r.status_code == 200
    r = c.post("/products/bracket-mass/order/mandates/M13", data={"mandate": "interval", "far": "17"})
    draft = Home(home_dir).draft("bracket-mass")
    assert draft.mandates()["M13"] == {"form": "interval", "to": 17} and draft.change("O8") == "free"
    acts = logged(tmp_path, "edit mandate") + logged(tmp_path, "edit object (free)")
    assert {(a["detail"]["capacity"], a["detail"]["section"]) for a in acts} == {("orderer", "order"), ("orderer", "type")}
    assert acts[0]["detail"]["metric"] == "M13" and acts[-1]["detail"]["object"] == "O8"
    refused = c.post("/products/bracket-mass/order/objects/O8", data={"change": "loose"})
    assert refused.status_code == 400 and "fixed or free" in refused.text


def test_the_order_view_holds_who_takes_it_and_its_runs(home_dir, tmp_path):
    c = tool(home_dir, tmp_path, stub_at("parked"))
    page = c.get(VIEW).text
    assert '<section id="runs">' in page and 'hx-get="/products/bracket-mass/frame"' in page
    fragment = c.get("/products/bracket-mass/frame").text
    assert "Who will take the order" in fragment and 'href="/frame/runs/bracket-mass@4"' in fragment and ">Delete</button>" in fragment
    assert "parked: your word is awaited" in fragment and 'href="/products/bracket-mass/order#word"' in fragment


# ------------------------------------------------------------------------ the links both ways

def test_the_run_links_to_its_order_and_a_parked_run_says_where_the_word_is_given(home_dir, tmp_path):
    c = tool(home_dir, tmp_path, stub_at("parked"))
    run = c.get("/frame/runs/bracket-mass@4").text
    assert '<a href="/products/bracket-mass/order">bracket-mass@4</a>' in run
    assert '<a href="/products/bracket-mass/order#word">Your word is given on the order</a>' in run
    before = c.get("/frame/runs/bracket-mass@4?at=10").text
    assert "Your word is given on the order" not in before
    view = c.get(VIEW).text
    assert 'href="/frame/runs/bracket-mass@4"' in view


# ------------------------------------------------------------------------ the owner's word

def test_the_parked_runs_showing_in_words(home_dir, tmp_path):
    page = html.unescape(tool(home_dir, tmp_path, stub_at("parked")).get(VIEW).text)
    word = page.split('<section class="word" id="word">', 1)[1].split("</section>", 1)[0]
    assert f"Your word: {WAITS}, on M13" in word
    assert 'src="/frame/runs/bracket-mass@4/picture/bracket-mass@v3"' in word and "The design engineer shows bracket-mass@v3" in word
    assert "55 min print time, 19.9 g material, 19.85 g printed" in word
    assert "M8 at pin-hole at risk: the plan reaches 0.838 against the margin 0.6" in word
    assert "M13 (mass) unmet: the plan reaches 19.852 g" in word and "refuse instead" in word
    assert "The certificate of exhausted means:</b> Since the brief 1 version of bracket-mass made" in word
    assert f"(cites {body('dialogue-parked')['waits']['entry']['certificate']['cites'][0]})" in word
    assert 'name="relax:req-14" value="0.838"' in word and "accept the risk" not in word.lower()
    assert 'hx-confirm="Accept what was shown, relaxing the margin on M8 to 0.838?' in word
    again = html.unescape(tool(home_dir, tmp_path, stub_at("parked-again")).get(VIEW).text)
    assert "M13 from at most 16 g to at most 20 g <span class=\"beyond\">(beyond the order's mandate)</span>" in again


def test_a_refusal_sends_its_conditions_and_holds(home_dir, tmp_path):
    stub = stub_at("parked")
    c = tool(home_dir, tmp_path, stub)
    showing = body("dialogue-parked")["waits"]["dialogue"]
    r = c.post("/products/bracket-mass/order/word", data={"word": "refuse", "run": RUN, "on": showing, "choice:req-20": "instead",
                                                          "value:req-20": "20", "choice:req-14": "hold", "choice:req-x": "",
                                                          "text": "Up to 20 g printed; the margin as given."})
    assert r.status_code == 200, r.text
    assert stub.words[-1] == (RUN, {"schema": "word/1", "word": "refuse", "showing": showing, "conditions": [{"replaces": "req-20", "body": {"at_most": 20}}],
                                    "held": ["req-14"], "text": "Up to 20 g printed; the margin as given."})
    t = html.unescape(r.text)
    assert "Your word is recorded at the frame" in t and "the run bracket-mass@4 goes on, running" in t
    assert '<a href="/frame/runs/bracket-mass@4">follow bracket-mass@4</a>' in t
    # the run has gone on and parked again on the owner's conditions: the new showing waits
    assert reached(r.text) == "word" and body("dialogue-parked-again")["waits"]["dialogue"] in t
    nothing = c.post("/products/bracket-mass/order/word", data={"word": "refuse", "run": RUN, "text": "No."})
    assert nothing.status_code == 400 and "a refusal states at least one requirement" in html.unescape(nothing.text)


def test_an_acceptance_sends_r12s_relaxations(home_dir, tmp_path):
    stub = stub_at("parked-again")
    c = tool(home_dir, tmp_path, stub)
    showing = body("dialogue-parked-again")["waits"]["dialogue"]
    short = c.post("/products/bracket-mass/order/word", data={"word": "accept", "run": RUN, "on": showing, "relax:req-14": "0.7"})
    assert short.status_code == 400 and "still leaves the plan at risk" in html.unescape(short.text) and not stub.words
    unconfirmed = c.post("/products/bracket-mass/order/word", data={"word": "accept", "run": RUN, "on": showing})
    assert unconfirmed.status_code == 400 and "relaxes its margin to what the plan reaches" in unconfirmed.text and not stub.words
    r = c.post("/products/bracket-mass/order/word", data={"word": "accept", "run": RUN, "on": showing, "relax:req-14": "0.838", "text": "Accepted."})
    assert r.status_code == 200
    assert stub.words[-1][1] == {"schema": "word/1", "word": "accept", "showing": showing, "relaxes": [{"replaces": "req-14", "margin": 0.838}],
                                 "text": "Accepted."}
    assert reached(r.text) == "accepted" and "Approve for manufacturing" in r.text


def test_a_decline_needs_its_reason(home_dir, tmp_path):
    stub = stub_at("parked")
    c = tool(home_dir, tmp_path, stub)
    showing = body("dialogue-parked")["waits"]["dialogue"]
    r = c.post("/products/bracket-mass/order/word", data={"word": "decline", "run": RUN, "on": showing, "text": " "})
    assert r.status_code == 400 and "a decline names what you hold that what was shown cannot meet" in r.text and not stub.words
    r = c.post("/products/bracket-mass/order/word", data={"word": "decline", "run": RUN, "on": showing, "text": "The part is no use above 16 g."})
    assert r.status_code == 200 and stub.words[-1][1]["text"] == "The part is no use above 16 g."


def test_the_frames_409_and_422_in_its_words(home_dir, tmp_path):
    stub = stub_at("parked-again")
    c = tool(home_dir, tmp_path, stub)
    stale = body("dialogue-parked")["waits"]["dialogue"]
    r = c.post("/products/bracket-mass/order/word", data={"word": "decline", "run": RUN, "on": stale, "text": "No use above 16 g."})
    assert r.status_code == 409
    assert f"The frame did not take your word: the word is on showing {stale}, which does not wait" in html.unescape(r.text)
    # the requester's tool refuses an acceptance, in its own words (a refusal recorded for this word, on a copy)
    showing = body("dialogue-parked-again")["waits"]["dialogue"]
    word = {"schema": "word/1", "word": "accept", "showing": showing, "relaxes": [{"replaces": "req-14", "margin": 0.9}]}
    refusal = renamed(example("dialogue-word-422"), RUN, REV)
    refusal["request"]["body"] = word
    stub.recorded.append(refusal)
    r = c.post("/products/bracket-mass/order/word", data={"word": "accept", "run": RUN, "on": showing, "relax:req-14": "0.9"})
    assert r.status_code == 422 and "a plan at risk is accepted only with its margins relaxed by the acceptance to what it reaches" in html.unescape(r.text)
    assert len(stub.words) == 0
    other = c.post("/products/plate/order/word", data={"word": "decline", "run": RUN, "on": showing, "text": "x"})
    assert other.status_code == 404 and "is no run of an order of plate" in other.text


def test_the_log_holds_each_word_with_its_capacity(home_dir, tmp_path):
    stub = stub_at("parked")
    c = tool(home_dir, tmp_path, stub)
    showing = body("dialogue-parked")["waits"]["dialogue"]
    c.post("/products/bracket-mass/order/word", data={"word": "refuse", "run": RUN, "on": showing, "choice:req-20": "instead",
                                                      "value:req-20": "20", "text": "Up to 20 g."})
    c.post("/products/bracket-mass/order/word", data={"word": "decline", "run": RUN, "on": showing})
    words = logged(tmp_path, "word")
    assert len(words) == 2 and all(w["detail"]["capacity"] == "orderer" and w["detail"]["run"] == RUN for w in words)
    assert words[0]["detail"]["word"]["conditions"] == [{"replaces": "req-20", "body": {"at_most": 20}}]
    assert words[0]["detail"]["answer"]["schema"] == "said/1" and "decline names" in words[1]["detail"]["refused"]
    assert stub.token not in json.dumps(words)


# ------------------------------------------------------------------------ the approval

def test_the_approval_writes_a_new_revision_the_features_and_the_dialogue(home_dir, tmp_path):
    c = tool(home_dir, tmp_path, stub_at("accepted"))
    r = c.post("/products/bracket-mass/order/approve", data={"run": RUN})
    assert r.status_code == 200 and "Approved for manufacturing as revision 5: plan-bracket-mass-v3-mZ@v59 for bracket-mass@v3" in r.text
    h = Home(home_dir)
    order = h.load("bracket-mass")
    assert order.data["revision"] == 5 and order.form == 2
    accepted = order.accepted()
    assert accepted == {"run": RUN, "order": REV, "plan": "plan-bracket-mass-v3-mZ@v59", "design": "bracket-mass@v3",
                        "design_sha256": body("features-accepted")["sha256"],
                        "time": next(e["time"] for e in body("dialogue-accepted")["thread"] if e["kind"] == "accepted")}
    assert [(x["metric"], x["what"], x["from"], x["to"], x["by"]["actor"], x["within_mandate"]) for x in order.in_force()] == \
           [("M13", "value", 16.0, 20.0, "owner", False), ("M8", "margin", 0.6, 0.838, "owner", True)]
    assert all(x["run"] == RUN and x["showing"] == body("dialogue-parked-again")["waits"]["dialogue"] for x in order.in_force())
    # not a change of the requirements: the type and the mandates as placed
    placed = h.load("bracket-mass@4")
    assert order.type == placed.type and order.mandates() == placed.mandates()
    assert h.features("bracket-mass@v3")["design"] == "bracket-mass@v3"
    # the picture and the models as the frame served them, each the hash the feature list names
    features = body("features-accepted")
    named = {f["file"]: f["sha256"] for f in [features["picture"]] + features["models"]}
    for name, data, _ in served_files():
        kept = (home_dir / "features" / "bracket-mass@v3" / name).read_bytes()
        assert kept == data and sha256(kept) == named[name]
    assert h.dialogue("bracket-mass", RUN) == renamed(body("dialogue-accepted"), RUN, REV)
    page = r.text
    assert reached(page) == "approved" and button(page) == "" and '<section id="approved">' in page
    assert "the value on M13 relaxed from 16 to 20 by the order&#39;s owner, beyond its mandate" in page
    assert f'href="/products/bracket-mass/dialogue/{RUN}"' in page and c.get(f"/products/bracket-mass/dialogue/{RUN}").json()["schema"] == "dialogue/1"
    fragment = c.get("/products/bracket-mass/frame").text
    assert "Not ready to be placed: revision 5 is approved for manufacturing" in fragment and "Place revision 5" not in fragment
    act = logged(tmp_path, "approve")[-1]["detail"]
    assert act["capacity"] == "orderer" and act["run"] == RUN and act["revision"] == 5
    # a later change of the order is a new order: placed again, without the approval's record
    c.post("/products/bracket-mass/order/mandates/M13", data={"mandate": "interval", "far": "18"})
    saved = c.post("/products/bracket-mass/order/save").text
    assert "saved as revision 6" in saved
    assert Home(home_dir).load("bracket-mass").accepted() is None and Home(home_dir).load("bracket-mass").in_force() == []
    assert button(saved) == "Changed since it was placed: place revision 6 -> POST /products/bracket-mass/order/place"


def test_the_approval_only_at_its_step(home_dir, tmp_path):
    c = tool(home_dir, tmp_path, stub_at("parked"))
    r = c.post("/products/bracket-mass/order/approve", data={"run": RUN})
    assert r.status_code == 409 and "Not approved: the order&#39;s step is your word, not accepted." in r.text
    assert Home(home_dir).load("bracket-mass").data["revision"] == 4
    readonly = tool(home_dir, tmp_path, stub_at("accepted"), allow_own=False).post("/products/bracket-mass/order/approve", data={"run": RUN})
    assert readonly.status_code == 403 and "read only" in readonly.text


# ------------------------------------------------------------------------ the command line

def test_the_command_line_reads_the_dialogue_gives_a_word_and_approves(home_dir, tmp_path, capsys, monkeypatch):
    stub = stub_at("parked")
    app = stub.app()
    monkeypatch.setattr("am_order.cli._client", lambda url: TestClient(app, base_url=url))
    token = tmp_path / "token"
    token.write_text(f"me={stub.token}\n", encoding="utf-8")
    base = ["--frame", "http://frame.test", "--token-file", str(token)]
    assert main(base + ["dialogue", RUN]) == 0
    out = capsys.readouterr().out
    assert WAITS in out and "M8 at pin-hole at risk: the plan reaches 0.838 against the margin 0.6" in out
    assert "M13 (mass) unmet: the plan reaches 19.852 g" in out and "The certificate of exhausted means" in out
    assert main(base + ["say", RUN, "decline"]) == 1
    assert "a decline names what you hold" in capsys.readouterr().err
    assert main(base + ["say", RUN, "refuse", "--condition", "req-20:at_most=20", "--hold", "req-14", "--text", "Up to 20 g."]) == 0
    assert "recorded" in capsys.readouterr().out
    assert stub.words[-1][1]["conditions"] == [{"replaces": "req-20", "body": {"at_most": 20}}] and stub.words[-1][1]["held"] == ["req-14"]
    assert main(base + ["say", RUN, "accept"]) == 1
    assert "--relax req-14=0.838" in capsys.readouterr().err
    assert main(base + ["say", RUN, "accept", "--relax", "req-14=0.838"]) == 0
    capsys.readouterr()
    assert main(base + ["dialogue", RUN]) == 0
    assert "nothing waits for the owner's word" in capsys.readouterr().out
    # the run accepted: approved from the command line
    accepted = stub_at("accepted")
    app = accepted.app()
    monkeypatch.setattr("am_order.cli._client", lambda url: TestClient(app, base_url=url))
    assert main(["--home", str(home_dir), "--allow-own"] + base + ["approve", "bracket-mass"]) == 0
    assert "revision 5" in capsys.readouterr().out and Home(home_dir).load("bracket-mass").accepted()["run"] == RUN
    assert main(["--home", str(home_dir), "--allow-own"] + base + ["approve", "bracket-mass"]) == 1
    assert "approved" in capsys.readouterr().err
