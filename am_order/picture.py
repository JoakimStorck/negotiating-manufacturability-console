"""The overview of a run at a time, as geometry for the page to draw: the roles as cells in their ranks with their decision makers,
the traffic between them, what is awake and what waits, and the time axis with every event marked and the clock's position on it.

Nothing here reads a file; it takes a `runs.Run` and a `runs.State` and returns plain dicts and lists the template turns into SVG.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta

from .runs import DIALOGUE, RANK, TITLES, Event, Run, State

WIDTH = 1200
BOX_W, BOX_H = 230, 74
AXIS_X0, AXIS_X1 = 150, 1130
LANE_H = 24                      # a role's activity line, parallel to the time axis above it
# thinking has one colour on every line, apart from the calls' colours; the calls are what the model chose, the thinking is the model
ACT_COLOURS = {"think": "#b9a7e2", "read": "#b9c7d6", "analyse": "#7aa7d9", "make": "#f2b05e", "other": "#c9c9c9"}
ACT_WORDS = (("thinking", "think"), ("reading", "read"), ("analysing", "analyse"), ("reshaping, planning", "make"))
COLOURS = {"assignment": "#2a78d6", "proposal": "#eb6834", "query": "#1baf7a", "answer": "#eda100", "report": "#e87ba4",
           "escalation": "#008300", "status": "#6250d6", "dialogue": "#52514e", "design": "#0b0b0b", "refused": "#e34948",
           "woke": "#b9c2cc", "slept": "#b9c2cc", "plan": "#8a8f94"}
FILLS = {"awake": "#dce8f7", "waiting": "#fff1c7", "idle": "#f3f5f7", "absent": "#ffffff"}
STROKES = {"awake": "#1f5fa8", "waiting": "#b7791f", "idle": "#c5ccd3", "absent": "#d4d9de"}


def colour(e: Event) -> str:
    if not e.valid:
        return COLOURS["refused"]
    return COLOURS.get(e.type if e.kind == "message" else e.kind, COLOURS["dialogue"])


def _clock(t: datetime, start: datetime | None) -> str:
    """Time since the run's start as h:mm:ss."""
    if start is None:
        return t.strftime("%H:%M:%S")
    s = int((t - start).total_seconds())
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}"


def _span(d: timedelta) -> str:
    s = math.ceil(d.total_seconds())
    if s >= 3600:
        return f"{s // 3600} h {s % 3600 // 60} min"
    if s >= 60:
        return f"{s // 60} min {s % 60} s"
    return f"{s} s"


def ranks(run: Run) -> list[int]:
    """The ranks that have a role in the run, top down; the rows of the picture."""
    return sorted({RANK.get(r, 3) for r in run.roles})


def diagram_width(run: Run) -> float:
    """The block diagram's width: the widest rank's cells, with room beside them for the arrows' labels."""
    by_rank: dict[int, int] = {}
    for r in run.roles:
        by_rank[RANK.get(r, 3)] = by_rank.get(RANK.get(r, 3), 0) + 1
    widest = max(by_rank.values(), default=1)
    return widest * BOX_W + (widest - 1) * 60 + 2 * 270


def lanes_top(run: Run) -> float:
    """The activity lines start at the top of the time picture, with room above them for the clock and "next in"."""
    return 36


def axis_y(run: Run) -> float:
    """The time axis sits below the activity lines, one per role, with room for the marks that stand on it."""
    return lanes_top(run) + len(run.roles) * LANE_H + 40


def nodes(run: Run, st: State) -> list[dict]:
    """A cell per role: its place by rank, its decision maker, its state at the time."""
    by_rank: dict[int, list[str]] = {}
    for r in run.roles:
        by_rank.setdefault(RANK.get(r, 3), []).append(r)
    rows = {rank: 36 + i * 150 for i, rank in enumerate(ranks(run))}
    width = diagram_width(run)
    out = []
    for rank, roles in by_rank.items():
        n = len(roles)
        gap = 60
        total = n * BOX_W + (n - 1) * gap
        x0 = (width - total) / 2
        for i, role in enumerate(roles):
            if role in st.awake:
                mode = "awake"
            elif role in st.waiting:
                mode = "waiting"
            elif role in run.decision_makers:
                mode = "idle"
            else:
                mode = "absent"
            maker = run.decision_makers.get(role)
            out.append({"role": role, "title": TITLES.get(role, role), "x": x0 + i * (BOX_W + gap), "y": rows[rank],
                        "w": BOX_W, "h": BOX_H, "mode": mode, "fill": FILLS[mode], "stroke": STROKES[mode],
                        "maker": {"operator": "a person", "none": "no decision maker", "scripted": "the scripted policy"}.get(maker, maker)
                        if maker else "not woken in this run",
                        "note": st.waiting.get(role) or (_doing(st.activity.get(role)) if mode == "awake" else "")})
    return out


