"""The order's steps, as the order view shows them in one line, from stated to approved:

    Stated → Checked → Bound → Confirmed → Placed → Being prepared → Your word → Accepted → Approved

Each step is read from the products home (the order's facets: a draft, a saved version, its design and bindings) and from the
frame (the catalogue, presence, the run's result), never stored. The step reached names the next thing to do as one action, and
every step done links to where it was done. `steps` is the one reading; the order view, the header's badge and the command line
take it.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .home import Home
from .order import Order

STEPS = (("stated", "Stated"), ("checked", "Checked"), ("bound", "Bound"), ("confirmed", "Confirmed"), ("placed", "Placed"),
         ("preparing", "Being prepared"), ("word", "Your word"), ("accepted", "Accepted"), ("approved", "Approved"))
LABELS = dict(STEPS)
OUTCOMES = {"declined": "Declined by the requester", "referred": "Referred: the case stalled",
            "stopped": "Stopped: a decision was needed and nobody decides", "error": "Ended by an error"}


@dataclass
class Next:
    """The next thing to do as one action: a link (`href`), or a form posted (`post`, confirmed first where `confirm` is given)."""
    text: str
    href: str | None = None
    post: str | None = None
    confirm: str | None = None


@dataclass
class Steps:
    reached: str                                   # the key of the step reached
    revision: int | None                           # the latest saved revision, None before the first save
    next: Next | None
    links: dict[str, str] = field(default_factory=dict)   # step key -> where it was done
    run: dict | None = None                        # the run of the latest version at the frame, as `Reading.runs_of` gives it
    ended: str | None = None                       # a run that ended without a plan: its outcome in words, with its reason
    note: str | None = None                        # what else the line says

    @property
    def label(self) -> str:
        return LABELS[self.reached]

    def line(self) -> list[dict]:
        """The steps in order, each with whether it is done, reached, and where it was done."""
        keys = [k for k, _ in STEPS]
        at = keys.index(self.reached)
        return [{"key": k, "label": label, "done": i < at, "reached": i == at, "href": self.links.get(k) if i <= at else None}
                for i, (k, label) in enumerate(STEPS)]


def unconfirmed(order: Order) -> int:
    """The bindings to the order's design not yet confirmed."""
    design = order.type.get("design")
    return sum(not f["confirmed"] for b in order.type.get("bindings", []) if b["design"] == design for f in b["features"])


def _page(lineage: str, item: str) -> str:
    """Where a refusal's item is fixed."""
    base = f"/products/{lineage}"
    if item.startswith("M") and item[1:].isdigit():
        return f"{base}/metrics/{item}"
    if item.startswith("O") and item[1:].isdigit():
        return f"{base}/objects"
    if item == "order":
        return f"{base}/order#the-order"
    return base


def _hhmm(t: str | None) -> str:
    return f"{t[11:16]}Z" if t else ""


def steps(home: Home, lineage: str, refusals: list, reading=None) -> Steps:
    """The order's steps as the home and, where the tool is connected, the frame hold them. `refusals` are the checks' on what
    is edited (the draft, or the order as it stands); `reading` is the frame's `Reading`, read already."""
    base = f"/products/{lineage}"
    folder = home._folder(lineage)
    history = home.history(lineage) if (folder / "versions").exists() else []
    latest = history[-1] if history else None
    revision = latest["revision"] if latest else None
    links = {"stated": base}
    draft = (folder / "draft.json").exists()
    if latest is None or draft:
        then = (revision or 0) + 1
        if refusals:
            n = len(refusals)
            nxt = Next(f"Fix {n} refusal{'s' if n != 1 else ''}", href=_page(lineage, refusals[0].item))
        else:
            nxt = Next(f"Save revision {then}", post=f"{base}/order/save")
        note = f"The draft changes revision {revision}; saved, it is revision {then}, placed anew." if latest else None
        return Steps("stated", revision, nxt, links, note=note)
    order = home.load(lineage)
    links["checked"] = f"{base}/history"
    design = order.type.get("design")
    if not design:
        return Steps("checked", revision, Next("Bind to a design", href=f"{base}/binding"), links)
    links["bound"] = f"{base}/binding"
    n = unconfirmed(order)
    bound = [f for b in order.type.get("bindings", []) if b["design"] == design for f in b["features"]]
    if not bound:
        return Steps("checked", revision, Next("Bind to a design", href=f"{base}/binding"), links)
    if n:
        return Steps("bound", revision, Next(f"Confirm {n} binding{'s' if n != 1 else ''}", href=f"{base}/binding"), links)
    links["confirmed"] = f"{base}/binding"
    if order.accepted():
        a = order.accepted()
        links.update(placed=f"{base}/order#runs", preparing=f"/frame/runs/{a['run']}", word=f"/frame/runs/{a['run']}",
                     accepted=f"/frame/runs/{a['run']}", approved=f"{base}/order#approved")
        return Steps("approved", revision, None, links,
                     note=f"Approved for manufacturing: {a['plan']} for {a['design']}, accepted in {a['run']}.")
    if order.form == 1:
        return Steps("confirmed", revision, Next(f"Save revision {revision + 1}", post=f"{base}/order/save"), links,
                     note=f"Revision {revision} is saved as order 1; saved again it is order 2, which is what is placed.")
    if reading is None:
        return Steps("confirmed", revision, None, links, note="The tool is not connected to a frame: start it with --frame URL --token-file FILE to place the order.")
    runs = reading.runs_of(lineage)
    run = next((r for r in runs if r["sha256"] == latest["version"] or r["revision"] == revision), None)
    if run is None:
        place = Next(f"Place revision {revision}", post=f"{base}/order/place")
        if runs:
            place.text = f"Changed since it was placed: place revision {revision}"
        return Steps("confirmed", revision, place, links)
    href = f"/frame/runs/{run['id']}"
    links.update(placed=f"{base}/order#runs", preparing=href)
    if not run["run"] or run["status"] == "placed":
        return Steps("placed", revision, Next("Follow the run", href=href), links, run=run)
    if run["status"] in ("running", "preparing"):
        return Steps("preparing", revision, Next("Follow the run", href=href), links, run=run)
    if run["status"] == "parked":
        waits = (run.get("result") or {}).get("waits") or {}
        since = _hhmm(waits.get("since") or run.get("started"))
        what = waits.get("what") or "showing"
        links["word"] = f"{base}/order#word"
        return Steps("word", revision, Next(f"Give your word: a {what} waits since {since}", href=f"{base}/order#word"), links, run=run)
    outcome = run.get("outcome") or (run.get("result") or {}).get("outcome")
    if outcome == "accepted":
        links.update(word=href, accepted=href)
        return Steps("accepted", revision, Next("Approve for manufacturing", post=f"{base}/order/approve",
                                                confirm=f"Approve {lineage}@{revision} for manufacturing, bound to the plan the run "
                                                        f"{run['id']} accepted? A new revision records the plan, the design version "
                                                        "and the requirements in force."), links, run=run)
    reason = run.get("reason") or (run.get("result") or {}).get("reason")
    words = OUTCOMES.get(outcome, f"Ended {outcome or run['status']}")
    return Steps("preparing", revision, Next("Change the order and place it again", href=f"{base}/order#the-order"), links, run=run,
                 ended=words + (f": {reason}" if reason else ""))
