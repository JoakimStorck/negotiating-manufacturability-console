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
AXIS_X0, AXIS_X1 = 70, 1130
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


def axis_y(run: Run) -> float:
    """The time axis sits below the last row of cells, however many rows there are."""
    return 36 + len(ranks(run)) * 150 + 70


def nodes(run: Run, st: State) -> list[dict]:
    """A cell per role: its place by rank, its decision maker, its state at the time."""
    by_rank: dict[int, list[str]] = {}
    for r in run.roles:
        by_rank.setdefault(RANK.get(r, 3), []).append(r)
    rows = {rank: 36 + i * 150 for i, rank in enumerate(ranks(run))}
    out = []
    for rank, roles in by_rank.items():
        n = len(roles)
        gap = 60
        total = n * BOX_W + (n - 1) * gap
        x0 = (WIDTH - total) / 2
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
                        "note": st.waiting.get(role) or ("awake" if mode == "awake" else "")})
    return out


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
        nxt = {"in": _span(st.next.time - st.at), "what": st.next.type, "at": st.next.time.isoformat()}
    return {"marks": marks, "ticks": ticks, "head": x_of(st.at), "start": start.strftime("%Y-%m-%d %H:%M:%SZ"),
            "end": end.strftime("%H:%M:%SZ"), "clock": _clock(st.at, start), "next": nxt, "live": run.live,
            "x0": AXIS_X0, "x1": AXIS_X1, "y": y, "seconds": (st.at - start).total_seconds(), "span": span}


def _tick_step(span: float) -> float:
    for step in (10, 30, 60, 120, 300, 600, 900, 1800, 3600, 7200, 14400, 43200, 86400):
        if span / step <= 12:
            return step
    return 86400 * max(1, int(span / 86400 / 12))


def jumps(run: Run, st: State) -> dict:
    """Where the page can go from here: the previous and next event, the next decision, the start, the end; as seconds."""
    start = run.start
    if start is None:
        return {}

    def s(t: datetime) -> str:
        return f"{(t - start).total_seconds():.3f}"

    before = [e for e in run.events if e.time < st.at]
    after = [e for e in run.events if e.time > st.at]
    decisions_after = [e for e in after if e.decision]
    return {"start": "0", "end": s(run.end) if run.end else None,
            "previous": s(before[-1].time) if before else None, "next": s(after[0].time) if after else None,
            "next_decision": s(decisions_after[0].time) if decisions_after else None,
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
        out.append({"clock": _clock(e.time, start), "head": head, "text": e.text if e.kind != "woke" and e.kind != "slept" else "",
                    "colour": colour(e), "decision": e.decision, "valid": e.valid})
    return out


def overview(run: Run, st: State) -> dict:
    cells = nodes(run, st)
    return {"width": WIDTH, "height": axis_y(run) + 60, "nodes": cells, "edges": edges(run, st, cells), "axis": axis(run, st),
            "jumps": jumps(run, st), "sentences": sentences(st, run.start), "design": st.design, "outcome": st.outcome,
            "legend": [(t, COLOURS[t]) for t in ("assignment", "report", "status", "query", "answer", "proposal", "escalation")]
            + [("dialogue", COLOURS["dialogue"]), ("design version", COLOURS["design"]), ("refused", COLOURS["refused"])]}