def _doing(act) -> str:
    """What an awake role does, for its cell: the act's word, else just awake."""
    if act is None:
        return "awake"
    if act.detail and act.word in ("reshaping the design", "planning"):
        return f"{act.word.split()[0]} {act.detail}"     # short enough for the cell: "reshaping bracket-mass@v11"
    return act.word


def _anchor(a: dict, b: dict) -> tuple[float, float]:
    """Where an arrow leaves box a towards box b: the middle of the facing side."""
    if b["y"] > a["y"]:
        return a["x"] + a["w"] / 2, a["y"] + a["h"]
    if b["y"] < a["y"]:
        return a["x"] + a["w"] / 2, a["y"]
    if b["x"] > a["x"]:
        return a["x"] + a["w"], a["y"] + a["h"] / 2
    return a["x"], a["y"] + a["h"] / 2


def edges(run: Run, st: State, cells: list[dict]) -> list[dict]:
    """The traffic between pairs of roles so far, one line per direction with its counts, and the latest message bold."""
    by_role = {c["role"]: c for c in cells}
    pairs: dict[tuple, dict] = {}
    for (a, b), counts in st.traffic.items():
        if a in by_role and b in by_role:
            pairs[(a, b)] = counts
    last = next((e for e in reversed(st.recent) if e.kind in ("message", "dialogue") and e.sender != e.recipient), None)
    out = []
    seen = set()
    for (a, b), counts in pairs.items():
        seen.add((a, b))
        out.append(_edge(by_role, a, b, counts, last is not None and (last.sender, last.recipient) == (a, b), last))
    # the dialogue has no message rows: draw it from the latest dialogue event when it is the last thing said
    if last is not None and last.kind == "dialogue" and (last.sender, last.recipient) not in seen and last.sender in by_role and last.recipient in by_role:
        out.append(_edge(by_role, last.sender, last.recipient, {}, True, last))
    return out


def _edge(by_role, a, b, counts, bold, last):
    x1, y1 = _anchor(by_role[a], by_role[b])
    x2, y2 = _anchor(by_role[b], by_role[a])
    # offset the two directions of a pair so that they do not overlap
    dx, dy = (14, 0) if abs(y2 - y1) > abs(x2 - x1) else (0, 14)
    if (a, b) > (b, a):
        dx, dy = -dx, -dy
    words = ", ".join(f"{n} {t}{'s' if n > 1 and not t.endswith('s') else ''}" for t, n in sorted(counts.items(), key=lambda kv: -kv[1]))
    stroke = colour(last) if bold and last is not None else "#8a94a0"
    return {"x1": x1 + dx, "y1": y1 + dy, "x2": x2 + dx, "y2": y2 + dy, "words": words, "bold": bold, "stroke": stroke,
            "label_x": (x1 + x2) / 2 + dx + (10 if dx > 0 else -10 if dx < 0 else 0), "label_y": (y1 + y2) / 2 + dy + (-6 if dy < 0 else 14 if dy > 0 else 4),
            "anchor": "start" if dx > 0 else "end" if dx < 0 else "middle"}


def axis(run: Run, st: State) -> dict:
    """The time axis from the run's start to the last time the log knows, every event a mark, the clock's position on it."""
    start, end = run.start, run.end
    if start is None or end is None:
        return {"marks": [], "ticks": [], "head": AXIS_X0, "start": "", "end": "", "clock": "", "next": None, "live": run.live}
    y = axis_y(run)
    if run.live and st.at > end:
        end = st.at                     # live, the clock at now is the axis's right end
    span = max((end - start).total_seconds(), 1.0)

    def x_of(t: datetime) -> float:
        return AXIS_X0 + (AXIS_X1 - AXIS_X0) * max(0.0, min(1.0, (t - start).total_seconds() / span))

    marks = []
    for e in run.events:
        if e.kind in ("woke", "slept"):
            h = 5
        elif e.decision:
            h = 26
        elif e.kind == "design":
            h = 9
        else:
            h = 16
        marks.append({"x": x_of(e.time), "h": h, "colour": colour(e), "past": e.time <= st.at, "dashed": not e.valid,
                      "title": f"{_clock(e.time, start)} {e.type}" + (f": {e.text}" if e.text else "")})
    step = _tick_step(span)
    ticks = []
    t = 0.0
    while t <= span + 1e-6:
        ticks.append({"x": x_of(start + timedelta(seconds=t)), "label": _clock(start + timedelta(seconds=t), start)})
        t += step
    nxt = None
    if st.next is not None:
        nxt = {"in": _span(st.next.time - st.at), "what": st.next.type, "at": st.next.time.isoformat(),
               "seconds": (st.next.time - start).total_seconds()}
    return {"marks": marks, "ticks": ticks, "head": x_of(st.at), "start": start.strftime("%Y-%m-%d %H:%M:%SZ"),
            "end": end.strftime("%H:%M:%SZ"), "clock": _clock(st.at, start), "next": nxt, "live": run.live,
            "x0": AXIS_X0, "x1": AXIS_X1, "y": y, "top": lanes_top(run), "seconds": (st.at - start).total_seconds(), "span": span,
            "end_seconds": (end - start).total_seconds(), "start_epoch": start.timestamp(), "lanes": lanes(run, st, x_of, end)}


