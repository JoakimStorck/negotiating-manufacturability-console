"""The standing frame as the tool reads it: one client over HTTP, the same locally and across machines.

    frame = Frame("http://127.0.0.1:8780", token=read_token("~/.config/am-order/frame-token"))
    frame.presence()          # presence-1: the frame, its roles with their decision makers, the machines, its runs
    frame.runs()              # runs-1: the catalogue
    frame.events(run, after)  # events-1: a run as it stands and its events after a sequence number
    frame.place(document)     # an order-1 version placed; the frame makes the run

The frame is am-llm's (its design document 2.6); the contracts are this package's schemas, and every document the frame answers
with is validated against its schema as it arrives. What can go wrong is one of four things, each `FrameError` with its `kind`:
the frame refuses the token (`unauthorized`, in the frame's own words, which name the tokens file it reads and never a value);
the frame does not answer, or answers late (`unreachable`); the frame answers with a document its schema refuses (`refused`,
the frame's fault, with the validator's reasons); or the frame answers a request with an error of its own (`answer`: 404, 409,
422, in the frame's words). The token is read from a file's one `NAME=TOKEN` line or from `AM_FRAME_TOKEN`, sent as a bearer
token, and never logged, shown or stored anywhere else.

Times are the frame's: `at` in every document is the frame's clock when it served it, and `down` is inferred from a part's
latest sign of life older than `down_after` before `at`, never from the tool's clock.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

import httpx

from .schema import SchemaError, validate_events, validate_features, validate_presence, validate_runs

TIMEOUT = 5.0
TOKEN_ENV = "AM_FRAME_TOKEN"


def read_token(path: str | Path | None = None) -> str | None:
    """The token from a file (its one `NAME=TOKEN` line, or the token alone) or, without a file, from `AM_FRAME_TOKEN`."""
    if path:
        for line in Path(path).expanduser().read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                return line.partition("=")[2].strip() if "=" in line else line
        return None
    return os.environ.get(TOKEN_ENV) or None


def _time(s: str | None) -> datetime | None:
    if not s:
        return None
    t = datetime.fromisoformat(s.replace("Z", "+00:00"))
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


class FrameError(Exception):
    """What the frame did instead of answering: `unauthorized`, `unreachable`, `refused` (a document out of its schema's form),
    `answer` (an error the frame answered with); `status` the HTTP status where there was one, `reasons` the frame's or the
    validator's."""

    def __init__(self, kind: str, message: str, status: int | None = None, reasons: list[str] | None = None):
        self.kind, self.status, self.reasons = kind, status, list(reasons or [])
        super().__init__(message)


@dataclass
class Contact:
    """When the frame last answered and what went wrong since, for the page to say."""
    answered: datetime | None = None          # the tool's clock: when the frame last answered
    error: FrameError | None = None
    since: datetime | None = None             # the tool's clock: when the frame first failed in the current failing stretch
    skew: timedelta = field(default_factory=timedelta)   # the frame's clock less the tool's, from the last `at`

    def frame_now(self) -> datetime:
        """Now on the frame's clock."""
        return datetime.now(timezone.utc) + self.skew


class Frame:
    """A client of one standing frame. `client` may be given (an `httpx.Client`, as a test's client is) instead of the URL's own."""

    def __init__(self, url: str, token: str | None = None, timeout: float = TIMEOUT, client: httpx.Client | None = None):
        self.url = url.rstrip("/")
        self._token = token
        self.client = client or httpx.Client(base_url=self.url, timeout=timeout)
        self.contact = Contact()

    def __repr__(self) -> str:
        return f"Frame({self.url!r})"                     # never the token

    # ---------------------------------------------------------------- the requests

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._token}"} if self._token else {}

    def _request(self, method: str, path: str, **kw) -> httpx.Response:
        headers = {**self._headers(), **kw.pop("headers", {})}
        try:
            r = self.client.request(method, path, headers=headers, **kw)
        except httpx.TimeoutException as e:
            raise self._failed(FrameError("unreachable", f"the frame at {self.url} answered too late ({type(e).__name__})"))
        except httpx.HTTPError as e:
            raise self._failed(FrameError("unreachable", f"the frame at {self.url} does not answer ({type(e).__name__})"))
        if r.status_code == 401:
            raise self._failed(FrameError("unauthorized", f"the frame at {self.url} refuses the token: {self._said(r)}", 401))
        self.contact.answered, self.contact.error, self.contact.since = datetime.now(timezone.utc), None, None
        if r.status_code >= 400:
            body = self._body(r)
            raise FrameError("answer", self._said(r), r.status_code, body.get("reasons") if isinstance(body, dict) else None)
        return r

    def _failed(self, e: FrameError) -> FrameError:
        if self.contact.error is None:
            self.contact.since = datetime.now(timezone.utc)
        self.contact.error = e
        return e

    @staticmethod
    def _body(r: httpx.Response):
        try:
            return r.json()
        except ValueError:
            return None

    def _said(self, r: httpx.Response) -> str:
        body = self._body(r)
        if isinstance(body, dict) and body.get("error"):
            return str(body["error"])
        if isinstance(body, dict) and body.get("detail"):
            return str(body["detail"])
        return f"HTTP {r.status_code}"

    def _document(self, path: str, validate, what: str, **params) -> dict:
        r = self._request("GET", path, params=params or None)
        doc = self._body(r)
        try:
            validate(doc if isinstance(doc, dict) else {})
        except SchemaError as e:
            raise self._failed(FrameError("refused", f"the frame's {what} does not have the form of its schema", r.status_code, e.errors))
        if isinstance(doc, dict) and doc.get("at"):
            self.contact.skew = _time(doc["at"]) - datetime.now(timezone.utc)
        return doc

    @staticmethod
    def _run_path(run_id: str) -> str:
        return quote(run_id, safe="/@")

    # ---------------------------------------------------------------- the contracts

    def presence(self) -> dict:
        return self._document("/presence", validate_presence, "presence")

    def runs(self) -> dict:
        return self._document("/runs", validate_runs, "catalogue")

    def events(self, run_id: str, after: int = 0) -> dict:
        return self._document(f"/runs/{self._run_path(run_id)}/events", validate_events, f"events of {run_id}", after=after)

    def features(self, run_id: str, design: str) -> dict:
        return self._document(f"/runs/{self._run_path(run_id)}/features/{quote(design, safe='@')}", validate_features,
                              f"feature list of {design}")

    def file(self, run_id: str, design: str, name: str) -> tuple[bytes, str]:
        """A file beside an accepted version's feature list (`picture.png`, `model.stl`, `model.3mf`), or with `name` None a
        version's picture as the run drew it."""
        base = f"/runs/{self._run_path(run_id)}"
        path = f"{base}/designs/{quote(design, safe='@')}/picture.png" if name is None else f"{base}/features/{quote(design, safe='@')}/{name}"
        r = self._request("GET", path)
        return r.content, r.headers.get("content-type", "application/octet-stream")

    def place(self, document: bytes | dict) -> dict:
        """An order version placed: the frame's answer (201: the run, the order version, its state, where its events are)."""
        body = document if isinstance(document, bytes) else json.dumps(document).encode("utf-8")
        r = self._request("POST", "/orders", content=body, headers={"Content-Type": "application/json"})
        return self._body(r) or {}

    def help_url(self) -> str:
        return self.url + "/"


