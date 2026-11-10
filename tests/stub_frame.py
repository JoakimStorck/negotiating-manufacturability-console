"""A standing frame stubbed in the tool's own tests: a FastAPI app that answers as am-llm's frame does (`agents/frame.py`), from
the frame's own documents, so that the tool's tests run on every platform without am-llm and a frame that changes shows here as
a failing test.

The documents are the contract's examples (`tests/contract/`), which am-llm writes from a frame with scripted roles
(`python -m agents frame examples`) and this repository copies at the pin, each with the request that drew it: presence empty,
being prepared, at each parking and ended; the catalogue and the held mass order's events being prepared, at each parking and
accepted; its dialogue at each parking and accepted; the picture of the version shown at the first parking, as the run drew it;
the accepted version's feature list, picture and models; the answers to a word, to a decision maker placed, to an order placed
and to a run deleted, with their refusals. `held_mass` stands the stub in the state an
example was recorded in; a test that needs another state changes a copy (`renamed` for another order version, `shifted` for another
clock). The frame's answers the stub computes are in the frame's words; the one whose words it cannot compute, an acceptance refused
in the requester's tool's words, it gives as recorded for the request that drew it.

`record_events` turns a run folder made by `test_runs.make_run` into the events the frame would serve for it, numbered in the
order the record writes its rows (a waking's start as it starts and its end as it ends, a turn as it ends, a call as it answers),
so that the same run can be read both ways and compared.
"""
from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

from am_order import SchemaError, validate_order
from am_order.order import canonical, sha256
from am_order.schema import errors

DIALOGUE = ("brief", "ask_requester", "answer_requester", "remark", "show_design", "accept_design", "decline_order", "consent")
CONTRACT = Path(__file__).resolve().parent / "contract"
HELD = "bracket-mass@2"                      # the examples' run: the held mass order, placed as revision 2
WORDS = {"accept": "accepted", "refuse": "remark", "decline": "declined", "answer": "answer"}
DESIGN = re.compile(r"[a-z0-9][a-z0-9-]{0,63}@v[1-9][0-9]*")    # a design version's id, as the frame reads one


def example(name: str) -> dict:
    """An example as am-llm wrote it, a fresh copy: {request, status, body}."""
    return json.loads((CONTRACT / f"{name}.json").read_text(encoding="utf-8"))


def body(name: str) -> dict:
    return example(name)["body"]


def examples() -> list[str]:
    """Every example's name, as the index lists them."""
    return sorted(json.loads((CONTRACT / "index.json").read_text(encoding="utf-8"))["examples"])


TOKENS_FILE = body("presence-401")["error"].rsplit(" ", 1)[1]


def renamed(doc, run_id: str, order: dict):
    """A copy of a document of the held mass order's run as the run of another order version: its id, paths and order."""
    old = body("runs-parked")["runs"][0]["order"]
    text = json.dumps(doc).replace(f'"{HELD}"', f'"{run_id}"').replace(f"/runs/{HELD}/", f"/runs/{run_id}/").replace(f"run {HELD} ", f"run {run_id} ")
    out = json.loads(text)

    def walk(x):
        if isinstance(x, dict):
            if x.get("sha256") == old["sha256"] and x.get("revision") == old["revision"]:
                x.update(order)
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    walk(out)
    return out


def shifted(doc, to: str, frm: str | None = None):
    """A copy of a document on another clock: every time in it moved by the same amount, so that `at` becomes `to` (or `frm`
    becomes `to`) and every age read against `at` stays what it was."""
    delta = _t(to) - _t(frm or doc["at"])

    def walk(x):
        if isinstance(x, dict):
            return {k: walk(v) for k, v in x.items()}
        if isinstance(x, list):
            return [walk(v) for v in x]
        if isinstance(x, str) and len(x) >= 20 and x[4] == "-" and x[10] == "T" and x.endswith("Z"):
            try:
                return (_t(x) + delta).isoformat().replace("+00:00", "Z")
            except ValueError:
                return x
        return x
    return walk(doc)