def lanes(run: Run, st: State, x_of, end: datetime) -> list[dict]:
    """One activity line per role, parallel to the axis: its wakings as bars, within them what it did (the acts, coloured by
    family), and on it every event the role sent. What lies after the clock is drawn faint; live, nothing does."""
    start = run.start
    out = []
    for i, role in enumerate(run.roles):
        y = lanes_top(run) + i * LANE_H
        bars, acts = [], []
        for b in run.bars:
            if b.role != role:
                continue
            b_end = b.end or (st.at if st.at > b.start else end)
            bars.append({"x1": x_of(b.start), "x2": max(x_of(b_end), x_of(b.start) + 1), "past": b.start <= st.at,
                         "title": f"{_clock(b.start, start)}–{_clock(b_end, start) if b.end else '…'} awake" + (f" · {b.model}" if b.model else "")})
            for a in b.acts:
                acts.append({"x1": x_of(a.start), "x2": max(x_of(a.end), x_of(a.start) + 1.5), "colour": ACT_COLOURS[a.family],
                             "past": a.start <= st.at, "now": a.start <= st.at <= a.end,
                             "title": f"{_clock(a.start, start)}–{_clock(a.end, start)} {a.word}" + (f" ×{a.count}" if a.count > 1 else "")
                             + (f" · {a.detail}" if a.detail else "") + (f" · {_span(a.end - a.start)}" if a.family == "think" else "")})
        marks = [{"x": x_of(e.time), "colour": colour(e), "past": e.time <= st.at, "decision": e.decision, "dashed": not e.valid,
                  "title": f"{_clock(e.time, start)} {e.type}" + (f": {e.text}" if e.text else "")}
                 for e in run.events if e.sender == role and e.kind in ("message", "dialogue", "design")]
        out.append({"role": role, "title": TITLES.get(role, role), "y": y, "h": LANE_H, "bars": bars, "acts": acts, "marks": marks,
                    "awake": role in st.awake})
    return out


def _tick_step(span: float) -> float:
    for step in (10, 30, 60, 120, 300, 600, 900, 1800, 3600, 7200, 14400, 43200, 86400):
        if span / step <= 12:
            return step
    return 86400 * max(1, int(span / 86400 / 12))


def jumps(run: Run, st: State) -> dict:
    """Where the page can go from here: the previous and next event, the previous and next decision, the start, the end; as
    seconds from the start with the record's microseconds, so that a jump lands on the event and the next jump leaves it."""
    start = run.start
    if start is None:
        return {}

    def s(t: datetime) -> str:
        return f"{(t - start).total_seconds():.6f}"

    here = timedelta(microseconds=500)   # an event this close to the clock is the one the clock stands on
    before = [e for e in run.events if e.time < st.at - here]
    after = [e for e in run.events if e.time > st.at + here]
    decisions_before = [e for e in before if e.decision]
    decisions_after = [e for e in after if e.decision]
    # a turn's end is where the model's choice is known: the thinking done, the calls chosen
    ends = sorted(t.end for b in run.bars for t in b.turns)
    turns_before = [t for t in ends if t < st.at - here]
    turns_after = [t for t in ends if t > st.at + here]
    return {"start": "0", "end": s(run.end) if run.end else None,
            "previous": s(before[-1].time) if before else None, "next": s(after[0].time) if after else None,
            "previous_decision": s(decisions_before[-1].time) if decisions_before else None,
            "next_decision": s(decisions_after[0].time) if decisions_after else None,
            "previous_turn": s(turns_before[-1]) if turns_before else None, "next_turn": s(turns_after[0]) if turns_after else None,
            "here": s(st.at)}


def sentences(st: State, start: datetime | None) -> list[dict]:
    """The recent events as lines a reader follows: the clock, who, to whom, what."""
    out = []
    for e in st.recent:
        who = TITLES.get(e.sender, e.sender or "")
        to = TITLES.get(e.recipient, e.recipient or "")
        if e.kind == "message":
            head = f"{who} → {to}: {e.type}"
        elif e.kind == "dialogue":
            head = f"{who} → {to}: {e.type}" if e.sender != e.recipient else f"{who}: {e.type}"
        elif e.kind == "design":
            head = f"{who}: new design version"
        else:
            head = e.text
        notes, certificate = details(e.detail)
        out.append({"clock": _clock(e.time, start), "head": head, "text": e.text if e.kind != "woke" and e.kind != "slept" else "",
                    "colour": colour(e), "decision": e.decision, "valid": e.valid, "notes": notes, "certificate": certificate})
    return out


