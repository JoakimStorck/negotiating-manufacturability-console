"""The overview of a run at a time, as geometry for the page to draw: the roles' cells in their ranks, each a being-box holding what
the cell has at the clock's time, with the decision maker over it as a mark joined to the box; the traffic between them, what is
awake and what waits, and the time axis with every event marked and the clock's position on it.

The beings exist whether or not a decision maker stands over them (ARTI): a cell shows what it holds, "none yet" where it holds
nothing, and the mark above it who decides over it, dimmed where nobody does. The same drawing serves the frame's empty state,
from its presence alone (`empty_cells`), and a run at any time in it (`cells`).

Nothing here reads a file; it takes a `runs.Run` and a `runs.State` and returns plain dicts and lists the template turns into SVG.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta

import re

from .diff import mandate_text, value_text
from .runs import DIALOGUE, RANK, ROLES, TITLES, Event, Run, State

WIDTH = 1200
AXIS_X0, AXIS_X1 = 150, 1130
LANE_H = 24                      # a role's activity line, parallel to the time axis above it
# thinking has one colour on every line, apart from the calls' colours; the calls are what the model chose, the thinking is the model
ACT_COLOURS = {"think": "#b9a7e2", "read": "#b9c7d6", "analyse": "#7aa7d9", "make": "#f2b05e", "other": "#c9c9c9"}
ACT_WORDS = (("thinking", "think"), ("reading", "read"), ("analysing", "analyse"), ("reshaping, planning", "make"))
COLOURS = {"assignment": "#2a78d6", "proposal": "#eb6834", "query": "#1baf7a", "answer": "#eda100", "report": "#e87ba4",
           "escalation": "#008300", "status": "#6250d6", "dialogue": "#52514e", "design": "#0b0b0b", "refused": "#e34948",
           "woke": "#b9c2cc", "slept": "#b9c2cc", "plan": "#8a8f94"}
FILLS = {"awake": "#dce8f7", "waiting": "#fff1c7", "idle": "#f3f5f7", "absent": "#ffffff", "none": "#ffffff", "down": "#fdeceb"}
STROKES = {"awake": "#1f5fa8", "waiting": "#b7791f", "idle": "#8a94a0", "absent": "#c5ccd3", "none": "#a0a8b0", "down": "#b3261e"}
# a cell: the being-box with its lines, and above it the decision maker's mark, a rounded badge joined to the box by a short line
CELL_W, CELL_GAP, LINE_H, CELL_PAD, SIDE = 240, 40, 15, 30, 90
MARK_W, MARK_H, MARK_RISE = 150, 34, 46
CELL_LINES = 7                                   # a cell's lines at most; the rest in its tooltip


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


def lanes_top(run: Run) -> float:
    """The activity lines start at the top of the time picture, with room above them for the clock and "next in"."""
    return 36


def axis_y(run: Run) -> float:
    """The time axis sits below the activity lines, one per role, with room for the marks that stand on it."""
    return lanes_top(run) + len(run.roles) * LANE_H + 40


def _maker_text(maker: str | None) -> str:
    """A decision maker in words, from the word the run readers give (`_short`)."""
    return {"operator": "a person", "none": "none", "scripted": "the scripted policy", "reference": "scripted (reference)"}.get(maker, maker) \
        if maker else "not known"


def _maker_word(maker: dict | None) -> str | None:
    """A presence-1 decision maker as the word the run readers give."""
    if not maker:
        return None
    if maker.get("kind") == "model":
        return maker.get("name")
    if maker.get("kind") == "scripted" and maker.get("name") not in (None, "scripted"):
        return maker["name"]
    return maker.get("kind")


def _metric_lines(order: dict) -> list[str]:
    """The order's metrics with their values and mandates, those with a mandate first, alike ones joined (M6–M9)."""
    rows = []
    for m in order.get("metrics") or []:
        if m.get("dropped"):
            continue
        mandate = m.get("mandate") or {"form": "held"}
        rows.append((m["id"], f"{(m.get('quantity') or '').replace('_', ' ')} {value_text(m.get('value'), m.get('unit'))}",
                     mandate_text(mandate, m.get("unit")), mandate.get("form") != "held"))
    out, held = [], 0
    i = 0
    while i < len(rows):
        j = i
        while j + 1 < len(rows) and rows[j + 1][1:] == rows[i][1:]:
            j += 1
        ids = rows[i][0] if i == j else f"{rows[i][0]}–{rows[j][0]}"
        if rows[i][3]:
            out.append(f"{ids} {rows[i][1]} · {rows[i][2]}")
        else:
            held += j - i + 1
        i = j + 1
    return out + ([f"{held} metrics held"] if held else [])