# -------------------------------------------------------------------- reading presence

def saved_version(home, lineage: str, revision: int | None = None) -> tuple[str, bytes] | None:
    """A product's saved version (the latest, or a revision) as the home holds it: its hash, the name of its file, and the file's
    bytes, which are what is placed. Found by its revision in the history, not by hashing `order.json`, whose bytes a checkout may
    have changed (line endings) while the version keeps its name."""
    history = home.history(lineage) if (home._folder(lineage) / "versions").exists() else []
    found = [v for v in history if revision is None or v["revision"] == revision]
    if not found:
        return None
    version = found[-1]["version"]
    return version, (home._folder(lineage) / "versions" / f"{version}.json").read_bytes()


def part_state(part: dict, presence: dict) -> str:
    """A part's state as the reader takes it: what it declares, or `down` when its latest sign of life is older than
    `down_after` before the frame's `at` (the frame's clock, both)."""
    if part["state"] == "left":
        return "left"
    at, seen = _time(presence["at"]), _time(part["seen"])
    if at - seen > timedelta(seconds=float(presence["down_after"])):
        return "down"
    return part["state"]


def maker_text(maker: dict | None) -> str:
    """A decision maker in words."""
    if not maker:
        return "no decision maker"
    kind, name = maker.get("kind"), maker.get("name")
    if kind == "model":
        return name or "a model"
    if kind == "scripted":
        return f"the scripted policy{f' ({name})' if name and name != 'scripted' else ''}"
    if kind == "operator":
        return f"a person{f' ({name})' if name else ''}"
    return "no decision maker"