def _t(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _maker(model: str | None, actor: str) -> dict:
    if actor == "operator":
        return {"kind": "operator", "name": None}
    model = model or ""
    if model.startswith("scripted:"):
        return {"kind": "none", "name": None} if "without a decision maker" in model else {"kind": "scripted", "name": "scripted"}
    return {"kind": "model", "name": model.split(":", 1)[-1]}


def record_events(folder: Path) -> list[dict]:
    """The events of a folder's record as the frame serves them, in the order the record writes its rows."""
    db = sqlite3.connect(folder / "record.db")
    db.row_factory = sqlite3.Row
    rows: list[tuple[datetime, int, dict]] = []      # (written, insertion, event)

    def add(written: str | datetime, event: dict):
        rows.append((_t(written) if isinstance(written, str) else written, len(rows), event))

    for r in db.execute("SELECT * FROM design ORDER BY rowid"):
        add(r["time"], {"time": r["time"], "kind": "design", "source": {"table": "design", "row": r["id"]}, "id": r["id"], "parent": r["parent"],
                        "made_by_role": r["made_by_role"], "made_by_actor": r["made_by_actor"], "sha256": (r["content_sha256"] * 64)[:64]})
    for r in db.execute("SELECT * FROM message ORDER BY rowid"):
        add(r["time"], {"time": r["time"], "kind": "message", "source": {"table": "message", "row": r["id"]}, "id": r["id"], "case": r["case_id"],
                        "type": r["type"], "from_role": r["from_role"], "to_role": r["to_role"], "from_actor": r["from_actor"],
                        "in_reply_to": r["in_reply_to"], "valid": r["validation"] == "valid", "reasons": json.loads(r["reasons"] or "[]"),
                        "body": json.loads(r["body"])})
    for r in db.execute("SELECT * FROM run ORDER BY rowid"):
        prompt = json.loads(r["prompt"] or "{}")
        add(r["started"], {"time": r["started"], "kind": "woke", "source": {"table": "run", "row": r["id"]}, "waking": r["id"], "role": r["role"],
                           "actor": r["actor"], "maker": _maker(r["model"], r["actor"]), "case": r["case_id"],
                           "prompt": prompt.get("text", "") if isinstance(prompt, dict) else str(prompt)})
        if r["ended"]:
            add(r["ended"], {"time": r["ended"], "kind": "slept", "source": {"table": "run", "row": r["id"]}, "waking": r["id"], "role": r["role"],
                             "outcome": r["outcome"]})
    model_turn: dict[str, int] = {}
    for r in db.execute("SELECT * FROM turn ORDER BY run_id, seq"):
        src = {"table": "turn", "row": f"{r['run_id']}/{r['seq']}"}
        if r["kind"] == "model":
            model_turn[r["run_id"]] = r["seq"]
            add(r["time"], {"time": r["time"], "kind": "turn", "source": src, "waking": r["run_id"], "turn": r["seq"], "seconds": r["seconds"] or 0.0,
                            "model": None, "thinking": r["thinking"] or "", "text": r["text"] or ""})
        elif r["kind"] == "results":
            add(r["time"], {"time": r["time"], "kind": "results", "source": src, "waking": r["run_id"], "turn": model_turn.get(r["run_id"], 1)})
    for r in db.execute("SELECT * FROM call ORDER BY rowid"):
        written = _t(r["time"]) + timedelta(seconds=r["seconds"] or 0)
        inputs = json.loads(r["inputs"] or "{}")
        src = {"table": "call", "row": r["id"]}
        if r["tool"] in DIALOGUE and not r["error"]:
            ev = {"time": r["time"], "kind": "dialogue", "source": src, "id": r["id"], "case": None, "tool": r["tool"], "actor": "agent", "inputs": inputs}
            if r["tool"] == "consent":
                ev["within_brief"] = bool(inputs.get("brief"))
            add(written, ev)
        elif not r["tool"].startswith("send_"):
            add(written, {"time": r["time"], "kind": "call", "source": src, "id": r["id"], "waking": r["run_id"], "turn": r["turn"], "tool": r["tool"],
                          "seconds": r["seconds"] or 0.0, "error": bool(r["error"]), "inputs": inputs,
                          "about": inputs.get("design") or inputs.get("plan")})
    for r in db.execute("SELECT * FROM case_state"):
        last = db.execute("SELECT MAX(time) AS t FROM message").fetchone()["t"]
        add(_t(last) + timedelta(milliseconds=1), {"time": last, "kind": "case", "source": {"table": "case_state", "row": r["case_id"]}, "case": r["case_id"],
                                                  "phase": r["phase"], "negotiation": r["negotiation"], "status": r["status"],
                                                  "accepted_plan": r["accepted_plan"], "mandate": json.loads(r["mandate"] or "{}"),
                                                  "requirement_version": r["requirement_version"] or 0, "referred": bool(r["referred"])})
    db.close()
    status = json.loads((folder / "status.json").read_text())
    if status.get("ended"):
        result = json.loads((folder / "result.json").read_text())
        add(status["ended"], {"time": status["ended"], "kind": "ended", "source": {"table": "result.json", "row": "outcome"},
                              "outcome": result.get("outcome") or "ended", "reason": result.get("reason")})
    rows.sort(key=lambda x: (x[0], x[1]))
    out = []
    for seq, (_, _, e) in enumerate(rows, start=1):
        e = {"seq": seq, **e}
        e["time"] = e["time"] if e["time"].endswith("Z") else e["time"].replace("+00:00", "Z")
        out.append(e)
    return out


def run_document(folder: Path, run_id: str, scenario: tuple[str, str] | None, order: dict | None) -> dict:
    """The run as the frame names it (`runs-1` without makers and last), from the folder's JSON files."""
    run, status = json.loads((folder / "run.json").read_text()), json.loads((folder / "status.json").read_text())
    result = json.loads((folder / "result.json").read_text()) if (folder / "result.json").exists() else {}
    return {"id": run_id, "order": order, "scenario": {"experiment": scenario[0], "condition": scenario[1]} if scenario else None,
            "lineages": run.get("lineages") or [], "settings": run.get("settings") or {}, "version": "0123456789ab",
            "status": "done" if status.get("status") == "done" else "running", "started": run["created"], "ended": status.get("ended"),
            "outcome": result.get("outcome"), "reason": result.get("reason")}


class StubFrame:
    """The frame's endpoints over the documents a test gives it: `presence`; `runs`, run id -> its stages, each {run, events,
    dialogue, presence}, the first standing and the next taken when the owner's word is taken (`add_run`, `then`); the orders
    placed; the pictures of the versions the runs drew, (run, design) -> (bytes, content type); the accepted versions' feature lists
and files, (run, design, file) -> (bytes, content type). `served` is how many
    events of each run may be served, for a run followed while it grows; `at` the frame's clock in the documents it composes
    (presence's `at` when None)."""

    def __init__(self, presence: dict | None = None, token: str = "s3cret"):
        self.presence = presence if presence is not None else body("presence-empty")
        self.token = token
        self.at: str | None = None
        self.runs: dict[str, dict] = {}
        self.served: dict[str, int] = {}
        self.orders: dict[str, dict] = {}              # ref -> {"sha256", "document"}
        self.pictures: dict[tuple[str, str], tuple[bytes, str]] = {}
        self.features: dict[tuple[str, str], dict] = {}
        self.files: dict[tuple[str, str, str], tuple[bytes, str]] = {}
        self.asked: list[str] = []
        self.words: list[tuple[str, dict]] = []        # the words taken, with their run
        self.refuse_with: list[str] | None = None      # the reasons of a 422 to an order placed, when set
        self.broken: str | None = None                 # a document served out of its schema's form
        self.preparing = False                         # a run being prepared: a maker placed stands as `next`
        # the answer whose words the stub cannot compute, as recorded for the request that drew it
        self.recorded = [example("dialogue-word-422")]

    def add_run(self, run: dict, events: list[dict], makers: dict | None = None, dialogue: dict | None = None,
                presence: dict | None = None) -> None:
        self.runs[run["id"]] = {"run": run, "events": events, "makers": makers or {}, "dialogue": dialogue, "presence": presence, "next": []}

    def then(self, run_id: str, run: dict, events: list[dict], dialogue: dict | None = None, presence: dict | None = None) -> None:
        """What the run goes on to once the owner's word is taken: its run, its events and dialogue then, the presence then."""
        r = self.runs[run_id]
        r["next"].append({"run": run, "events": events, "makers": r["makers"], "dialogue": dialogue, "presence": presence, "next": []})

    def now(self) -> str:
        return self.at or self.presence["at"]

    def _status_at(self, rid: str) -> dict:
        r = self.runs[rid]
        n = self.served.get(rid, len(r["events"]))
        doc = dict(r["run"])
        if n < len(r["events"]):
            doc.update(status="running", ended=None, outcome=None, reason=None, result=None)
        return doc

    def _last(self, rid: str) -> int:
        r = self.runs[rid]
        n = self.served.get(rid, len(r["events"]))
        return r["events"][n - 1]["seq"] if n else 0

    def dialogue_of(self, rid: str) -> dict:
        """The run's dialogue as the frame serves it: the stage's, or for a run without one its thread empty and nothing waiting."""
        r, run = self.runs[rid], self._status_at(rid)
        doc = dict(r["dialogue"]) if r["dialogue"] is not None else \
            {"schema": "dialogue/1", "at": self.now(), "run": {"id": rid, "order": run.get("order"), "status": run["status"]}, "waits": None, "thread": []}
        if run["status"] != "parked":
            doc = {**doc, "waits": None, "run": {**doc["run"], "status": run["status"]}}
        return {**doc, "at": self.at or doc["at"]}

    def _recorded(self, method: str, path: str, sent) -> JSONResponse | None:
        for e in self.recorded:
            q = e["request"]
            if q["method"] == method and q["path"] == path and q.get("body") == sent:
                return JSONResponse(e["body"], e["status"])
        return None

    def _word(self, rid: str, word: dict) -> JSONResponse | dict:
        """The owner's word, answered as the frame answers it."""
        if not self.runs[rid]["run"].get("order"):
            return JSONResponse({"error": f"the run {rid} is an experiment's, not an order's: it has no owner to give a word"}, 403)
        found = errors(word, "dialogue-1.json", "word") if isinstance(word, dict) else ["(the document): not an object"]
        if found:
            return JSONResponse({"error": "the schema refuses the document", "reasons": found}, 422)
        status = self._status_at(rid)["status"]
        if status != "parked":
            state = {"running": "being prepared", "done": "ended"}.get(status, status)
            return JSONResponse({"error": f"the run {rid} is not parked: it is {state}; a word is taken only while the run waits for the owner's word"}, 409)
        waits = self.dialogue_of(rid)["waits"]
        on = word.get("showing") or word.get("question")
        what = "showing" if word.get("showing") else "question"
        if waits is None or on != waits["dialogue"] or what != waits["what"]:
            return JSONResponse({"error": f"the word is on {what} {on}, which does not wait: the {waits['what']} {waits['dialogue']} waits for the "
                                          f"owner's word since {waits['since']}"}, 409)
        if (refused := self._recorded("POST", f"/runs/{rid}/dialogue", word)) is not None:
            return refused
        if word["word"] == "accept":
            ways = waits["entry"].get("alternatives") or []
            way = next((a for a in ways if a["name"] == word.get("alternative")), ways[0] if len(ways) == 1 else None)
            if way is None:
                return JSONResponse({"error": f"the showing {on} has {len(ways)} alternatives: the acceptance names the one it accepts"}, 422)
            relaxed = {r["replaces"]: r["margin"] for r in word.get("relaxes") or []}
            for f in way["at_risk"]:
                if relaxed.get(f["replaces"]) is None or relaxed[f["replaces"]] < f["reaches"]:
                    return JSONResponse({"error": f"the acceptance does not relax {f['replaces']}'s margin to what the plan reaches, {f['reaches']}: "
                                                  "a plan at risk is accepted only with its margins relaxed to what it reaches"}, 422)
        self.words.append((rid, word))
        r = self.runs[rid]
        if r["next"]:
            stage = r["next"].pop(0)
            stage["next"] = r["next"]
            self.runs[rid] = r = stage
            self.served.pop(rid, None)
            if stage["presence"] is not None:
                self.presence = stage["presence"]
            thread = (r["dialogue"] or {}).get("thread") or []
            call = next((e["call"] for e in reversed(thread) if e["actor"] == "owner" and e["kind"] == WORDS[word["word"]]), f"call-stub-{len(self.words)}")
        else:
            r["run"] = {**r["run"], "status": "running", "ended": None, "outcome": None, "reason": None, "result": None}
            for x in self.presence.get("runs", []):
                if x["id"] == rid:
                    x["state"] = "preparing"
            call = f"call-stub-{len(self.words)}"
        return {"schema": "said/1", "run": rid, "word": word["word"], "call": call, "status": "running"}

    def app(self) -> FastAPI:
        api = FastAPI()

        def authorised(request: Request):
            if request.headers.get("authorization") != f"Bearer {self.token}":
                missing = "missing" if not request.headers.get("authorization") else "not one the frame knows"
                return JSONResponse({"error": f"a bearer token is {missing}: Authorization: Bearer <token>, a token listed in {TOKENS_FILE}"}, 401)
            return None

        def no_run(run_id: str):
            return JSONResponse({"error": f"no run {run_id} at this frame"}, 404)

        @api.get("/presence")
        def presence(request: Request):
            self.asked.append("/presence")
            if (refused := authorised(request)) is not None:
                return refused
            if self.broken == "presence":
                return {**self.presence, "down_after": "thirty"}
            return self.presence

        @api.get("/runs")
        def runs(request: Request):
            self.asked.append("/runs")
            if (refused := authorised(request)) is not None:
                return refused
            docs = [{**self._status_at(rid), "makers": r["makers"], "last": self._last(rid)} for rid, r in self.runs.items()]
            return {"schema": "runs/1", "at": self.now(), "runs": docs}

        @api.get("/runs/{run_id:path}/events")
        def events(run_id: str, request: Request, after: int = 0):
            self.asked.append(f"/runs/{run_id}/events?after={after}")
            if (refused := authorised(request)) is not None:
                return refused
            if run_id not in self.runs:
                return no_run(run_id)
            r = self.runs[run_id]
            n = self.served.get(run_id, len(r["events"]))
            evs = [e for e in r["events"][:n] if e["seq"] > after]
            return {"schema": "events/1", "at": self.now(), "run": self._status_at(run_id), "after": after, "last": evs[-1]["seq"] if evs else after,
                    "events": evs}

        @api.get("/runs/{run_id:path}/dialogue")
        def dialogue(run_id: str, request: Request):
            self.asked.append(f"/runs/{run_id}/dialogue")
            if (refused := authorised(request)) is not None:
                return refused
            if run_id not in self.runs:
                return no_run(run_id)
            return self.dialogue_of(run_id)

        @api.post("/runs/{run_id:path}/dialogue")
        async def say(run_id: str, request: Request):
            self.asked.append(f"POST /runs/{run_id}/dialogue")
            if (refused := authorised(request)) is not None:
                return refused
            if run_id not in self.runs:
                return no_run(run_id)
            try:
                word = json.loads(await request.body())
            except ValueError:
                return JSONResponse({"error": "the schema refuses the document", "reasons": ["(the document): not JSON"]}, 422)
            return self._word(run_id, word)

        @api.get("/runs/{run_id:path}/designs/{design}/picture.png")
        def picture(run_id: str, design: str, request: Request):
            self.asked.append(f"/runs/{run_id}/designs/{design}/picture.png")
            if (refused := authorised(request)) is not None:
                return refused
            if run_id not in self.runs:
                return no_run(run_id)
            if (run_id, design) not in self.pictures:     # the frame's words for a version it has no picture of
                said = f"the run {run_id} made no design {design}" if DESIGN.fullmatch(design) else f"no design {design} in the run {run_id}"
                return JSONResponse({"error": said}, 404)
            data, media = self.pictures[(run_id, design)]
            return Response(data, media_type=media)

        @api.get("/runs/{run_id:path}/features/{design}/{name}")
        def feature_file(run_id: str, design: str, name: str, request: Request):
            if (refused := authorised(request)) is not None:
                return refused
            if (run_id, design, name) not in self.files:
                return JSONResponse({"error": f"no {name} of an accepted version {design} in the run {run_id}"}, 404)
            data, media = self.files[(run_id, design, name)]
            return Response(data, media_type=media)

        @api.get("/runs/{run_id:path}/features/{design}")
        def features(run_id: str, design: str, request: Request):
            if (refused := authorised(request)) is not None:
                return refused
            if (run_id, design) not in self.features:
                return JSONResponse({"error": f"{design} is no version the run {run_id} accepted"}, 404)
            return self.features[(run_id, design)]

        @api.delete("/runs/{run_id:path}")
        def delete(run_id: str, request: Request):
            self.asked.append(f"DELETE /runs/{run_id}")
            if (refused := authorised(request)) is not None:
                return refused
            if run_id not in self.runs and run_id not in self.orders:
                return no_run(run_id)
            if run_id in self.runs and not self.runs[run_id]["run"].get("order"):
                return JSONResponse({"error": f"the run {run_id} is an experiment's, not an order's"}, 403)
            if run_id in self.runs and self._status_at(run_id)["status"] == "running":
                return JSONResponse({"error": f"the run {run_id} is being prepared; it can be deleted once it has ended or parked"}, 409)
            self.runs.pop(run_id, None)
            self.orders.pop(run_id, None)
            self.presence["runs"] = [r for r in self.presence["runs"] if r["id"] != run_id]
            return {"deleted": run_id}

        @api.put("/roles/{role}")
        async def put_role(role: str, request: Request):
            self.asked.append(f"PUT /roles/{role}")
            if (refused := authorised(request)) is not None:
                return refused
            part = next((p for p in self.presence["parts"] if p["id"] == role and p["kind"] == "role"), None)
            if part is None:
                return JSONResponse({"error": f"no role {role} at this frame"}, 404)
            maker = json.loads(await request.body())
            r = part["role"]
            if maker != r["maker"] and maker not in r.get("alternatives", []):
                # the alternatives presence offers the role, each once, as the frame names them
                names = ", ".join(f"{m['kind']} {m['name']}" if m.get("name") else m["kind"] for m in r.get("alternatives", []))
                return JSONResponse({"error": "the schema refuses the document",
                                     "reasons": [f"maker: {maker.get('kind')} {maker.get('name')} is not among the alternatives of the {role}: {names}"]}, 422)
            if self.preparing and maker != r["maker"]:
                r["next"] = maker                               # a run is being prepared: it stands until the role wakes
            elif maker != r["maker"]:
                r["alternatives"] = [a for a in r.get("alternatives", []) if a != maker] + [r["maker"]]
                r["maker"], r["next"] = maker, None
            return self.presence

        @api.get("/orders/{ref}")
        def order(ref: str, request: Request):
            if (refused := authorised(request)) is not None:
                return refused
            if ref not in self.orders:
                return JSONResponse({"error": f"no order {ref} at this frame"}, 404)
            return self.orders[ref]["document"]

        @api.post("/orders", status_code=201)
        async def place(request: Request):
            if (refused := authorised(request)) is not None:
                return refused
            raw = await request.body()
            if self.refuse_with:
                return JSONResponse({"error": "the schema refuses the document", "reasons": self.refuse_with}, 422)
            try:
                doc = validate_order(json.loads(raw))
            except (ValueError, SchemaError) as e:
                return JSONResponse({"error": "the schema refuses the document", "reasons": getattr(e, "errors", [str(e)])}, 422)
            ref = f"{doc['lineage']}@{doc['revision']}"
            if ref in self.orders or ref in self.runs:
                return JSONResponse({"error": f"the order version {ref} is placed already (runs/orders/{ref})"}, 409)
            self.orders[ref] = {"sha256": sha256(canonical(doc)), "document": doc}
            o = {"lineage": doc["lineage"], "revision": doc["revision"], "sha256": self.orders[ref]["sha256"]}
            self.presence.setdefault("runs", []).append({"id": ref, "order": o, "state": "placed", "since": self.now(), "outcome": None})
            return {"run": ref, "order": o, "state": "placed", "events": f"/runs/{ref}/events"}

        return api


# -------------------------------------------------------------------- the held mass order, as the examples hold it

def _stage(name: str, run_id: str, order: dict | None, at: str | None) -> dict:
    """One state of the held mass order's run, from the examples: {run, events, dialogue, presence}."""
    def fix(doc):
        doc["run"] = {k: v for k, v in doc["run"].items() if k not in ("makers", "last")}   # the run as events-1 names it
        doc = renamed(doc, run_id, order) if order else doc
        return shifted(doc, at, frm=FIRST) if at else doc
    if name == "preparing":
        return fix({"run": body("runs-preparing")["runs"][0], "events": body("events-preparing")["events"], "dialogue": None,
                    "presence": body("presence-preparing")})
    if name == "parked":
        return fix({"run": body("runs-parked")["runs"][0], "events": body("events-parked")["events"], "dialogue": body("dialogue-parked"),
                    "presence": body("presence-parked")})
    if name == "parked-again":
        return fix({"run": body("runs-parked-again")["runs"][0], "events": body("events-parked-again")["events"],
                    "dialogue": body("dialogue-parked-again"), "presence": body("presence-parked-again")})
    if name == "accepted":
        return fix({"run": body("runs-accepted")["runs"][0], "events": body("events-accepted")["events"], "dialogue": body("dialogue-accepted"),
                    "presence": body("presence-ended")})
    raise ValueError(name)


FIRST = body("presence-empty")["at"]
STAGES = ("preparing", "parked", "parked-again", "accepted")


def held_mass(stage: str = "parked", run_id: str = HELD, order: dict | None = None, at: str | None = None, token: str = "s3cret") -> StubFrame:
    """A stub with the held mass order's run in a state the examples hold (`empty`, `preparing`, `parked`, `parked-again`,
    `accepted`), the later states its stages after the owner's words: the refusal with conditions goes on to the second parking,
    the acceptance to the accepted run. `run_id` and `order` name it as another order version, `at` puts the first example's
    time there."""
    if stage == "empty":
        return StubFrame(shifted(body("presence-empty"), at) if at else body("presence-empty"), token)
    first = _stage(stage, run_id, order, at)
    stub = StubFrame(first["presence"], token)
    makers = body("runs-accepted")["runs"][0]["makers"]
    stub.add_run(first["run"], first["events"], makers, first["dialogue"], first["presence"])
    if stage in ("parked", "parked-again"):
        for later in STAGES[STAGES.index(stage) + 1:]:
            s = _stage(later, run_id, order, at)
            stub.then(run_id, s["run"], s["events"], s["dialogue"], s["presence"])
    if stage != "preparing":                             # the version shown at the first parking, its picture as the run drew it
        design, data, content_type = drawn_picture()
        stub.pictures[(run_id, design)] = (data, content_type)
    if order is None:                                    # the version placed, as the frame holds it
        placed = example("orders-post-201")["request"]["body"]
        stub.orders[HELD] = {"sha256": body("runs-parked")["runs"][0]["order"]["sha256"], "document": placed}
    if stage == "accepted":
        features = body("features-accepted")
        stub.features[(run_id, features["design"])] = features
        for name, data, content_type in served_files():
            stub.files[(run_id, features["design"], name)] = (data, content_type)
    return stub


FILES = ("features-accepted-picture", "features-accepted-model-stl", "features-accepted-model-3mf")


def drawn_picture() -> tuple[str, bytes, str]:
    """The picture of the version shown at the first parking as the run drew it: (design, bytes, content type), the bytes kept
    beside the example."""
    e = example("designs-picture")
    return e["request"]["path"].split("/designs/", 1)[1].split("/", 1)[0], (CONTRACT / e["bytes"]).read_bytes(), e["content_type"]


def served_files() -> list[tuple[str, bytes, str]]:
    """The accepted version's picture and models as the frame served them: (file, bytes, content type), the bytes kept beside
    each example."""
    out = []
    for n in FILES:
        e = example(n)
        out.append((e["request"]["path"].rsplit("/", 1)[1], (CONTRACT / e["bytes"]).read_bytes(), e["content_type"]))
    return out


def wake(stub: StubFrame, role: str) -> None:
    """The role wakes in the run being prepared: the maker placed as `next` becomes its maker, as the frame's run takes it."""
    r = next(p for p in stub.presence["parts"] if p["id"] == role)["role"]
    if r.get("next"):
        r["alternatives"] = [a for a in r.get("alternatives", []) if a != r["next"]] + [r["maker"]]
        r["maker"], r["next"] = r["next"], None