def _orientation(plan_id: str | None) -> str | None:
    m = re.search(r"-([mp])([XYZ])@", plan_id or "")
    return f"{'-' if m.group(1) == 'm' else '+'}{m.group(2)}" if m else None


def _settings_text(settings: dict) -> str:
    def v(x):
        return x["value"] if isinstance(x, dict) else x
    parts = []
    if "layer_height" in settings:
        parts.append(f"{v(settings['layer_height']):g} mm layers")
    if "perimeters" in settings:
        parts.append(f"{v(settings['perimeters'])} perimeters")
    if "fill_density" in settings:
        parts.append(f"{v(settings['fill_density']):g} % fill")
    return ", ".join(parts)


def plan_at(run: Run, st: State) -> tuple[str | None, bool]:
    """The plan in force at the clock (the latest accepted), else the latest candidate made or analysed; and whether it is in force."""
    accepted = None
    for e in run.events:
        if e.time > st.at:
            break
        if e.kind == "message" and e.valid and e.type == "status" and e.text.startswith("accepted · "):
            accepted = e.text.split(" · ", 1)[1]
    if accepted:
        return accepted, True
    latest, when = None, None
    for b in run.bars:
        for a in b.acts:
            if a.word == "analysing" and a.detail.startswith("plan") and a.start <= st.at and (when is None or a.start >= when):
                latest, when = a.detail, a.start
    for pid, p in run.plans.items():
        if p["time"] <= st.at and (when is None or p["time"] >= when):
            latest, when = pid, p["time"]
    return latest, False


def _settings_of(run: Run, plan_id: str) -> tuple[str | None, dict]:
    """The orientation and settings a plan was made with: the latest plan_candidate call ended before the plan was first analysed."""
    first = run.plans.get(plan_id, {}).get("time")
    if first is None:
        first = min((a.start for b in run.bars for a in b.acts if a.word == "analysing" and a.detail == plan_id), default=None)
    if first is None:
        return _orientation(plan_id), {}
    made = [m for m in run.made if m["tool"] == "plan_candidate" and m["end"] <= first + timedelta(seconds=0.01)]
    if not made:
        return _orientation(plan_id), {}
    inputs = made[-1]["inputs"]
    return inputs.get("orientation") or _orientation(plan_id), dict(inputs.get("settings") or {})


