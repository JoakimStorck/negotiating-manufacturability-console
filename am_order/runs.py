"""The runs of am-llm as the tool reads them: a catalogue of recorded runs under a root, and one run read into events in time
order, with the state of the organisation at any time in it.

A run is a folder with a `record.db` (am-llm's record, read only, directly: the tool never imports am-llm), beside which the
experiment runner leaves `run.json` (when it started, which design lineages), `status.json` (done or running, when it ended) and
`result.json` (the outcome). The catalogue walks the root two levels down, as `runs/experiments/<experiment>/<condition>/` is laid
out, and reads the JSON files only; the record is opened when a run is listed with its decision makers or read.

What the picture shows is read from five tables: `message` (the protocol's traffic between the roles), `call` (the requester's
dialogue, by the tools that carry it), `run` (when a role was awake, as which actor and model), `design` (the versions as they were
made) and `case_state` (the mandate in force and the accepted plan at the end). Every row has a time; the events are the rows in
time order, and the state at a time is what the rows before it say. The clock that plays a run back, and the one that follows a
live run, are the same reading with the time moving.

A run of a standing frame is read the same way from its events as the frame serves them (`events-1`, `from_events`): one reader
with two sources, the folder's tables and the frame's events, giving the same `Run`, so that the page is the same code for both.
The frame's events carry what the tables are not read for here (a showing's findings and certificate, an acceptance's
relaxations, a plan's verdict, a case parked for the owner); they are kept beside the picture (`Event.detail`, `Run.plans`,
`Run.parked`), never in it.
"""
from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROLES = ("requester", "design_engineer", "process_planner", "production_planner", "quality_engineer",
         "machine_operator", "maintenance_technician")
RANK = {"requester": 0, "design_engineer": 1, "process_planner": 2, "production_planner": 2, "quality_engineer": 2,
        "machine_operator": 3, "maintenance_technician": 3}
TITLES = {"requester": "Requester", "design_engineer": "Design engineer", "process_planner": "Process planner",
          "production_planner": "Production planner", "quality_engineer": "Quality engineer",
          "machine_operator": "Machine operator", "maintenance_technician": "Maintenance technician"}
TYPES = ("assignment", "status", "query", "answer", "proposal", "report", "escalation")
# the requester's dialogue: the tool that carries each call, whether it goes down (requester to design engineer) and its word
DIALOGUE = {"brief": (True, "brief"), "ask_requester": (False, "question"), "answer_requester": (True, "answer"),
            "remark": (True, "remark"), "show_design": (False, "showing"), "accept_design": (True, "acceptance"),
            "decline_order": (True, "order declined"), "consent": (True, "consent")}
# what counts as a decision: the orderer's side of the dialogue, a plan accepted, an order declined, a mandate changed
DECISIONS = {"answer", "acceptance", "order declined", "consent", "accepted", "extended mandate", "relaxed"}
ORDER_NOTE = re.compile(r"\border ([a-z0-9][a-z0-9-]*)@(\d+)\b")
# what a role does between its words, from the tools it calls while awake: a family for the colour and a word for the reader;
# the tools that say something (send_*, the dialogue) are events and are not activities
ACTS = {"analyse": ("analyse", "analysing"), "sensitivity": ("analyse", "analysing"), "survey_orientations": ("analyse", "analysing"),
        "design_constraints": ("analyse", "analysing"), "brief_bounds": ("analyse", "analysing"),
        "reshape": ("make", "reshaping the design"), "plan_candidate": ("make", "planning"), "restore_plans": ("make", "restoring plans")}


def act_of(tool: str) -> tuple[str, str] | None:
    """The family and the word of a tool call, None for a call that is an event instead."""
    if tool in ACTS:
        return ACTS[tool]
    if tool.startswith("read_"):
        return "read", "reading"
    if tool.startswith("send_") or tool in DIALOGUE:
        return None
    return "other", tool.replace("_", " ")