# -------------------------------------------------------------------- what the tool has read

class Reading:
    """What the tool has read from one frame, kept so that a page shows the last of it when the frame does not answer, and so that
    nothing read is read again: a run's events are asked for after the last number read, and a run that is done not at all."""

    def __init__(self, frame: Frame):
        self.frame = frame
        self.presence: dict | None = None
        self.catalogue: dict | None = None
        self.runs: dict[str, dict] = {}            # run id -> {"run": the run as it stands, "events": [...], "last": n}
        self.features: dict[tuple[str, str], dict] = {}

    def read_presence(self) -> FrameError | None:
        try:
            self.presence = self.frame.presence()
        except FrameError as e:
            return e
        return None

    def read_catalogue(self) -> FrameError | None:
        try:
            self.catalogue = self.frame.runs()
        except FrameError as e:
            return e
        return None

    def read_run(self, run_id: str) -> tuple[dict | None, FrameError | None]:
        """The run's events as read so far, with the new ones appended; a run that is done is not asked for again."""
        kept = self.runs.get(run_id)
        if kept is not None and kept["run"]["status"] == "done":
            return kept, None
        try:
            doc = self.frame.events(run_id, kept["last"] if kept else 0)
        except FrameError as e:
            return kept, e
        if kept is None:
            kept = {"run": doc["run"], "events": list(doc["events"]), "last": doc["last"]}
        else:
            kept["run"] = doc["run"]
            kept["events"] += [e for e in doc["events"] if e["seq"] > kept["last"]]
            kept["last"] = max(kept["last"], doc["last"])
        self.runs[run_id] = kept
        return kept, None

    def read_features(self, run_id: str, design: str) -> tuple[dict | None, FrameError | None]:
        key = (run_id, design)
        if key in self.features:
            return self.features[key], None
        try:
            self.features[key] = self.frame.features(run_id, design)
        except FrameError as e:
            return None, e
        return self.features[key], None

    def runs_of(self, lineage: str) -> list[dict]:
        """The frame's runs of a product's orders, from the catalogue and, for an order placed and not yet a run, presence; each
        {id, revision, sha256, status, outcome, reason, started}."""
        out, seen = [], set()
        for r in (self.catalogue or {}).get("runs", []):
            o = r.get("order") or {}
            if o.get("lineage") == lineage:
                seen.add(r["id"])
                out.append({"id": r["id"], "revision": o["revision"], "sha256": o["sha256"], "status": r["status"],
                            "outcome": r.get("outcome"), "reason": r.get("reason"), "started": r.get("started"), "run": True})
        for r in (self.presence or {}).get("runs", []):
            o = r.get("order") or {}
            if o.get("lineage") == lineage and r["id"] not in seen:
                out.append({"id": r["id"], "revision": o["revision"], "sha256": o["sha256"], "status": r["state"],
                            "outcome": r.get("outcome"), "reason": None, "started": r.get("since"), "run": False})
        return sorted(out, key=lambda x: x["revision"], reverse=True)