def beings(role: str, run: Run | None, st: State | None, ctx: dict) -> tuple[list[dict], str | None]:
    """What a role's cell holds at the clock, as lines ({text, kind}), and the design version whose picture it shows."""
    def line(text, kind=""):
        return {"text": text, "kind": kind}
    order, presence = ctx.get("order"), ctx.get("presence")
    at = st.at if st is not None else None
    out, picture = [], None
    if role == "requester":
        if run is not None and run.order:
            name = ((order or {}).get("product") or {}).get("name") or (order or {}).get("title")
            out.append(line(f"order {run.order[0]}@{run.order[1]}" + (f": {name}" if name else ""), "head"))
            out += [line(t) for t in _metric_lines(order)] if order else [line("its metrics: the order is not read", "muted")]
        elif run is not None:
            out.append(line("a scenario's brief, no order", "muted"))
        else:
            words = {"placed": "placed, waiting for the frame", "preparing": "being prepared", "parked": "parked: the owner's word is awaited"}
            held = [r for r in (presence or {}).get("runs", []) if r.get("order") and r["state"] in words]
            out += [line(f"order {r['order']['lineage']}@{r['order']['revision']} {words[r['state']]}", "bad" if r["state"] == "parked" else "head")
                    for r in held] or [line("order: none yet", "muted")]
        if run is not None and run.parked and at >= run.parked["time"]:
            out.append(line(f"waits for the owner's word: a {run.parked['what']}" + (f" on {', '.join(run.parked['metrics'])}" if run.parked["metrics"] else ""), "bad"))
        elif st is not None and st.waiting.get("requester"):
            out.append(line(f"waits: {st.waiting['requester']}", "bad"))
    elif role == "design_engineer":
        design = st.design if st is not None else None
        if design:
            picture = design
            bound = (order or {}).get("design")
            n = (ctx.get("features") or {}).get(design)
            out.append(line(f"{design}" + (f", {n} features" if n is not None else ""), "head"))
            made = [m for m in run.made if m["tool"] == "reshape" and m["end"] <= at and m["start"] >= (run.start or m["start"])]
            means: dict[str, int] = {}
            for m in made:
                means[m["inputs"].get("means") or "shape"] = means.get(m["inputs"].get("means") or "shape", 0) + 1
            versions = sum(1 for t, d in run.designs if run.start and run.start <= t <= at)
            if versions:
                out.append(line(f"{versions} version{'s' if versions > 1 else ''} made in the run"
                                + (f" ({', '.join(f'{k} {v}' for k, v in sorted(means.items()))})" if means else "")))
            if bound:
                out.append(line(f"bound version {bound}" if bound != design else "the order's bound version", "muted"))
        else:
            out.append(line("design version: none yet", "muted"))
    elif role == "process_planner":
        plan, in_force = plan_at(run, st) if run is not None else (None, False)
        if plan:
            orientation, settings = _settings_of(run, plan)
            out.append(line(f"{'plan in force' if in_force else 'latest candidate'}: {plan}", "head"))
            text = ", ".join(x for x in (orientation, _settings_text(settings)) if x)
            if text:
                out.append(line(text))
            p = run.plans.get(plan)
            if p:
                out.append(line(f"verdict {p['verdict'].replace('_', ' ')}", "bad" if p["verdict"] != "ok" else ""))
                for f in p["findings"][:3]:
                    out.append(line(f"{f.get('metric') or f['requirement']}{' at ' + f['feature'] if f.get('feature') else ''} {f['status'].replace('_', ' ')}", "bad"))
        else:
            out.append(line("plan: none yet", "muted"))
    elif role == "production_planner":
        latest: dict[str, tuple] = {}
        for t, jid, machine, status in (run.jobs if run is not None else []):
            if t <= at:
                latest[jid] = (machine, status)
        live = [(j, m, s) for j, (m, s) in latest.items() if s in ("queued", "running", "paused")]
        out += [line(f"{j} on {m}, {s}") for j, m, s in live] or [line("jobs: none yet" if not latest else f"{len(latest)} jobs done, none queued", "muted")]
    elif role == "machine_operator":
        machines = [p for p in (presence or {}).get("parts", []) if p["kind"] == "machine"]
        if machines:
            from .frame import part_state
            for m in machines:
                state = part_state(m, presence)
                out.append(line(f"{m['id']}: {m['machine']['adapter']}, {state}" + (f", {m['machine']['job']}" if m["machine"].get("job") else ""),
                                "bad" if state in ("down", "unavailable") else ""))
        else:
            known = sorted({m for _, _, m, _ in (run.jobs if run is not None else [])})
            out += [line(f"{m}") for m in known] or [line("machines: not known here", "muted")]
    elif role == "quality_engineer":
        out.append(line("measurements: none yet", "muted"))
    elif role == "maintenance_technician":
        out.append(line("capability entries: none yet", "muted"))
    return out, picture