def _value(v) -> str:
    if isinstance(v, dict):
        return ", ".join(f"{k.replace('_', ' ')} {_value(x)}" for k, x in v.items())
    if isinstance(v, float):
        return f"{v:g}"
    return str(v)


def details(detail: dict | None) -> tuple[list[str], dict | None]:
    """What the frame's events say of a showing and an acceptance, in words: the findings at risk or critical, each relaxation
    an acceptance makes, and the certificate of exhausted means as one block with its citations."""
    if not detail:
        return [], None
    notes = []
    for f in detail.get("findings") or []:
        name = f.get("metric") or f.get("requirement")
        where = f" at {f['feature']}" if f.get("feature") else ""
        status = f["status"].replace("_", " ")
        if f.get("value") is not None and f.get("margin") is not None and f["status"] == "at_risk":
            notes.append(f"{name}{where} {status}: {f['value']:g} against the margin {f['margin']:g}")
        elif f.get("value") is not None and f.get("limit") is not None:
            notes.append(f"{name}{where} {status}: {f['value']:g} against the limit {f['limit']:g}")
        else:
            notes.append(f"{name}{where} {status}")
    for r in detail.get("relaxations") or []:
        name = r.get("metric") or r.get("requirement")
        what = "the margin on " if r.get("what") == "margin" else ""
        within = {True: " within its mandate", False: " beyond its mandate"}.get(r.get("within_mandate"), "")
        notes.append(f"{what}{name} relaxed from {_value(r.get('from'))} to {_value(r.get('to'))}{within}")
    c = detail.get("certificate")
    return notes, ({"text": c["text"], "cites": list(c.get("cites") or [])} if c else None)


def _fold(text: str, n: int = 320) -> tuple[str, str]:
    """A text as a lead and a rest: the lead ends at a word before `n` characters; a short text is all lead."""
    text = text or ""
    if len(text) <= n + 40:
        return text, ""
    cut = text.rfind(" ", 0, n)
    cut = cut if cut > n // 2 else n
    return text[:cut], text[cut:].lstrip()


def wakings(run: Run, st: State) -> list[dict]:
    """What each awake role is doing, for the reader to inspect: what woke it, its turns so far (the thinking, the calls), and
    where it stands at the clock. A turn is shown when it has ended, since that is when the record writes it."""
    start = run.start
    out = []
    for role, b in st.awake.items():
        done = [t for t in b.turns if t.end <= st.at]
        turns = [{"n": i, "seq": t.seq, "clock": _clock(t.end, start), "seconds": f"{t.seconds:.0f} s", "thinking": _fold(t.thinking), "text": _fold(t.text),
                  "acts": [{"word": a.word, "count": a.count, "detail": a.detail, "seconds": f"{(a.start - start).total_seconds():.6f}",
                            "clock": _clock(a.start, start), "future": a.start > st.at} for a in t.acts]}
                 for i, t in enumerate(done, 1)]
        current = next((t for t in b.turns if t.start <= st.at < t.end), None)
        if current is not None:
            now = f"turn {b.turns.index(current) + 1}: thinking, {_span(st.at - current.start)} so far"
        elif done and done[-1].results_end and st.at < done[-1].results_end:
            now = f"turn {len(done)}: the tools answer"
        else:
            last_end = (done[-1].results_end or done[-1].end) if done else b.start
            now = f"at work for {_span(st.at - last_end)}, nothing written yet" if st.at > last_end else None
        out.append({"role": role, "title": TITLES.get(role, role), "since": _clock(b.start, start), "model": b.model, "prompt": _fold(b.prompt),
                    "turns": turns, "now": now})
    return out


def overview(run: Run, st: State) -> dict:
    cells = nodes(run, st)
    return {"width": WIDTH, "height": axis_y(run) + 60, "diagram": {"width": diagram_width(run), "height": 36 + len(ranks(run)) * 150 - 40},
            "nodes": cells, "edges": edges(run, st, cells), "axis": axis(run, st),
            "jumps": jumps(run, st), "sentences": sentences(st, run.start), "design": st.design, "outcome": st.outcome,
            "wakings": wakings(run, st),
            "legend": [(t, COLOURS[t]) for t in ("assignment", "report", "status", "query", "answer", "proposal", "escalation")]
            + [("dialogue", COLOURS["dialogue"]), ("design version", COLOURS["design"]), ("refused", COLOURS["refused"])],
            "act_legend": [(w, ACT_COLOURS[f]) for w, f in ACT_WORDS]}