def _time(s: str | None) -> datetime | None:
    if not s:
        return None
    t = datetime.fromisoformat(s.replace("Z", "+00:00"))
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def _short(model: str | None, actor: str | None) -> str:
    """A decision maker in a word: the model, `scripted` for a policy, `none` for the reference's decision-free routine,
    `operator` for a person in the role."""
    if actor == "operator":
        return "operator"
    model = model or ""
    if model.startswith("scripted:"):
        return "none" if "without a decision maker" in model else "scripted"
    return model.split(":", 1)[-1] or (actor or "unknown")


def _json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _connect(db: Path) -> sqlite3.Connection:
    """The record opened read only, by a file URI, which on Windows must be `file:///C:/...` and not the bare path."""
    conn = sqlite3.connect(f"{Path(db).resolve().as_uri()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _tables(conn) -> set[str]:
    return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type IN ('table', 'view')")}


# -------------------------------------------------------------------- the catalogue

@dataclass
class Entry:
    """A run as the catalogue lists it, from the JSON files beside its record."""
    id: str                       # the folder relative to the root, the run's name in the tool
    experiment: str
    condition: str
    lineages: list[str]
    started: datetime | None
    ended: datetime | None
    status: str                   # done, running, or unknown
    outcome: str | None
    reason: str | None
    negotiation: str | None
    held: str | None
    decision_makers: dict = field(default_factory=dict)
    source: str = "folder"        # folder, or frame: where the run is read from
    last: int = 0                 # the frame's: the last sequence number of the run's events

    @property
    def href(self) -> str:
        """The run's page in the tool."""
        return ("/frame/runs/" if self.source == "frame" else "/runs/") + self.id

    @property
    def minutes(self) -> float | None:
        return (self.ended - self.started).total_seconds() / 60 if self.started and self.ended else None


@dataclass
class Experiment:
    name: str
    started: datetime | None
    runs: list[Entry]

    @property
    def lineages(self) -> list[str]:
        return sorted({l for r in self.runs for l in r.lineages})


def entry(root: Path, folder: Path) -> Entry:
    run, status, result = _json(folder / "run.json"), _json(folder / "status.json"), _json(folder / "result.json")
    settings = run.get("settings") or {}
    rel = folder.relative_to(root).as_posix()
    parts = rel.split("/")
    return Entry(id=rel, experiment=parts[0] if len(parts) > 1 else "", condition=parts[-1], lineages=list(run.get("lineages") or []),
                 started=_time(run.get("created")), ended=_time(status.get("ended")), status=status.get("status") or "unknown",
                 outcome=result.get("outcome"), reason=result.get("reason") or result.get("detail"),
                 negotiation=settings.get("negotiation"), held=settings.get("held"))


def decision_makers(folder: Path) -> dict[str, str]:
    """Who filled each role in the run, from the record's agent runs: the latest run's actor and model per role."""
    db = folder / "record.db"
    if not db.exists():
        return {}
    out: dict[str, str] = {}
    try:
        conn = _connect(db)
        try:
            if "run" in _tables(conn):
                for r in conn.execute("SELECT role, actor, model FROM run ORDER BY started"):
                    out[r["role"]] = _short(r["model"], r["actor"])
        finally:
            conn.close()
    except sqlite3.Error:
        pass
    return out


def catalogue(root: Path, depth: int = 2) -> list[Experiment]:
    """The runs under the root, grouped by experiment folder, newest experiment first; a folder is a run when it holds a record."""
    root = Path(root)
    if not root.is_dir():
        return []
    found: list[Path] = []

    def walk(folder: Path, left: int):
        if (folder / "record.db").exists():
            found.append(folder)
            return
        if left == 0:
            return
        try:
            children = sorted(p for p in folder.iterdir() if p.is_dir() and not p.name.startswith("."))
        except OSError:
            return
        for c in children:
            walk(c, left - 1)

    walk(root, depth)
    by: dict[str, list[Entry]] = {}
    for f in found:
        e = entry(root, f)
        by.setdefault(e.experiment, []).append(e)
    out = []
    for name, runs in by.items():
        started = min((r.started for r in runs if r.started), default=None)
        out.append(Experiment(name, started, sorted(runs, key=lambda r: (r.started or datetime.min.replace(tzinfo=timezone.utc), r.id))))
    out.sort(key=lambda x: (x.started or datetime.min.replace(tzinfo=timezone.utc)), reverse=True)
    return out


def resolve(root: Path, run_id: str) -> Path | None:
    """The run's folder for an id from the catalogue, within the root and holding a record; None otherwise."""
    root = Path(root).resolve()
    if not run_id or run_id.startswith("/") or ".." in run_id.split("/"):
        return None
    folder = (root / run_id).resolve()
    try:
        folder.relative_to(root)
    except ValueError:
        return None
    return folder if (folder / "record.db").exists() else None


# -------------------------------------------------------------------- one run

@dataclass
class Event:
    time: datetime
    kind: str                     # message, dialogue, design, plan, woke, slept, job
    sender: str | None
    recipient: str | None
    type: str                     # the message type, the dialogue word, design, plan, ...
    text: str                     # one line in the reader's language
    valid: bool = True
    decision: bool = False
    ref: str | None = None        # the message id, the design id, the plan id
    detail: dict | None = None    # the frame's: a showing's findings and certificate, an acceptance's relaxations

    @property
    def colour_key(self) -> str:
        return self.type if self.kind == "message" else self.kind


@dataclass
class Act:
    """A stretch of one kind of work within a waking: consecutive calls of the same word, from the first call to the last's end."""
    start: datetime
    end: datetime
    family: str                   # read, analyse, make, other
    word: str
    count: int = 1
    detail: str = ""              # the design or plan the calls name, when they name one


@dataclass
class Turn:
    """One of the model's turns in a waking: it thinks from `start` to `end` and the calls it chose follow, then the results."""
    seq: int
    start: datetime               # the end less the model's seconds, never before the turn before
    end: datetime                 # when the model's turn ended, as the record writes it
    seconds: float
    thinking: str                 # the model's summary of its thinking, where it gives one; whole, as the record keeps it
    text: str                     # what the model said in words, where it did; whole
    acts: list = field(default_factory=list)
    results_end: datetime | None = None   # when the last of its calls had answered


@dataclass
class Bar:
    role: str
    actor: str
    model: str
    start: datetime
    end: datetime | None
    id: str | None = None
    acts: list = field(default_factory=list)      # thinking and calls, in time order, for the activity line
    turns: list = field(default_factory=list)
    prompt: str = ""              # what woke it

    def act_at(self, at: datetime) -> Act | None:
        return next((a for a in self.acts if a.start <= at <= a.end), None)


@dataclass
class Run:
    entry: Entry
    folder: Path
    events: list[Event]
    bars: list[Bar]
    designs: list[tuple[datetime, str]]
    roles: list[str]
    decision_makers: dict
    mandate: dict | None = None
    accepted_plan: str | None = None
    order: tuple[str, int] | None = None     # the order cited by the requirements: (lineage, revision)
    plans: dict = field(default_factory=dict)   # the frame's: plan id -> {design, verdict, findings}
    parked: dict | None = None                  # the frame's: the case parked for the owner's word, while it is
    now: datetime | None = None                 # the frame's clock when its events were last read, for a live run

    @property
    def accepted_design(self) -> str | None:
        """The design of the accepted plan, where the frame says which plan's design it is."""
        p = self.plans.get(self.accepted_plan) if self.accepted_plan else None
        return p["design"] if p else None

    @property
    def start(self) -> datetime | None:
        """When the run started: as the runner wrote it, else the first event."""
        if self.entry.started:
            return self.entry.started
        times = [e.time for e in self.events] + [b.start for b in self.bars]
        return min(times) if times else None

    @property
    def end(self) -> datetime | None:
        """The last time the log knows: the run's end when it has ended, else the latest row."""
        if self.entry.ended:
            return self.entry.ended
        times = [e.time for e in self.events] + [b.end or b.start for b in self.bars]
        return max(times) if times else None

    @property
    def live(self) -> bool:
        return self.entry.status == "running"

    @property
    def is_parked(self) -> bool:
        return self.entry.status == "parked"

    def decisions(self) -> list[Event]:
        return [e for e in self.events if e.decision]


def _cut(text, n: int = 110) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def _message_text(kind: str, body: dict) -> str:
    """One line for a message, from the fields its type carries."""
    if kind == "assignment":
        basis = (body.get("basis") or {}).get("design")
        return _cut((f"on {basis}: " if basis else "") + (body.get("goal") or ""))
    if kind == "status":
        state = body.get("state") or ""
        plan = body.get("plan") or (body.get("basis") or {}).get("plan")
        return _cut(state + (f" · {plan}" if plan else ""))
    if kind == "report":
        bc = body.get("binding_constraint") or {}
        return _cut(bc.get("description") or body.get("analysis") or "")
    if kind == "escalation":
        req = body.get("request") or ""
        bc = body.get("binding_constraint") or {}
        return _cut(f"asks for a {req.replace('_', ' ')}: " + (bc.get("description") or body.get("analysis") or ""))
    if kind == "query":
        return _cut(body.get("question") or "")
    if kind == "answer":
        return _cut(body.get("text") or body.get("decision") or json.dumps({k: v for k, v in body.items() if k in ("decisions", "mandate", "requirements")}))
    if kind == "proposal":
        return _cut(body.get("recommendation") or body.get("offer") or "")
    return ""


def _dialogue_text(tool: str, inputs: dict, result: dict) -> str:
    for key in ("text", "question", "summary", "note"):     # an answer's `question` is the call it answers
        if inputs.get(key):
            return _cut(inputs[key])
    if tool == "consent":
        return _cut(inputs.get("design") or inputs.get("version") or "")
    if tool == "show_design":
        return _cut(inputs.get("design") or "")
    return ""


def read(root: Path, run_id: str) -> Run | None:
    """The run read from its record: events in time order, the roles' waking as bars, the designs, the case's state at the end."""
    folder = resolve(root, run_id)
    if folder is None:
        return None
    e = entry(Path(root).resolve(), folder)
    events: list[Event] = []
    bars: list[Bar] = []
    designs: list[tuple[datetime, str]] = []
    makers: dict[str, str] = {}
    mandate, accepted, order = None, None, None
    conn = _connect(folder / "record.db")
    try:
        tables = _tables(conn)
        if "message" in tables:
            for r in conn.execute("SELECT id, type, from_role, to_role, time, validation, reasons, body FROM message ORDER BY time, rowid"):
                try:
                    body = json.loads(r["body"])
                except ValueError:
                    body = {}
                ok = r["validation"] == "valid"
                text = _message_text(r["type"], body)
                if not ok:
                    try:
                        rule = (json.loads(r["reasons"] or "[]") or [{}])[0]
                    except ValueError:
                        rule = {}
                    text = f"refused, rule {rule.get('rule', '?')} {rule.get('name', '')}".rstrip() + (f": {text}" if text else "")
                # a decision in the traffic: a plan accepted, or an answer (a mandate extended, a proposal taken or refused)
                decision = ok and ((r["type"] == "status" and body.get("state") == "accepted") or r["type"] == "answer")
                events.append(Event(_time(r["time"]), "message", r["from_role"], r["to_role"], r["type"], text, ok, decision, r["id"]))
                if r["type"] == "assignment":
                    for req in body.get("requirements") or []:
                        m = ORDER_NOTE.search(str(req.get("note") or ""))
                        if m and order is None:
                            order = (m.group(1), int(m.group(2)))
        if "run" in tables:
            for r in conn.execute("SELECT id, role, actor, model, prompt, started, ended FROM run WHERE started IS NOT NULL ORDER BY started"):
                label = _short(r["model"], r["actor"])
                makers[r["role"]] = label
                try:
                    prompt = json.loads(r["prompt"] or "{}")
                except ValueError:
                    prompt = {}
                bars.append(Bar(r["role"], r["actor"], label, _time(r["started"]), _time(r["ended"]), r["id"],
                                prompt=((prompt.get("text") if isinstance(prompt, dict) else str(prompt)) or "").strip()))
                events.append(Event(_time(r["started"]), "woke", r["role"], None, "woke", f"{TITLES.get(r['role'], r['role'])} wakes"))
                if r["ended"]:
                    events.append(Event(_time(r["ended"]), "slept", r["role"], None, "slept", f"{TITLES.get(r['role'], r['role'])} sleeps"))
        if bars:
            by_id = {b.id: b for b in bars}
            if "turn" in tables:
                for r in conn.execute("SELECT run_id, seq, kind, time, seconds, text, thinking FROM turn ORDER BY run_id, seq"):
                    bar = by_id.get(r["run_id"])
                    if bar is None:
                        continue
                    t = _time(r["time"])
                    if r["kind"] == "model":
                        floor = bar.turns[-1].results_end or bar.turns[-1].end if bar.turns else bar.start
                        start = max(floor, t - timedelta(seconds=r["seconds"] or 0))
                        bar.turns.append(Turn(r["seq"], start, t, r["seconds"] or 0, (r["thinking"] or "").strip(), (r["text"] or "").strip()))
                    elif r["kind"] == "results" and bar.turns:
                        bar.turns[-1].results_end = t
            if "call" in tables:
                for r in conn.execute("SELECT run_id, turn, tool, time, seconds, inputs FROM call WHERE run_id IS NOT NULL ORDER BY time, rowid"):
                    bar, act = by_id.get(r["run_id"]), act_of(r["tool"])
                    if bar is None or act is None:
                        continue
                    t = _time(r["time"])
                    end = t + timedelta(seconds=r["seconds"] or 0)
                    try:
                        inputs = json.loads(r["inputs"] or "{}")
                    except ValueError:
                        inputs = {}
                    detail = str(inputs.get("design") or inputs.get("plan") or "")
                    turn = next((x for x in bar.turns if x.seq == r["turn"]), None)
                    acts = turn.acts if turn is not None else bar.acts
                    if acts and acts[-1].word == act[1]:
                        last = acts[-1]
                        last.end, last.count, last.detail = max(last.end, end), last.count + 1, detail or last.detail
                    else:
                        acts.append(Act(t, end, act[0], act[1], 1, detail))
            for bar in bars:
                for turn in bar.turns:
                    bar.acts.append(Act(turn.start, turn.end, "think", "thinking", 1, ""))
                    bar.acts.extend(turn.acts)
                bar.acts.sort(key=lambda a: a.start)
        if "call" in tables:
            marks = ",".join("?" * len(DIALOGUE))
            for r in conn.execute(f"SELECT id, time, tool, inputs, result FROM call WHERE tool IN ({marks}) AND error = 0 ORDER BY time, rowid",
                                  tuple(DIALOGUE)):
                try:
                    inputs = json.loads(r["inputs"] or "{}")
                except ValueError:
                    inputs = {}
                down, word = DIALOGUE[r["tool"]]
                if r["tool"] == "consent" and inputs.get("brief"):
                    # the brief's own consent to a version within what it may change: no act of the requester's
                    events.append(Event(_time(r["time"]), "dialogue", "design_engineer", "design_engineer", "brief consent",
                                        _cut(f"within the brief: {inputs.get('design') or ''}"), ref=r["id"]))
                    continue
                a, b = ("requester", "design_engineer") if down else ("design_engineer", "requester")
                events.append(Event(_time(r["time"]), "dialogue", a, b, word, _dialogue_text(r["tool"], inputs, {}), True,
                                    word in DECISIONS, r["id"]))
        if "design" in tables:
            for r in conn.execute("SELECT id, time, made_by_role, made_by_actor FROM design ORDER BY time, version"):
                t = _time(r["time"])
                designs.append((t, r["id"]))
                events.append(Event(t, "design", r["made_by_role"], None, "design", f"{r['id']} made", ref=r["id"]))
        if "plan" in tables and "case_state" in tables:
            for r in conn.execute("SELECT accepted_plan, mandate FROM case_state ORDER BY rowid DESC LIMIT 1"):
                accepted = r["accepted_plan"]
                try:
                    mandate = json.loads(r["mandate"]) if r["mandate"] else None
                except ValueError:
                    mandate = None
    finally:
        conn.close()
    events.sort(key=lambda x: (x.time, {"woke": 0, "design": 1, "message": 2, "dialogue": 2, "slept": 3}.get(x.kind, 2)))
    # the run starts when the runner started it, else with its first message or waking; a design made before that (the lineage's
    # earlier versions, copied into the run's record) is state the run begins with, not an event of the run
    first = [x.time for x in events if x.kind != "design"]
    begin = e.started or (min(first) if first else None)
    if begin is not None:
        events = [x for x in events if x.time >= begin]
    used = {x.sender for x in events if x.sender} | {x.recipient for x in events if x.recipient} | {b.role for b in bars}
    roles = [r for r in ROLES if r in used or r in ("requester", "design_engineer", "process_planner")]
    e.decision_makers = makers
    return Run(e, folder, events, bars, designs, roles, makers, mandate, accepted, order)


# -------------------------------------------------------------------- the state at a time

@dataclass
class State:
    at: datetime
    awake: dict                   # role -> Bar for the roles awake at `at`
    activity: dict                # role -> the Act an awake role is in at `at`, for those in one
    waiting: dict                 # role -> what it waits for, in words (the requester's side when a question stands)
    latest: dict                  # role -> the last event the role sent at or before `at`
    design: str | None            # the latest design version made at or before `at`
    traffic: dict                 # (sender, recipient) -> {type: count} of valid messages at or before `at`
    recent: list                  # the last events at or before `at`, newest last
    seen: int                     # how many events are at or before `at`
    next: Event | None            # the first event after `at`, when the log knows one
    outcome: str | None           # the outcome, once `at` is at or past the run's end


def state(run: Run, at: datetime, recent: int = 6) -> State:
    before = [e for e in run.events if e.time <= at]
    after = [e for e in run.events if e.time > at]
    awake = {b.role: b for b in run.bars if b.start <= at and (b.end is None or b.end > at)}
    activity = {role: a for role, b in awake.items() if (a := b.act_at(at)) is not None}
    latest: dict = {}
    traffic: dict = {}
    for e in before:
        if e.sender and e.kind in ("message", "dialogue"):
            latest[e.sender] = e
        if (e.kind == "message" and e.valid) or (e.kind == "dialogue" and e.sender != e.recipient):
            traffic.setdefault((e.sender, e.recipient), {}).setdefault(e.type, 0)
            traffic[(e.sender, e.recipient)][e.type] += 1
    design = None
    for t, d in run.designs:
        if t <= at:
            design = d
    waiting: dict = {}
    # a question or a showing to the requester stands until the requester's next word down
    open_up = None
    for e in before:
        if e.kind == "dialogue" and e.recipient == "requester":
            open_up = e
        elif e.kind == "dialogue" and e.sender == "requester" and e.type != "brief":
            open_up = None
    if open_up is not None and "requester" not in awake:
        waiting["requester"] = f"{open_up.type} from design engineer waits"
    # a message that asks something waits at its recipient until the recipient wakes or says anything
    for e in reversed(before):
        if e.kind == "message" and e.valid and e.type in ("query", "escalation", "report", "proposal") and e.recipient not in awake:
            answered = any(x.sender == e.recipient and x.time > e.time and x.kind in ("message", "dialogue", "woke") for x in before)
            if e.recipient not in waiting and not answered:
                waiting[e.recipient] = f"{e.type} from {TITLES.get(e.sender, e.sender).lower()} waits"
    outcome = None
    if run.end and at >= run.end and run.entry.status == "done":
        outcome = run.entry.outcome + (f" ({run.entry.reason})" if run.entry.reason else "") if run.entry.outcome else "ended"
    return State(at, awake, activity, waiting, latest, design, traffic, before[-recent:], len(before), after[0] if after else None, outcome)


def picture_of(run: Run, design: str | None) -> Path | None:
    """The design version's picture as the experiment runner leaves it: `pictures/<lineage>-v<n>-<condition>.png` in the
    experiment's folder, else `pictures/<lineage>-v<n>.png`, else the run's own `pictures/`; None when there is none."""
    if not design or "@" not in design:
        return None
    lineage, version = design.split("@", 1)
    name = f"{lineage}-{version}"
    for folder in (run.folder.parent / "pictures", run.folder / "pictures"):
        for candidate in (folder / f"{name}-{run.folder.name}.png", folder / f"{name}.png"):
            if candidate.exists():
                return candidate
    return None


def parse_at(run: Run, text: str | None) -> datetime:
    """The time a page asks for: seconds from the run's start, or an ISO time; the run's end when nothing is asked."""
    end = run.end or run.now or datetime.now(timezone.utc)
    if text is None or text == "":
        return end
    start = run.start or end
    try:
        return start + timedelta(seconds=float(text))
    except ValueError:
        pass
    t = _time(text)
    return t if t else end


# -------------------------------------------------------------------- a run from the frame's events

def entry_of(doc: dict) -> Entry:
    """A frame's run (`runs-1`, or the run of `events-1`) as the catalogue lists one."""
    scenario, order = doc.get("scenario") or None, doc.get("order") or None
    settings = doc.get("settings") or {}
    status = {"running": "running", "parked": "parked", "done": "done"}.get(doc.get("status"), "unknown")
    makers = {role: _maker_word(m) for role, m in (doc.get("makers") or {}).items()}
    return Entry(id=doc["id"], experiment=scenario["experiment"] if scenario else "orders",
                 condition=doc["id"].rsplit("/", 1)[-1] if scenario else f"{order['lineage']}@{order['revision']}" if order else doc["id"],
                 lineages=list(doc.get("lineages") or ([order["lineage"]] if order else [])), started=_time(doc.get("started")),
                 ended=_time(doc.get("ended")), status=status, outcome=doc.get("outcome"), reason=doc.get("reason"),
                 negotiation=settings.get("negotiation"), held=settings.get("held"), decision_makers=makers, source="frame",
                 last=int(doc.get("last") or 0))


def _maker_word(maker: dict | None) -> str:
    """A decision maker in the word the folders give (`_short`): the model, `scripted`, `none`, `operator`."""
    kind = (maker or {}).get("kind")
    if kind == "model":
        return maker.get("name") or "unknown"
    return kind or "unknown"


def from_events(doc_run: dict, events: list[dict], now: datetime | None = None) -> Run:
    """A run read from the frame's events (`events-1`), into the same picture the folder's tables give (`read`)."""
    e = entry_of(doc_run)
    out: list[Event] = []
    bars: list[Bar] = []
    by_id: dict[str, Bar] = {}
    designs: list[tuple[datetime, str]] = []
    makers: dict[str, str] = {}
    plans: dict[str, dict] = {}
    mandate, accepted, parked = None, None, None
    calls, turns = [], []
    for ev in events:
        k, t = ev["kind"], _time(ev["time"])
        if k == "message":
            body = ev.get("body") or {}
            ok = bool(ev["valid"])
            text = _message_text(ev["type"], body)
            if not ok:
                rule = (ev.get("reasons") or [{}])[0]
                text = f"refused, rule {rule.get('rule', '?')} {rule.get('name', '')}".rstrip() + (f": {text}" if text else "")
            decision = ok and ((ev["type"] == "status" and body.get("state") == "accepted") or ev["type"] == "answer")
            out.append(Event(t, "message", ev["from_role"], ev["to_role"], ev["type"], text, ok, decision, ev["id"]))
        elif k == "woke":
            label = _maker_word(ev["maker"])
            makers[ev["role"]] = label
            bar = Bar(ev["role"], ev["actor"], label, t, None, ev["waking"], prompt=(ev.get("prompt") or "").strip())
            bars.append(bar)
            by_id[bar.id] = bar
            out.append(Event(t, "woke", ev["role"], None, "woke", f"{TITLES.get(ev['role'], ev['role'])} wakes"))
        elif k == "slept":
            bar = by_id.get(ev["waking"])
            if bar is not None:
                bar.end = t
            out.append(Event(t, "slept", ev["role"], None, "slept", f"{TITLES.get(ev['role'], ev['role'])} sleeps"))
        elif k in ("turn", "results"):
            turns.append(ev)
        elif k == "call":
            calls.append(ev)
        elif k == "dialogue":
            tool, inputs = ev["tool"], ev.get("inputs") or {}
            if tool not in DIALOGUE:
                continue
            detail = {key: ev[key] for key in ("findings", "relaxations", "certificate") if ev.get(key)} or None
            if tool == "consent" and (ev.get("within_brief") or inputs.get("brief")):
                out.append(Event(t, "dialogue", "design_engineer", "design_engineer", "brief consent",
                                 _cut(f"within the brief: {inputs.get('design') or ''}"), ref=ev["id"]))
                continue
            down, word = DIALOGUE[tool]
            a, b = ("requester", "design_engineer") if down else ("design_engineer", "requester")
            out.append(Event(t, "dialogue", a, b, word, _dialogue_text(tool, inputs, {}), True, word in DECISIONS, ev["id"], detail))
        elif k == "design":
            designs.append((t, ev["id"]))
            out.append(Event(t, "design", ev["made_by_role"], None, "design", f"{ev['id']} made", ref=ev["id"]))
        elif k == "plan":
            plans[ev["id"]] = {"design": ev["design"], "verdict": ev["verdict"], "findings": ev.get("findings") or []}
        elif k == "case":
            accepted, mandate = ev.get("accepted_plan"), ev.get("mandate") or None
        elif k == "parked":
            parked = {"time": t, "case": ev["case"], "what": ev["what"], "dialogue": ev.get("dialogue"), "metrics": ev.get("metrics") or []}
        elif k == "ended":
            parked = None
    # the turns of each waking in their order, then the calls in the order they started (as the folder's tables are read)
    for ev in sorted(turns, key=lambda x: (x["waking"], x["seq"])):
        bar = by_id.get(ev["waking"])
        if bar is None:
            continue
        t = _time(ev["time"])
        if ev["kind"] == "turn":
            floor = bar.turns[-1].results_end or bar.turns[-1].end if bar.turns else bar.start
            start = max(floor, t - timedelta(seconds=ev["seconds"] or 0))
            bar.turns.append(Turn(ev["turn"], start, t, ev["seconds"] or 0, (ev.get("thinking") or "").strip(), (ev.get("text") or "").strip()))
        elif bar.turns:
            bar.turns[-1].results_end = t
    for ev in sorted(calls, key=lambda x: (_time(x["time"]), x["seq"])):
        bar, act = by_id.get(ev.get("waking")), act_of(ev["tool"])
        if bar is None or act is None:
            continue
        t = _time(ev["time"])
        end = t + timedelta(seconds=ev["seconds"] or 0)
        inputs = ev.get("inputs") or {}
        detail = str(inputs.get("design") or inputs.get("plan") or "")
        turn = next((x for x in bar.turns if x.seq == ev.get("turn")), None)
        acts = turn.acts if turn is not None else bar.acts
        if acts and acts[-1].word == act[1]:
            last = acts[-1]
            last.end, last.count, last.detail = max(last.end, end), last.count + 1, detail or last.detail
        else:
            acts.append(Act(t, end, act[0], act[1], 1, detail))
    for bar in bars:
        for turn in bar.turns:
            bar.acts.append(Act(turn.start, turn.end, "think", "thinking", 1, ""))
            bar.acts.extend(turn.acts)
        bar.acts.sort(key=lambda a: a.start)
    designs.sort(key=lambda d: d[0])
    out.sort(key=lambda x: (x.time, {"woke": 0, "design": 1, "message": 2, "dialogue": 2, "slept": 3}.get(x.kind, 2)))
    first = [x.time for x in out if x.kind != "design"]
    begin = e.started or (min(first) if first else None)
    if begin is not None:
        out = [x for x in out if x.time >= begin]
    used = {x.sender for x in out if x.sender} | {x.recipient for x in out if x.recipient} | {b.role for b in bars}
    roles = [r for r in ROLES if r in used or r in ("requester", "design_engineer", "process_planner")]
    e.decision_makers = makers
    order = doc_run.get("order")
    return Run(e, None, out, bars, designs, roles, makers, mandate, accepted, (order["lineage"], order["revision"]) if order else None,
               plans, parked if e.status == "parked" else None, now)