def _mark(role: str, run: Run | None, st: State | None, ctx: dict) -> dict:
    """The decision maker over a cell: who, and its state at the clock (awake with what it does, waiting, not woken, left, down)."""
    presence = ctx.get("presence")
    part = next((p for p in (presence or {}).get("parts", []) if p["id"] == role), None)
    maker = (run.decision_makers.get(role) if run is not None else None) or _maker_word((part or {}).get("role", {}).get("maker"))
    state = None
    if part is not None and st is None:
        from .frame import part_state
        state = part_state(part, presence)
    if maker == "none" or (maker is None and part is not None):
        mode = "none"
        doing = "nobody decides here"
    elif st is not None and role in st.awake:
        mode, doing = "awake", _doing(st.activity.get(role))
    elif st is not None and role in st.waiting:
        mode, doing = "waiting", st.waiting[role]
    elif state in ("left", "down", "unavailable"):
        mode, doing = "down", state
    elif run is not None and role in run.decision_makers:
        mode, doing = "idle", "asleep"
    elif run is not None:
        mode, doing = "absent", "not woken in this run"
    else:
        r = (part or {}).get("role") or {}
        mode = "awake" if r.get("awake") else "waiting" if r.get("waits") else "idle"
        doing = "at work" if r.get("awake") else f"a {r['waits'][0]['what']} waits" if r.get("waits") else "waiting for work"
    return {"who": _maker_text(maker) if mode != "none" else "none", "doing": doing, "mode": mode, "dimmed": mode == "none",
            "fill": FILLS[mode], "stroke": STROKES[mode]}


def _place(cells: list[dict]) -> dict:
    """The cells placed in their ranks, top down, the marks above the boxes; the diagram's size."""
    by_rank: dict[int, list[dict]] = {}
    for c in cells:
        by_rank.setdefault(RANK.get(c["role"], 3), []).append(c)
    widest = max((len(v) for v in by_rank.values()), default=1)
    width = widest * CELL_W + (widest - 1) * CELL_GAP + 2 * SIDE
    y = 20
    for rank in sorted(by_rank):
        row = by_rank[rank]
        h = max(CELL_PAD + LINE_H * len(c["lines"]) + (70 if c["picture"] else 0) for c in row)
        total = len(row) * CELL_W + (len(row) - 1) * CELL_GAP
        x0 = (width - total) / 2
        for i, c in enumerate(row):
            c.update(x=x0 + i * (CELL_W + CELL_GAP), y=y + MARK_RISE, w=CELL_W, h=h)
            c["mark"].update(x=c["x"] + CELL_W - MARK_W - 6, y=y, w=MARK_W, h=MARK_H)
        y += MARK_RISE + h + 40
    return {"width": width, "height": y}


def _cell(role: str, run: Run | None, st: State | None, ctx: dict) -> dict:
    lines, picture = beings(role, run, st, ctx)
    mark = _mark(role, run, st, ctx)
    if mark["mode"] == "none":
        lines.append({"text": "the frame stops here when a decision is needed", "kind": "muted"})
    shown = lines[:CELL_LINES] if len(lines) <= CELL_LINES else lines[:CELL_LINES - 1] + [{"text": f"and {len(lines) - CELL_LINES + 1} more", "kind": "muted"}]
    return {"role": role, "title": TITLES.get(role, role), "lines": shown, "all": "\n".join(l["text"] for l in lines), "picture": picture,
            "mark": mark, "mode": mark["mode"], "maker": mark["who"], "note": mark["doing"] if mark["mode"] in ("awake", "waiting") else ""}


def cells(run: Run, st: State, ctx: dict | None = None) -> tuple[list[dict], dict]:
    """Every role's cell at the clock's time, placed; and the diagram's size."""
    out = [_cell(role, run, st, ctx or {}) for role in ROLES]
    return out, _place(out)


def empty_cells(presence: dict, ctx: dict | None = None) -> tuple[list[dict], dict]:
    """Every role's cell in the frame's empty state, from its presence alone."""
    ctx = {**(ctx or {}), "presence": presence}
    out = [_cell(role, None, None, ctx) for role in ROLES]
    return out, _place(out)


def _doing(act) -> str:
    """What an awake role does, for its cell: the act's word, else just awake."""
    if act is None:
        return "awake"
    if act.detail and act.word in ("reshaping the design", "planning"):
        return f"{act.word.split()[0]} {act.detail}"     # short enough for the cell: "reshaping bracket-mass@v11"
    return act.word


