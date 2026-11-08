"""A standing frame stubbed in the tool's own tests: a FastAPI app that answers as am-llm's frame does (`agents/frame.py`), from
documents the test gives it, so that the tool's tests run on every platform without am-llm.

`record_events` turns a run folder made by `test_runs.make_run` into the events the frame would serve for it, numbered in the
order the record writes its rows (a waking's start as it starts and its end as it ends, a turn as it ends, a call as it answers),
so that the same run can be read both ways and compared.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

from am_order import SchemaError, validate_order
from am_order.order import canonical, sha256

DIALOGUE = ("brief", "ask_requester", "answer_requester", "remark", "show_design", "accept_design", "decline_order", "consent")
TOKENS_FILE = "/home/frame/.config/am-llm/frame-tokens"


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
    """The frame's endpoints over documents the test sets: `presence`, `runs` (run id -> {"run": ..., "events": [...], "makers": ...}),
    the orders placed. `served` is how many events of each run may be served, for a run followed while it grows."""

    def __init__(self, presence: dict, token: str = "s3cret"):
        self.presence = presence
        self.token = token
        self.runs: dict[str, dict] = {}
        self.served: dict[str, int] = {}
        self.orders: dict[str, str] = {}
        self.asked: list[str] = []
        self.refuse_with: list[str] | None = None      # the reasons of a 422, when set
        self.broken: str | None = None                 # a document served out of its schema's form

    def add_run(self, run: dict, events: list[dict], makers: dict) -> None:
        self.runs[run["id"]] = {"run": run, "events": events, "makers": makers}

    def _status_at(self, rid: str) -> dict:
        r = self.runs[rid]
        n = self.served.get(rid, len(r["events"]))
        doc = dict(r["run"])
        if n < len(r["events"]):
            doc.update(status="running", ended=None, outcome=None, reason=None)
        return doc

    def app(self) -> FastAPI:
        api = FastAPI()

        def authorised(request: Request):
            if request.headers.get("authorization") != f"Bearer {self.token}":
                missing = "missing" if not request.headers.get("authorization") else "not one the frame knows"
                return JSONResponse({"error": f"a bearer token is {missing}: Authorization: Bearer <token>, a token listed in {TOKENS_FILE}"}, 401)
            return None

        def now() -> str:
            return self.presence["at"]

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
            docs = []
            for rid, r in self.runs.items():
                n = self.served.get(rid, len(r["events"]))
                docs.append({**self._status_at(rid), "makers": r["makers"], "last": r["events"][n - 1]["seq"] if n else 0})
            return {"schema": "runs/1", "at": now(), "runs": docs}

        @api.get("/runs/{run_id:path}/events")
        def events(run_id: str, request: Request, after: int = 0):
            self.asked.append(f"/runs/{run_id}/events?after={after}")
            if (refused := authorised(request)) is not None:
                return refused
            if run_id not in self.runs:
                return JSONResponse({"error": f"no run {run_id}"}, 404)
            r = self.runs[run_id]
            n = self.served.get(run_id, len(r["events"]))
            evs = [e for e in r["events"][:n] if e["seq"] > after]
            return {"schema": "events/1", "at": now(), "run": self._status_at(run_id), "after": after, "last": evs[-1]["seq"] if evs else after,
                    "events": evs}

        @api.get("/runs/{run_id:path}/designs/{design}/picture.png")
        def picture(run_id: str, design: str, request: Request):
            if (refused := authorised(request)) is not None:
                return refused
            return Response(b"\x89PNG\r\n\x1a\n" + design.encode(), media_type="image/png")

        @api.get("/runs/{run_id:path}/features/{design}/{name}")
        def feature_file(run_id: str, design: str, name: str, request: Request):
            if (refused := authorised(request)) is not None:
                return refused
            return Response(b"solid " + design.encode(), media_type="model/stl" if name.endswith(".stl") else "application/octet-stream")

        @api.get("/runs/{run_id:path}/features/{design}")
        def features(run_id: str, design: str, request: Request):
            if (refused := authorised(request)) is not None:
                return refused
            lineage, _, v = design.partition("@v")
            return {"schema": "features/1", "design": design, "lineage": lineage, "version": int(v), "units": "mm",
                    "features": [],
                    "picture": {"file": "picture.png", "sha256": "0" * 64},
                    "models": [{"format": "stl", "file": "model.stl", "sha256": "0" * 64}, {"format": "3mf", "file": "model.3mf", "sha256": "0" * 64}]}

        @api.delete("/runs/{run_id:path}")
        def delete(run_id: str, request: Request):
            self.asked.append(f"DELETE /runs/{run_id}")
            if (refused := authorised(request)) is not None:
                return refused
            if run_id not in self.runs and run_id not in self.orders:
                return JSONResponse({"error": f"no run {run_id}"}, 404)
            if run_id in self.runs and not self.runs[run_id]["run"].get("order"):
                return JSONResponse({"error": f"{run_id} is an experiment's run, not an order's: the frame deletes only orders' runs"}, 403)
            if run_id in self.runs and self._status_at(run_id)["status"] == "running":
                return JSONResponse({"error": f"the run {run_id} is being prepared; it can be deleted once it has ended or parked"}, 409)
            self.runs.pop(run_id, None)
            self.orders.pop(run_id, None)
            self.presence["runs"] = [r for r in self.presence["runs"] if r["id"] != run_id]
            return {"deleted": run_id}

        @api.post("/orders", status_code=201)
        async def place(request: Request):
            if (refused := authorised(request)) is not None:
                return refused
            body = await request.body()
            if self.refuse_with:
                return JSONResponse({"error": "the schema refuses the document", "reasons": self.refuse_with}, 422)
            try:
                doc = validate_order(json.loads(body))
            except (ValueError, SchemaError) as e:
                return JSONResponse({"error": "the schema refuses the document", "reasons": getattr(e, "errors", [str(e)])}, 422)
            ref = f"{doc['lineage']}@{doc['revision']}"
            if ref in self.orders or ref in self.runs:
                return JSONResponse({"error": f"the order version {ref} is placed already (runs/orders/{ref})"}, 409)
            self.orders[ref] = sha256(canonical(doc))
            return {"run": ref, "order": {"lineage": doc["lineage"], "revision": doc["revision"], "sha256": self.orders[ref]},
                    "state": "placed", "events": f"/runs/{ref}/events"}

        return api


def presence(at: str, parked_run: str | None = None) -> dict:
    """A frame's presence at `at`: the three roles of the cases with their decision makers, a machine down (its sign of life older
    than `down_after`), one unavailable, and a run parked for the owner where one is named."""
    t = _t(at)

    def iso(d: datetime) -> str:
        return d.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    since = iso(t - timedelta(hours=1))
    roles = []
    for role, title, level, maker in (("requester", "Requester", 0, {"kind": "scripted", "name": "reference"}),
                                      ("design_engineer", "Design engineer", 1, {"kind": "model", "name": "claude-sonnet-5-5"}),
                                      ("process_planner", "Process planner", 2, {"kind": "none", "name": None})):
        waits = [{"run": parked_run, "what": "showing", "from": "design_engineer", "since": iso(t - timedelta(minutes=5))}] if parked_run and role == "requester" else []
        roles.append({"id": role, "kind": "role", "since": since, "seen": at, "state": "present",
                      "role": {"title": title, "level": level, "maker": maker, "next": None,
                               "alternatives": [{"kind": "model", "name": "claude-haiku-5-5"}], "awake": None, "waits": waits}})
    machines = [{"id": "virtual-nominal", "kind": "machine", "since": since, "seen": iso(t - timedelta(seconds=300)), "state": "present",
                 "machine": {"class": "fff-3axis-0.4", "adapter": "virtual", "job": None}},
                {"id": "core-one-1", "kind": "machine", "since": since, "seen": at, "state": "unavailable", "note": "no host is configured for its adapter",
                 "machine": {"class": "fff-3axis-0.4", "adapter": "instrumented", "job": None}}]
    runs = [{"id": parked_run, "order": {"lineage": "bracket-mass", "revision": 2, "sha256": "a" * 64}, "state": "parked", "since": iso(t - timedelta(minutes=5)),
             "outcome": None}] if parked_run else []
    return {"schema": "presence/1", "at": at, "down_after": 30.0, "frame": {"name": "workshop-1", "version": "9836798a5c6f", "since": since, "scenario": None},
            "parts": roles + machines, "runs": runs}