def _anchor(a: dict, b: dict) -> tuple[float, float]:
    """Where an arrow leaves box a towards box b: the facing side, left of the mark that stands over a box's top."""
    if b["y"] > a["y"]:
        return a["x"] + a["w"] * 0.28, a["y"] + a["h"]
    if b["y"] < a["y"]:
        return a["x"] + a["w"] * 0.28, a["y"]
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
    if dx:
        # between ranks the marks stand to the right of the lines: both directions' words go to the left, one above the other
        return {"x1": x1 + dx, "y1": y1, "x2": x2 + dx, "y2": y2, "words": words, "bold": bold, "stroke": stroke,
                "label_x": min(x1, x2) - 24, "label_y": (y1 + y2) / 2 + (-4 if dx < 0 else 12), "anchor": "end"}
    return {"x1": x1 + dx, "y1": y1 + dy, "x2": x2 + dx, "y2": y2 + dy, "words": words, "bold": bold, "stroke": stroke,
            "label_x": (x1 + x2) / 2, "label_y": (y1 + y2) / 2 + dy + (-6 if dy < 0 else 14 if dy > 0 else 4), "anchor": "middle"}


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


def overview(run: Run, st: State, ctx: dict | None = None) -> dict:
    """The run at the clock's time, for the page: `ctx` gives what the run's events do not hold (the order's document, the frame's
    presence for the machines and the decision makers, the feature counts known)."""
    placed, size = cells(run, st, ctx)
    return {"width": WIDTH, "height": axis_y(run) + 60, "diagram": size,
            "nodes": placed, "edges": edges(run, st, placed), "axis": axis(run, st),
            "jumps": jumps(run, st), "sentences": sentences(st, run.start), "design": st.design, "outcome": st.outcome,
            "wakings": wakings(run, st),
            "legend": [(t, COLOURS[t]) for t in ("assignment", "report", "status", "query", "answer", "proposal", "escalation")]
            + [("dialogue", COLOURS["dialogue"]), ("design version", COLOURS["design"]), ("refused", COLOURS["refused"])],
            "act_legend": [(w, ACT_COLOURS[f]) for w, f in ACT_WORDS]}


OUTCOME_WORDS = {"accepted": "Accepted: a plan for manufacturing", "declined": "Declined by the requester",
                 "parked": "Parked: the owner's word is awaited", "referred": "Referred: the case stalled",
                 "stopped": "Stopped: a decision was needed and nobody decides", "error": "Ended by an error",
                 "closed": "Closed", "waiting": "Waiting"}


def relaxation_text(q: dict, showings: dict | None = None) -> str:
    """A requirement as finally stated, relaxed in the run, in words: what, from, to, by whom, on which showing."""
    r = q["relaxed"]
    name = q.get("metric") or q["requirement"]
    who = {"owner": "the order's owner"}.get(r["by"]["actor"]) or \
        f"the {TITLES.get(r['by']['role'], r['by']['role']).lower()}" + (", a person" if r["by"]["actor"] == "operator" else "")
    within = {True: ", within its mandate", False: ", beyond its mandate"}.get(r.get("within_mandate"), "")
    showing = (showings or {}).get(r["showing"]) or r["showing"]
    head = f"the margin on {name}" if r["what"] == "margin" else name
    return f"{head} relaxed from {_value(r['from'])} to {_value(r['to'])} by {who}{within}" + (f", on the showing of {showing}" if showing else "")


def result_card(outcome: str | None, reason: str | None, result: dict | None, run: Run | None = None) -> dict:
    """What the page's result card shows: the outcome's words, the result as served, each relaxation in words."""
    word = (result or {}).get("outcome") or outcome or "ended"
    showings = {}
    if run is not None:
        showings = {e.ref: e.text or e.ref for e in run.events if e.kind == "dialogue" and e.type == "showing" and e.ref}
    relaxations = [relaxation_text(q, showings) for q in (result or {}).get("requirements") or [] if q.get("relaxed")]
    return {"outcome": word, "words": OUTCOME_WORDS.get(word, word), "reason": reason, "result": result, "relaxations": relaxations}


def plan_figures(result: dict | None) -> str:
    """An accepted run's plan in one line for the catalogue: its time, material and mass."""
    p = (result or {}).get("plan")
    if not p:
        return ""
    return f"{p['print_time_s'] / 60:.0f} min, {p['material_g']:.1f} g material" + (f", {p['mass_g']:.2f} g" if p.get("mass_g") is not None else "")
