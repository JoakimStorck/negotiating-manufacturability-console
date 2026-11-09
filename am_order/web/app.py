"""The web app: the person's interface to the products home, rendered on the server with htmx; served on 127.0.0.1, or with
`--host` on the network, without a login.

    am-order [--frame URL --token-file FILE] serve [--home DIR] [--host 127.0.0.1] [--port 8770] [--log DIR] [--runs DIR] [--allow-own]

Every page is a URL of its own. An edit goes to the product's draft and the page comes back with the checks' refusals beside what
they concern; Save makes a version when no check fails, and a refused save keeps the draft. With `--log DIR` every action is one
JSON line in `DIR/<session>.jsonl` (time, session, page, action, the refusals shown), the session an id drawn at the start.

With `--frame URL` the runs pages read a standing frame of am-llm besides the folders: its presence (the overview's empty state),
its catalogue and a run's events, through one client (`am_order.frame`); an order version is placed there from the order's
page. A frame that does not answer is a state of the page, which keeps what it last read.
"""
from __future__ import annotations

import json
import math
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .. import vocab as V
from ..bind import bind as bind_order, confirm, proposals, reject
from ..check import RULES, check
from ..diff import diff, level_text, mandate_text, value_text
from ..export import export
from ..home import Home, HomeError, ReadOnly, Refused
from ..order import ANSWERING, CHANGE, Order
from ..render import TABLES, TITLES, metric_name, table
from .. import runs as R
from ..picture import empty_cells, overview, plan_figures, result_card
from ..frame import Frame, FrameError, Reading, maker_text, part_state, saved_version

HERE = Path(__file__).parent


class Log:
    """One JSON line per action: time, session, page, action, the refusals shown."""

    def __init__(self, folder: Path | None):
        self.session = uuid.uuid4().hex[:12]
        self.path = Path(folder) / f"{self.session}.jsonl" if folder else None
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, page: str, action: str, refusals: list | None = None, detail: dict | None = None) -> None:
        if not self.path:
            return
        entry = {"time": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"), "session": self.session,
                 "page": page, "action": action, "refusals": [r.to_dict() if hasattr(r, "to_dict") else r for r in (refusals or [])]}
        if detail:
            entry["detail"] = detail
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


# -------------------------------------------------------------------- parsing the forms

def _num(text):
    if text is None or str(text).strip() == "":
        return None
    try:
        v = float(str(text).replace(",", ".") if str(text).count(",") == 1 and "." not in str(text) and " " not in str(text) else text)
    except ValueError:
        return None
    return int(v) if v.is_integer() else v if math.isfinite(v) else None


def _vec(text):
    if text is None or str(text).strip() == "":
        return None
    parts = [p for p in str(text).replace(";", ",").replace(",", " ").split() if p]
    vals = [_num(p) for p in parts]
    return vals if len(vals) == 3 and all(v is not None for v in vals) else None


def parse_place(text: str):
    """Places in lines: `box x0 y0 z0 x1 y1 z1` or `cylinder px py pz dx dy dz radius length` (mm)."""
    out = []
    for line in (text or "").splitlines():
        parts = line.replace(",", " ").split()
        if not parts:
            continue
        nums = [_num(p) for p in parts[1:]]
        if parts[0] == "box" and len(nums) == 6 and None not in nums:
            out.append({"box": {"min": nums[:3], "max": nums[3:]}})
        elif parts[0] == "cylinder" and len(nums) == 8 and None not in nums and nums[6] > 0 and nums[7] > 0:
            out.append({"cylinder": {"point": nums[:3], "direction": nums[3:6], "radius": nums[6], "length": nums[7]}})
        else:
            raise ValueError(f"the place {line!r} is not `box x0 y0 z0 x1 y1 z1` or `cylinder px py pz dx dy dz radius length`")
    return None if not out else out[0] if len(out) == 1 else out


def place_text(place) -> str:
    if not place:
        return ""
    lines = []
    for r in place if isinstance(place, list) else [place]:
        if "box" in r:
            lines.append("box " + " ".join(f"{v:g}" for v in r["box"]["min"] + r["box"]["max"]))
        else:
            c = r["cylinder"]
            lines.append("cylinder " + " ".join(f"{v:g}" for v in c["point"] + c["direction"] + [c["radius"], c["length"]]))
    return "\n".join(lines)


def value_from_form(form) -> dict | None:
    comparator = form.get("comparator") or ""
    if comparator == "band":
        lo, hi, nom = _num(form.get("lower")), _num(form.get("upper")), _num(form.get("nominal"))
        if lo is None or hi is None:
            return None
        return {"band": {**({"nominal": nom} if nom is not None else {}), "lower": lo, "upper": hi}}
    raw = (form.get("value") or "").strip()
    if not comparator or raw == "":
        return None
    if comparator == "holds":
        return {"holds": raw}
    if comparator == "equals":
        n = _num(raw)
        return {"equals": n if n is not None else raw}
    v = _vec(raw) if comparator == "at_most" and len(raw.replace(",", " ").split()) == 3 else _num(raw)
    return {comparator: v} if v is not None else None


def mandate_from_form(form) -> dict:
    kind = form.get("mandate") or "held"
    if kind != "interval":
        return {"form": kind}
    raw = (form.get("far") or "").strip()
    if raw in ("as_needed", "as needed"):
        return {"form": "interval", "to": "as_needed"}
    parts = raw.replace(",", " ").split()
    if len(parts) == 2 and None not in (_num(p) for p in parts):
        return {"form": "interval", "to": {"lower": _num(parts[0]), "upper": _num(parts[1])}}
    if len(parts) == 3:
        v = _vec(raw)
        return {"form": "interval", "to": v} if v else {"form": "interval"}
    n = _num(raw)
    return {"form": "interval", "to": n} if n is not None else {"form": "interval"}


def sources_from_text(text: str) -> list[dict]:
    """Sources in lines `kind: reference` (kind one of requester, standard, project, reference)."""
    out = []
    for line in (text or "").splitlines():
        if not line.strip():
            continue
        kind, _, ref = line.partition(":")
        kind = kind.strip().lower()
        if kind not in V.SOURCES:
            raise ValueError(f"the source {line!r} starts with none of {', '.join(V.SOURCES)}")
        out.append({"kind": kind, **({"ref": ref.strip()} if ref.strip() else {})})
    return out


def sources_text(sources) -> str:
    return "\n".join(s["kind"] + (f": {s['ref']}" if s.get("ref") else "") for s in sources or [])


def picked(form, name: str) -> list[str]:
    """The ticked values of a group of checkboxes, empty ones left out."""
    return [v for v in form.getlist(name) if v]


# -------------------------------------------------------------------- the app

def create_app(home: Home, log_dir: Path | None = None, runs_root: Path | None = None, frame: Frame | None = None,
               refresh: float = 3.0) -> FastAPI:
    app = FastAPI(title="am-order", docs_url=None, redoc_url=None, openapi_url=None)
    templates = Jinja2Templates(directory=str(HERE / "templates"))
    templates.env.globals.update(value_text=value_text, mandate_text=mandate_text, level_text=level_text, heading_name=V.heading_name,
                                 place_text=place_text, sources_text=sources_text, TITLES=TITLES, ANSWERING=ANSWERING, CHANGE=CHANGE)
    app.mount("/static", StaticFiles(directory=str(HERE / "static")), name="static")
    log = Log(log_dir)
    app.state.home, app.state.log = home, log
    app.state.runs_root = Path(runs_root).resolve() if runs_root else None
    app.state.frame = Reading(frame) if frame else None
    templates.env.globals.update(maker_text=maker_text, refresh=refresh, plan_figures=plan_figures, result_card=result_card)

    def ending_of(run, st):
        """The run's end at the clock: once the clock has reached the end of a run that has ended or parked, what the result card
        shows; before that, nothing, so that playback shows the card when the clock reaches the end and not before."""
        if run.entry.status not in ("done", "parked") or run.end is None or st.at < run.end:
            return None
        return result_card(run.entry.outcome if run.entry.status == "done" else "parked", run.entry.reason, run.entry.result, run)

    def features_of(order: Order):
        return home.features(order.type["design"]) if order.type.get("design") else None

    def refusals_of(lineage: str, order: Order):
        previous = home.load(lineage) if home.folder(lineage) and (home._folder(lineage) / "order.json").exists() else None
        return check(order, features=features_of(order), previous=previous)

    def page(request: Request, template: str, lineage: str | None, action: str, message: str | None = None, status: int = 200,
             logged: dict | None = None, **ctx):
        """A page, its action logged with the refusals shown; `logged` adds to the log's detail (an act's capacity and section)."""
        message = message or request.query_params.get("message")
        order = ctx.get("order")
        refusals = refusals_of(lineage, order) if order is not None and lineage else []
        by_item: dict[str, list] = {}
        for r in refusals:
            by_item.setdefault(r.item, []).append(r)
        facets = home.facets(lineage) if lineage and home.folder(lineage) else None
        writable = home.writable(lineage) if lineage and home.folder(lineage) else True
        detail = {**(logged or {}), **({"message": message} if message else {})}
        log.write(request.url.path, action, refusals, detail or None)
        return templates.TemplateResponse(request, template, {"home": home, "lineage": lineage, "refusals": refusals, "by_item": by_item,
                                                              "message": message, "facets": facets, "writable": writable, "V": V,
                                                              "session": log.session, **ctx}, status_code=status)

    def working(lineage: str) -> Order:
        if home.folder(lineage) is None:
            raise HTTPException(404, f"{lineage} is not in the products home")
        return home.working(lineage)

    def edit(request: Request, lineage: str, change, template: str, action: str, section: str = "type", **ctx):
        """Apply a change to the draft and show the page, or the reason the change is not made. An edit of a product is the
        orderer's act, logged with the capacity and the section it writes, the type's or this order's."""
        order = working(lineage)
        try:
            change(order)
            home.put_draft(lineage, order)
            message = None
            status = 200
        except ReadOnly as e:
            order, message, status = working(lineage), str(e), 403
        except (ValueError, KeyError) as e:
            order, message, status = working(lineage), str(e), 400
        return page(request, template, lineage, action, message, status, logged={"capacity": "orderer", "section": section},
                    order=order, **ctx)

    def migrated(lineage: str) -> Order | None:
        """The order as it stands, migrated, where it is saved as order 1: the page says so with the notes."""
        if home.folder(lineage) is None or not (home._folder(lineage) / "order.json").exists():
            return None
        stands = home.load(lineage)
        return Order.from_v1(stands.raw) if stands.form == 1 else None

    # ---------------------------------------------------------------- products

    @app.get("/", response_class=HTMLResponse)
    def products(request: Request, tag: str = "", state: str = "", find: str = "", material: str = "", design: str = "", selected: str = ""):
        facet = {k: v for k, v in (("material", material), ("design", design)) if v}
        rows = home.tree(tag or None, state or None, find or None, facet or None)
        groups = home.groups()
        tree = _tree(home, groups, rows)
        chosen = home.working(selected) if selected and home.folder(selected) else None
        return page(request, "products.html", None, "view", tree=tree, rows=rows, filters={"tag": tag, "state": state, "find": find,
                    "material": material, "design": design}, selected=selected, chosen=chosen,
                    chosen_facets=home.facets(selected) if chosen else None, tags=sorted({t for r in home.tree() for t in r["tags"]}),
                    group_paths=sorted(home.group_path(g) for g in groups), designs=home.designs(),
                    all_rows=home.tree(archived=True))

    @app.post("/products")
    async def create(request: Request):
        form = await request.form()
        lineage = (form.get("lineage") or "").strip()
        try:
            if form.get("from_design"):
                home.from_features(form["from_design"], lineage or None, form.get("group") or None)
                lineage = lineage or home.features(form["from_design"])["lineage"]
            else:
                home.create(lineage, form.get("name") or None, form.get("purpose") or "", form.get("group") or None)
        except HomeError as e:
            log.write("/products", "create", detail={"message": str(e)})
            return _back(request, "/", str(e))
        log.write("/products", "create", detail={"lineage": lineage})
        return RedirectResponse(f"/products/{lineage}", 303)

    @app.post("/products/{lineage}/derive")
    async def derive(request: Request, lineage: str):
        form = await request.form()
        try:
            new = home.derive(form.get("source") or lineage, form["lineage"].strip(), form.get("name") or None, form.get("group") or None)
        except (HomeError, KeyError) as e:
            log.write(f"/products/{lineage}/derive", "derive", detail={"message": str(e)})
            return _back(request, f"/?selected={lineage}", str(e))
        log.write(f"/products/{lineage}/derive", "derive", detail={"lineage": new.lineage})
        return RedirectResponse(f"/products/{new.lineage}", 303)

    @app.post("/products/{lineage}/manage")
    async def manage(request: Request, lineage: str):
        form = await request.form()
        action = form.get("action")
        try:
            if action == "move":
                home.move(lineage, form["group"])
            elif action == "tag":
                home.tag(lineage, add=[t.strip() for t in (form.get("add") or "").split(",") if t.strip()],
                         remove=[t.strip() for t in (form.get("remove") or "").split(",") if t.strip()])
            elif action == "archive":
                home.archive(lineage)
            else:
                raise HomeError(f"no action {action!r}")
        except Refused as e:
            log.write(f"/products/{lineage}/manage", action, e.refusals)
            return _back(request, f"/products/{lineage}", f"{action}: the save is refused; the draft is kept")
        except HomeError as e:
            log.write(f"/products/{lineage}/manage", action, detail={"message": str(e)})
            return _back(request, f"/?selected={lineage}", str(e))
        log.write(f"/products/{lineage}/manage", action)
        return RedirectResponse(f"/?selected={lineage}", 303)

    @app.post("/groups")
    async def groups(request: Request):
        form = await request.form()
        try:
            if form.get("action") == "rename":
                home.rename_group(form["group"], form["name"])
            elif form.get("action") == "move":
                home.move_group(form["group"], form.get("parent") or None)
            else:
                home.add_group(form["path"])
        except (HomeError, KeyError) as e:
            log.write("/groups", form.get("action") or "add", detail={"message": str(e)})
            return _back(request, "/", str(e))
        log.write("/groups", form.get("action") or "add")
        return RedirectResponse("/", 303)

    @app.get("/compare", response_class=HTMLResponse)
    def compare(request: Request, a: str = "", b: str = ""):
        changes, message, sides = [], None, None
        if a and b:
            try:
                changes = home.compare(a, b)
                sides = (home.load(a), home.load(b))
            except HomeError as e:
                message = str(e)
        return page(request, "compare.html", None, "view", message, a=a, b=b, changes=changes, sides=sides,
                    lineages=home.lineages())

    # ---------------------------------------------------------------- a product

    @app.get("/products/{lineage}", response_class=HTMLResponse)
    def product(request: Request, lineage: str):
        return page(request, "product.html", lineage, "view", order=working(lineage), migrated=migrated(lineage))

    @app.post("/products/{lineage}/product", response_class=HTMLResponse)
    async def product_edit(request: Request, lineage: str):
        form = await request.form()

        def change(o: Order):
            o.data["title"] = form.get("title") or o.data.get("title")
            o.type["product"]["name"] = form.get("name") or o.type["product"]["name"]
            o.type["product"]["purpose"] = form.get("purpose") or ""
        return edit(request, lineage, change, "product.html", "edit product", migrated=migrated(lineage))

    @app.post("/products/{lineage}/order", response_class=HTMLResponse)
    async def order_edit(request: Request, lineage: str):
        """This order's section: the brief (text, objective, quantity) and the answering policy."""
        form = await request.form()

        def change(o: Order):
            b = o.instance.setdefault("brief", {})
            if form.get("brief_text") is not None:
                b["text"] = form.get("brief_text")
            b["objective"] = form.get("objective") or None
            b["quantity"] = int(_num(form.get("quantity"))) if _num(form.get("quantity")) else None
            if form.get("answering"):
                if form["answering"] not in ANSWERING:
                    raise ValueError(f"the answering policy is park or decline, not {form['answering']!r}")
                o.instance["answering"] = form["answering"]
        return edit(request, lineage, change, "product.html", "edit order", section="order", migrated=migrated(lineage))

    @app.post("/products/{lineage}/needs", response_class=HTMLResponse)
    async def need_add(request: Request, lineage: str):
        form = await request.form()
        imp = _num(form.get("importance"))
        return edit(request, lineage, lambda o: o.add_need(form.get("text") or "", int(imp) if imp else None, form.get("group") or ""),
                    "product.html", "add need")

    @app.post("/products/{lineage}/needs/{nid}", response_class=HTMLResponse)
    async def need_edit(request: Request, lineage: str, nid: str):
        form = await request.form()

        def change(o: Order):
            n = o.need(nid)
            if n is None:
                raise KeyError(f"no need {nid}")
            if form.get("action") == "drop":
                n["dropped"] = True
                return
            n["text"] = form.get("text") or n["text"]
            imp = _num(form.get("importance"))
            n["importance"] = int(imp) if imp else None
            n["group"] = form.get("group") or ""
        return edit(request, lineage, change, "product.html", "drop need" if form.get("action") == "drop" else "edit need")

    @app.post("/products/{lineage}/picture", response_class=HTMLResponse)
    async def picture_set(request: Request, lineage: str):
        form = await request.form()
        action = form.get("action")
        try:
            if action == "design":
                home.picture_from_design(lineage)
            elif action == "clear":
                home.clear_picture(lineage)
            else:
                f = form.get("file")
                home.set_picture(lineage, await f.read(), getattr(f, "filename", "") or "")
            message = "picture saved"
        except Refused:
            message = "the picture is in the draft; the save waits for the checks"
        except HomeError as e:
            message = str(e)
        return page(request, "product.html", lineage, f"picture {action or 'set'}", message, order=working(lineage))

    @app.get("/products/{lineage}/picture")
    def picture_get(lineage: str):
        found = home.picture(working(lineage))
        if found is None:
            raise HTTPException(404, "no picture")
        path, kind = found
        return FileResponse(path, media_type=kind)

    @app.post("/products/{lineage}/save", response_class=HTMLResponse)
    async def save(request: Request, lineage: str):
        order = working(lineage)
        try:
            saved = home.save(order)
            message = f"saved as revision {saved.revision} ({saved.version[:12]})" if saved else "nothing changed, no version made"
            status = 200
        except Refused as e:
            message, status = f"the save is refused: {len(e.refusals)} checks fail; the draft is kept", 409
        except ReadOnly as e:
            message, status = str(e), 403
        return page(request, "product.html", lineage, "save", message, status, order=working(lineage))

    @app.post("/products/{lineage}/discard", response_class=HTMLResponse)
    def discard(request: Request, lineage: str):
        try:
            home.discard_draft(lineage)
            message = "the draft is discarded"
        except ReadOnly as e:
            message = str(e)
        return page(request, "product.html", lineage, "discard", message, order=working(lineage))

    # ---------------------------------------------------------------- metrics, headings, the matrix, the specification

    @app.get("/products/{lineage}/metrics", response_class=HTMLResponse)
    def metrics(request: Request, lineage: str):
        return page(request, "metrics.html", lineage, "view", order=working(lineage), name=metric_name)

    @app.post("/products/{lineage}/metrics")
    async def metric_add(request: Request, lineage: str):
        form = await request.form()
        order = working(lineage)
        try:
            mid = order.add_metric(heading=form.get("heading") or None, text=form.get("text") or "")
            home.put_draft(lineage, order)
        except ReadOnly as e:
            return page(request, "metrics.html", lineage, "add metric", str(e), 403, order=working(lineage), name=metric_name)
        log.write(f"/products/{lineage}/metrics", "add metric", detail={"metric": mid})
        return RedirectResponse(f"/products/{lineage}/metrics/{mid}", 303)

    @app.get("/products/{lineage}/metrics/{mid}", response_class=HTMLResponse)
    def metric(request: Request, lineage: str, mid: str):
        order = working(lineage)
        if order.metric(mid) is None:
            raise HTTPException(404, f"no metric {mid}")
        return page(request, "metric.html", lineage, "view", order=order, m=order.metric(mid), quantities=V.quantities(), loads=V.loads())

    @app.post("/products/{lineage}/metrics/{mid}", response_class=HTMLResponse)
    async def metric_edit(request: Request, lineage: str, mid: str):
        form = await request.form()

        def change(o: Order):
            m = o.metric(mid)
            if m is None:
                raise KeyError(f"no metric {mid}")
            if form.get("action") == "drop":
                o.drop(mid)
                return
            m["class"] = form.get("class") or None
            m["heading"] = form.get("heading") or None
            m["text"] = form.get("text") or ""
            m["object"] = form.get("object") or None
            m["quantity"] = form.get("quantity") or None
            m["unit"] = form.get("unit") or None
            m["value"] = value_from_form(form)
            under = {}
            if form.get("load_type"):
                under = {"type": form["load_type"], "magnitude": _num(form.get("magnitude")), "unit": form.get("load_unit") or None,
                         "direction": _vec(form.get("direction")), "at": form.get("at") or None, "held_by": picked(form, "held_by")}
            if picked(form, "datums"):
                under["datums"] = picked(form, "datums")
            if form.get("under_name"):
                under["name"] = form["under_name"]
            if form.get("under_text"):
                under["text"] = form["under_text"]
            m["under"] = {k: v for k, v in under.items() if v not in (None, [], "")} or None
            m["needs"] = picked(form, "needs")
            o.sort_needs(m)
            m["source"] = sources_from_text(form.get("source") or "")
            m["verified_by"] = form.get("verified_by") or None
            m["carried_by"] = picked(form, "carried_by")
        return _metric_edit(request, lineage, mid, change, form)

    @app.post("/products/{lineage}/metrics/{mid}/mandate", response_class=HTMLResponse)
    async def mandate_edit(request: Request, lineage: str, mid: str):
        """A metric's mandate in this order, written to the order's section."""
        form = await request.form()

        def change(o: Order):
            if o.metric(mid) is None:
                raise KeyError(f"no metric {mid}")
            o.set_mandate(mid, mandate_from_form(form))
        return _metric_edit(request, lineage, mid, change, form, action="edit mandate", section="order")

    def _metric_edit(request, lineage, mid, change, form, action: str | None = None, section: str = "type"):
        order = working(lineage)
        try:
            change(order)
            home.put_draft(lineage, order)
            message, status = None, 200
        except ReadOnly as e:
            order, message, status = working(lineage), str(e), 403
        except (ValueError, KeyError) as e:
            order, message, status = working(lineage), str(e), 400
        action = action or ("drop metric" if form.get("action") == "drop" else "edit metric")
        return page(request, "metric.html", lineage, action, message, status, logged={"capacity": "orderer", "section": section, "metric": mid},
                    order=order, m=order.metric(mid), quantities=V.quantities(), loads=V.loads())

    @app.post("/products/{lineage}/headings", response_class=HTMLResponse)
    async def headings(request: Request, lineage: str):
        form = await request.form()

        def change(o: Order):
            stated = dict(o.type.get("headings") or {})
            for h in V.heading_ids():
                if f"h_{h}" in form:
                    text = (form.get(f"h_{h}") or "").strip()
                    if text:
                        stated[h] = text
                    else:
                        stated.pop(h, None)
            o.type["headings"] = stated
        return edit(request, lineage, change, "metrics.html", "state headings", name=metric_name)

    @app.get("/products/{lineage}/matrix", response_class=HTMLResponse)
    def matrix(request: Request, lineage: str):
        return page(request, "matrix.html", lineage, "view", order=working(lineage), name=metric_name)

    @app.post("/products/{lineage}/matrix", response_class=HTMLResponse)
    async def matrix_cell(request: Request, lineage: str):
        form = await request.form()
        need, mid, on = form.get("need"), form.get("metric"), form.get("on") in ("1", "true", "on")

        def change(o: Order):
            m = o.metric(mid)
            if m is None or o.need(need) is None:
                raise KeyError(f"no cell {need} x {mid}")
            needs = [n for n in m.get("needs", []) if n != need] + ([need] if on else [])
            m["needs"] = needs
            o.sort_needs(m)
        return edit(request, lineage, change, "matrix.html", f"cell {need} {mid} {'on' if on else 'off'}", name=metric_name)

    @app.get("/products/{lineage}/spec", response_class=HTMLResponse)
    def spec(request: Request, lineage: str, mandate: int = 0):
        order = working(lineage)
        cols, rows = table(order, "specification", bool(mandate))
        return page(request, "spec.html", lineage, "view", order=order, cols=cols, rows=rows, mandate=bool(mandate))

    @app.get("/products/{lineage}/tables", response_class=HTMLResponse)
    def tables(request: Request, lineage: str, mandate: int = 0):
        order = working(lineage)
        shown = [(TITLES[t], *table(order, t, bool(mandate))) for t in TABLES]
        return page(request, "tables.html", lineage, "view", order=order, shown=shown, mandate=bool(mandate))

    @app.get("/products/{lineage}/export.{fmt}")
    def download(lineage: str, fmt: str):
        if fmt not in ("xlsx", "reqif"):
            raise HTTPException(404)
        data = export(working(lineage), fmt)
        media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" if fmt == "xlsx" else "application/xml"
        log.write(f"/products/{lineage}/export.{fmt}", f"export {fmt}")
        return Response(data, media_type=media, headers={"Content-Disposition": f'attachment; filename="{lineage}.{fmt}"'})

    # ---------------------------------------------------------------- objects

    @app.get("/products/{lineage}/objects", response_class=HTMLResponse)
    def objects(request: Request, lineage: str):
        return page(request, "objects.html", lineage, "view", order=working(lineage))

    @app.post("/products/{lineage}/objects", response_class=HTMLResponse)
    async def object_add(request: Request, lineage: str):
        form = await request.form()

        def change(o: Order):
            count = _num(form.get("count")) or 1
            o.add_object(form.get("name") or "", form.get("kind") or "face", int(count), form.get("datum") or None, form.get("text") or "",
                         parse_place(form.get("place") or ""), change=form.get("change") or "fixed")
        return edit(request, lineage, change, "objects.html", "add object")

    @app.post("/products/{lineage}/objects/{oid}", response_class=HTMLResponse)
    async def object_edit(request: Request, lineage: str, oid: str):
        form = await request.form()

        def change(o: Order):
            obj = o.obj(oid)
            if obj is None:
                raise KeyError(f"no object {oid}")
            if form.get("action") == "drop":
                obj["dropped"] = True
                return
            obj.update(name=form.get("name") or obj["name"], kind=form.get("kind") or obj["kind"], count=int(_num(form.get("count")) or 1),
                       datum=form.get("datum") or None, text=form.get("text") or "")
            if form.get("change"):
                o.set_change(oid, form["change"])
            place = parse_place(form.get("place") or "")
            if place is None:
                obj.pop("place", None)
            else:
                obj["place"] = place
        action = "drop object" if form.get("action") == "drop" else f"edit object ({form.get('change')})" if form.get("change") else "edit object"
        return edit(request, lineage, change, "objects.html", action)

    # ---------------------------------------------------------------- the binding

    @app.get("/products/{lineage}/binding", response_class=HTMLResponse)
    def binding(request: Request, lineage: str, design: str = ""):
        order = working(lineage)
        return page(request, "binding.html", lineage, "view", **_binding_ctx(home, order, design))

    @app.post("/products/{lineage}/binding", response_class=HTMLResponse)
    async def binding_act(request: Request, lineage: str):
        form = await request.form()
        action = form.get("action")
        detail = {}

        def change(o: Order):
            if action == "bind":
                design = form.get("design") or o.type.get("design")
                features = home.features(design) if design else None
                if features is None:
                    raise KeyError(f"no feature list of {design!r} in the products home")
                previous = home.features(o.type["design"]) if o.type.get("design") and o.type["design"] != design else None
                report = bind_order(o, features, previous)
                detail.update(declared=report["declared"], matched=report["matched"])
            elif action == "confirm":
                confirm(o, form["object"], form.get("feature") or None)
            elif action == "reject":
                reject(o, form["object"], form["feature"])
            else:
                raise KeyError(f"no action {action!r}")
        order = working(lineage)
        try:
            change(order)
            home.put_draft(lineage, order)
            message, status = None, 200
        except ReadOnly as e:
            order, message, status = working(lineage), str(e), 403
        except (ValueError, KeyError) as e:
            order, message, status = working(lineage), str(e), 400
        name = f"{action} {form.get('object', '')} {form.get('feature', '')}".strip()
        return page(request, "binding.html", lineage, name, message, status, **_binding_ctx(home, order, ""))

    @app.get("/features/{design}/{name}")
    def feature_file(design: str, name: str):
        try:
            path = home.feature_file(design, name)
        except HomeError as e:
            raise HTTPException(404, str(e))
        media = {"png": "image/png", "stl": "model/stl", "3mf": "model/3mf"}.get(name.rsplit(".", 1)[-1], "application/octet-stream")
        headers = {} if media == "image/png" else {"Content-Disposition": f'attachment; filename="{design}-{name}"'}
        return FileResponse(path, media_type=media, headers=headers)

    # ---------------------------------------------------------------- history

    @app.get("/products/{lineage}/history", response_class=HTMLResponse)
    def history(request: Request, lineage: str, a: str = "", b: str = ""):
        order = working(lineage)
        versions = home.history(lineage) if (home._folder(lineage) / "versions").exists() else []
        changes, sides, message = [], None, None
        if a and b:
            try:
                changes = home.compare(f"{lineage}@{a}", f"{lineage}@{b}")
                sides = (home.load(f"{lineage}@{a}"), home.load(f"{lineage}@{b}"))
            except HomeError as e:
                message = str(e)
        return page(request, "history.html", lineage, "view", message, order=order, versions=versions, record=home.changes(lineage),
                    a=a, b=b, changes=changes, sides=sides)

    # ---------------------------------------------------------------- the runs of am-llm, read only

    @app.get("/runs", response_class=HTMLResponse)
    def runs_page(request: Request, experiment: str = "", product: str = ""):
        root = app.state.runs_root
        experiments = R.catalogue(root) if root else []
        if product:
            experiments = [x for x in experiments if product in x.lineages]
        for x in experiments:
            if x.name == experiment:
                for r in x.runs:
                    r.decision_makers = R.decision_makers(root / r.id)
        outcomes = {}
        for x in experiments:
            counts = {}
            for r in x.runs:
                key = r.outcome or r.status
                counts[key] = counts.get(key, 0) + 1
            outcomes[x.name] = sorted(counts.items(), key=lambda kv: -kv[1])
        lineages = sorted({l for x in (R.catalogue(root) if root and product else experiments) for l in x.lineages})
        reading = app.state.frame
        framed = None
        if reading is not None:
            error = reading.read_catalogue()
            entries = [R.entry_of(d) for d in (reading.catalogue or {}).get("runs", [])]
            if product:
                entries = [x for x in entries if product in x.lineages]
            framed = {"entries": entries, "origins": {d["id"]: _origin(home, d) for d in (reading.catalogue or {}).get("runs", [])},
                      **presence_ctx(error)}
        return page(request, "runs.html", None, "runs", root=root, experiments=experiments, experiment=experiment, product=product,
                    outcomes=outcomes, lineages=lineages, total=sum(len(x.runs) for x in experiments), framed=framed)

    # ---------------------------------------------------------------- the standing frame

    def contact_note(error: FrameError | None) -> str | None:
        """What the page says when the frame did not answer as asked, keeping what it last read."""
        reading = app.state.frame
        if error is None:
            return None
        if error.kind == "unreachable":
            since = reading.frame.contact.since or datetime.now(timezone.utc)
            return f"The frame at {reading.frame.url} has not answered since {since.strftime('%Y-%m-%d %H:%M:%S')}Z ({error}); " \
                   "the page shows what it last read."
        if error.kind == "refused":
            return f"{error} (the frame's fault, not the tool's): " + "; ".join(error.reasons[:5])
        return str(error)

    def presence_ctx(catalogue_error: FrameError | None = None) -> dict:
        reading = app.state.frame
        error = reading.read_presence() or catalogue_error
        doc = reading.presence
        parts = []
        if doc is not None:
            for part in doc["parts"]:
                parts.append({**part, "reader_state": part_state(part, doc), "seen_ago": _ago(doc["at"], part["seen"])})
        levels = sorted({p["role"]["level"] for p in parts if p["kind"] == "role"})
        waits = {}
        for p in parts:
            for w in (p.get("role") or {}).get("waits") or []:
                waits.setdefault(w["run"], []).append({**w, "for": p["role"]["title"]})
        drawn, diagram = empty_cells(doc) if doc is not None else ([], None)
        return {"presence": doc, "parts": parts, "levels": levels, "waits": waits, "frame_url": reading.frame.url, "cells": drawn, "diagram": diagram,
                "contact_note": contact_note(error), "frame_error": error}

    def maker_ctx(role: str, message: str | None = None, bad: bool = False, reasons=None, error: FrameError | None = None) -> dict:
        reading = app.state.frame
        presence = reading.presence or {}
        return {"role": role, "title": R.TITLES.get(role, role), "r": reading.role(role), "message": message, "bad": bad, "reasons": reasons or [],
                "contact_note": contact_note(error), "frame_name": (presence.get("frame") or {}).get("name")}

    @app.get("/frame/roles/{role}", response_class=HTMLResponse)
    def maker_select(request: Request, role: str):
        """The selector of a role's decision maker, opened from its mark in the overview: the system operator's."""
        reading = app.state.frame
        if reading is None:
            raise HTTPException(404, "the tool is not connected to a frame; start it with --frame URL --token-file FILE")
        error = reading.read_presence()
        if reading.role(role) is None and error is None:
            raise HTTPException(404, f"the frame has no role {role}")
        return templates.TemplateResponse(request, "_maker.html", maker_ctx(role, error=error))

    @app.post("/frame/roles/{role}", response_class=HTMLResponse)
    async def maker_set(request: Request, role: str):
        """A role's decision maker placed at the frame, in the system operator's capacity; the picture redraws from presence."""
        reading = app.state.frame
        if reading is None:
            raise HTTPException(404, "the tool is not connected to a frame")
        form = await request.form()
        try:
            maker = json.loads(form.get("maker") or "")
        except ValueError:
            maker = None
        if not isinstance(maker, dict) or "kind" not in maker:
            return templates.TemplateResponse(request, "_maker.html", maker_ctx(role, "Not placed: no decision maker chosen.", True), status_code=400)
        maker = {"kind": maker["kind"], "name": maker.get("name")}
        error = reading.set_maker(role, maker)
        r = reading.role(role) or {}
        if error is None:
            when = "from the role's next waking" if r.get("next") == maker else "at once: no run is being prepared" if r.get("maker") == maker else ""
            message, bad, status = f"Placed: {maker_text(maker)} as the {R.TITLES.get(role, role).lower()}'s decision maker, {when}.".replace(", .", "."), False, 200
            answer = {"next": r.get("next"), "maker": r.get("maker")}
        else:
            message, bad = f"Not placed: {error}", True
            status = error.status if error.kind == "answer" and error.status else 503
            answer = {"status": error.status, "kind": error.kind}
        log.write(f"/frame/roles/{role}", "set maker", detail={"capacity": "system operator", "role": role, "maker": maker, "answer": answer})
        response = templates.TemplateResponse(request, "_maker.html", maker_ctx(role, message, bad, error.reasons if error else None,
                                                                                error if error is not None and error.kind != "answer" else None),
                                              status_code=status)
        if error is None:
            response.headers["HX-Trigger"] = "makers-changed"
        return response

    @app.get("/frame/presence", response_class=HTMLResponse)
    def frame_presence(request: Request):
        """The overview's empty state: what the page refreshes at its interval."""
        if app.state.frame is None:
            raise HTTPException(404, "the tool is not connected to a frame; start it with --frame URL --token-file FILE")
        return templates.TemplateResponse(request, "_presence.html", presence_ctx())

    def run_ctx(run, reading: Reading | None = None) -> dict:
        """What a run's cells show beyond its events: the order's document (the frame's, else the home's), the feature counts the
        home or the frame knows, and the frame's presence (its machines, its decision makers)."""
        order = None
        if run.order:
            ref = f"{run.order[0]}@{run.order[1]}"
            order = reading.read_order(ref) if reading is not None else None
            if order is None and home.folder(run.order[0]) is not None:
                try:
                    order = home.load(ref).data
                except HomeError:
                    order = None
        features = {}
        for _, d in run.designs:
            f = home.features(d)
            if f is not None:
                features[d] = len(f["features"])
        if reading is not None:
            for (rid, d), f in reading.features.items():
                if rid == run.entry.id and f is not None:
                    features[d] = len(f["features"])
        return {"order": order, "features": features, "presence": reading.presence if reading is not None else None}

    def frame_run(run_id: str):
        reading = app.state.frame
        if reading is None:
            raise HTTPException(404, "the tool is not connected to a frame; start it with --frame URL --token-file FILE")
        kept, error = reading.read_run(run_id)
        if kept is None:
            if error is not None and error.kind == "answer" and error.status == 404:
                raise HTTPException(404, str(error))
            return None, error
        live = kept["run"]["status"] == "running"
        run = R.from_events(kept["run"], kept["events"], reading.frame.contact.frame_now() if live else None)
        run.entry.last = kept["last"]
        return run, error

    def frame_view(request: Request, run_id: str, at: str | None, template: str):
        reading = app.state.frame
        run, error = frame_run(run_id)
        if run is None:
            return page(request, "frame_down.html", None, "run", contact_note=contact_note(error), run_id=run_id, status=503)
        if error is None:
            reading.read_presence(max_age=2.0)    # the frame's name, its machines, its decision makers and what is placed next
        st = R.state(run, R.parse_at(run, at))
        accepted = None
        design = ((run.entry.result or {}).get("plan") or {}).get("design") or run.accepted_design
        if run.entry.outcome == "accepted" and design:
            features, ferror = reading.read_features(run_id, design)
            accepted = {"design": design, "features": features, "error": str(ferror) if ferror else None}
        pic = overview(run, st, run_ctx(run, reading))
        presence = reading.presence or {}
        return page(request, template, None, "run", run=run, state=st, pic=pic, picture=True, accepted=accepted, ending=ending_of(run, st),
                    skew=reading.frame.contact.skew.total_seconds(), frame_name=(presence.get("frame") or {}).get("name") or reading.frame.url,
                    contact_note=contact_note(error))

    def frame_file(run_id: str, design: str, name: str | None):
        reading = app.state.frame
        if reading is None:
            raise HTTPException(404, "the tool is not connected to a frame")
        try:
            data, media = reading.frame.file(run_id, design, name)
        except FrameError as e:
            raise HTTPException(e.status if e.kind == "answer" and e.status else 503, str(e))
        headers = {} if media.startswith("image/") else {"Content-Disposition": f'attachment; filename="{design}-{name}"'}
        return Response(data, media_type=media, headers=headers)

    @app.get("/frame/runs/{run_id:path}/picture/{design}")
    def frame_picture(run_id: str, design: str):
        return frame_file(run_id, design, None)

    @app.get("/frame/runs/{run_id:path}/features/{design}/{name}")
    def frame_feature_file(run_id: str, design: str, name: str):
        if name not in ("picture.png", "model.stl", "model.3mf"):
            raise HTTPException(404)
        return frame_file(run_id, design, name)

    @app.get("/frame/runs/{run_id:path}/view", response_class=HTMLResponse)
    def frame_run_fragment(request: Request, run_id: str, at: str | None = None):
        return frame_view(request, run_id, at, "_overview.html")

    @app.get("/frame/runs/{run_id:path}", response_class=HTMLResponse)
    def frame_run_page(request: Request, run_id: str, at: str | None = None):
        return frame_view(request, run_id, at, "run.html")

    @app.get("/products/{lineage}/frame", response_class=HTMLResponse)
    def product_frame(request: Request, lineage: str):
        """The order at the frame: its runs and their states, and the version that may be placed (a fragment of the order's page)."""
        working(lineage)
        return templates.TemplateResponse(request, "_placing.html", placing_ctx(lineage))

    def placing_ctx(lineage: str, message: str | None = None, bad: bool = False) -> dict:
        reading = app.state.frame
        error = reading.read_catalogue() or reading.read_presence()
        held = saved_version(home, lineage)
        saved = home.load(lineage) if held else None
        facets = home.facets(lineage)
        ready = saved is not None and facets["state"] == "confirmed" and saved.form == 2
        why = None if ready else ("the order has no saved version yet" if saved is None else
                                  "the draft has changes not yet saved" if facets["state"] == "draft" else
                                  "the order is saved as order 1: answer the migration's notes and save it as order 2" if saved.form == 1 else
                                  f"the order is {facets['state']}, not confirmed: bind it to a design and confirm every binding")
        runs = reading.runs_of(lineage)
        latest = next((r for r in runs if r.get("result") or r["status"] in ("done", "parked")), None)
        card = result_card(latest["outcome"] or latest["status"], latest.get("reason"), latest.get("result")) if latest else None
        takers = [{"title": R.TITLES.get(p["id"], p["id"]), "maker": p["role"]["maker"], "next": p["role"].get("next")}
                  for p in (reading.presence or {}).get("parts", []) if p["kind"] == "role"]
        return {"lineage": lineage, "runs": runs, "card": card, "card_run": latest, "saved": saved, "takers": takers, "version": held[0] if held else None,
                "ready": ready, "why": why, "contact_note": contact_note(error), "frame_url": reading.frame.url,
                "message": message, "bad": bad}

    @app.post("/products/{lineage}/runs/{run_id:path}/delete", response_class=HTMLResponse)
    def delete_run(request: Request, lineage: str, run_id: str):
        """A run of the product's orders deleted at the frame, so that its version may be placed again: the orderer's act on the
        order's own runs, never on another product's or on an experiment's."""
        reading = app.state.frame
        if reading is None:
            raise HTTPException(404, "the tool is not connected to a frame")
        working(lineage)
        reading.read_catalogue() or reading.read_presence()
        if run_id not in {r["id"] for r in reading.runs_of(lineage)}:
            return templates.TemplateResponse(request, "_placing.html", {**placing_ctx(lineage), "bad": True,
                                              "message": f"Not deleted: {run_id} is no run of an order of {lineage} at the frame."}, status_code=404)
        try:
            answer = reading.frame.delete_run(run_id)
            reading.forget(run_id)
            message, bad, status = f"Deleted at the frame: the run {run_id}; its version may be placed again.", False, 200
        except FrameError as e:
            message = f"Not deleted: {e}"
            bad, status = True, e.status if e.kind == "answer" and e.status else 503
            answer = {"status": e.status, "kind": e.kind}
        log.write(f"/products/{lineage}/runs/{run_id}/delete", "delete run", detail={"capacity": "orderer", "run": run_id, "answer": answer})
        return templates.TemplateResponse(request, "_placing.html", {**placing_ctx(lineage), "message": message, "bad": bad}, status_code=status)

    @app.post("/products/{lineage}/place", response_class=HTMLResponse)
    def place(request: Request, lineage: str):
        """The order's saved version placed at the frame, as the home holds it; the frame makes the run, never the tool."""
        reading = app.state.frame
        if reading is None:
            raise HTTPException(404, "the tool is not connected to a frame")
        working(lineage)
        ctx = placing_ctx(lineage)
        if not ctx["ready"]:
            log.write(f"/products/{lineage}/place", "place", detail={"capacity": "orderer", "message": ctx["why"]})
            return templates.TemplateResponse(request, "_placing.html", {**ctx, "message": f"Not placed: {ctx['why']}.", "bad": True}, status_code=409)
        version, body = saved_version(home, lineage)
        try:
            answer = reading.frame.place(body)
            message, bad, status = f"Placed at the frame: the run {answer.get('run')} ({answer.get('state', 'placed')}).", False, 201
        except FrameError as e:
            message = f"Not placed: {e}" + (": " + "; ".join(e.reasons[:5]) if e.reasons else "")
            bad, status = True, e.status if e.kind == "answer" and e.status else 503
            answer = {"status": e.status, "kind": e.kind}
        log.write(f"/products/{lineage}/place", "place", detail={"capacity": "orderer", "version": version,
                                                                 "revision": ctx["saved"].data.get("revision"), "answer": answer})
        return templates.TemplateResponse(request, "_placing.html", {**placing_ctx(lineage), "message": message, "bad": bad}, status_code=status)

    @app.get("/runs/{run_id:path}/picture/{design}")
    def run_picture(run_id: str, design: str):
        root = app.state.runs_root
        run = R.read(root, run_id) if root else None
        path = R.picture_of(run, design) if run else None
        if path is None:
            raise HTTPException(404, "no picture of this version beside the run")
        return FileResponse(path)

    def run_view(request: Request, run_id: str, at: str | None, template: str):
        root = app.state.runs_root
        run = R.read(root, run_id) if root else None
        if run is None:
            raise HTTPException(404, f"{run_id} is not a run under the runs root")
        st = R.state(run, R.parse_at(run, at))
        pic = overview(run, st, run_ctx(run))
        return page(request, template, None, "run", run=run, state=st, pic=pic, picture=R.picture_of(run, st.design) is not None,
                    ending=ending_of(run, st))

    @app.get("/runs/{run_id:path}/view", response_class=HTMLResponse)
    def run_fragment(request: Request, run_id: str, at: str | None = None):
        """The part of the run's page that depends on the time: what the player fetches when the clock passes an event."""
        return run_view(request, run_id, at, "_overview.html")

    @app.get("/runs/{run_id:path}", response_class=HTMLResponse)
    def run_page(request: Request, run_id: str, at: str | None = None):
        return run_view(request, run_id, at, "run.html")

    return app


def _ago(at: str, then: str) -> str:
    """How long before the frame's `at` a time of the frame's was, in words."""
    a = datetime.fromisoformat(at.replace("Z", "+00:00"))
    b = datetime.fromisoformat(then.replace("Z", "+00:00"))
    s = max(0, int((a - b).total_seconds()))
    return f"{s} s ago" if s < 120 else f"{s // 60} min ago" if s < 7200 else f"{s // 3600} h ago"


def _origin(home: Home, run: dict) -> dict | None:
    """Where a frame's order run links in the products home: the lineage when the tool holds it, and whether the revision the
    frame names is the version the home holds under that number (by its hash)."""
    o = run.get("order")
    if not o or home.folder(o["lineage"]) is None:
        return None
    held = next((v for v in home.history(o["lineage"]) if v["revision"] == o["revision"]), None) \
        if (home._folder(o["lineage"]) / "versions").exists() else None
    return {"lineage": o["lineage"], "revision": o["revision"], "same": held is not None and held["version"] == o["sha256"],
            "held": held is not None}


def _back(request: Request, url: str, message: str):
    from urllib.parse import quote
    sep = "&" if "?" in url else "?"
    return RedirectResponse(f"{url}{sep}message={quote(message)}", 303)


def _tree(home: Home, groups: dict, rows: list[dict]) -> list[dict]:
    """The groups as a tree, each with its products (those that pass the filters)."""
    by_group: dict[str, list] = {}
    for r in rows:
        by_group.setdefault(r["group"], []).append(r)

    def node(gid, depth):
        path = home.group_path(gid)
        children = [node(c, depth + 1) for c in sorted(g for g, v in groups.items() if v["parent"] == gid)]
        return {"id": gid, "name": groups[gid]["name"], "path": path, "depth": depth, "products": by_group.get(path, []), "children": children}
    roots = [node(g, 0) for g in sorted(g for g, v in groups.items() if v["parent"] is None)]
    flat = []

    def walk(n):
        flat.append(n)
        for c in n["children"]:
            walk(c)
    for r in roots:
        walk(r)
    loose = [r for r in rows if not r["group"]]
    if loose:
        flat.append({"id": None, "name": "(no group)", "path": "", "depth": 0, "products": loose, "children": []})
    return flat


def _binding_ctx(home: Home, order: Order, design: str) -> dict:
    design = design or order.type.get("design") or ""
    features = home.features(design) if design else None
    rows, props = [], {}
    if features is not None:
        for o in order.objects():
            if o["kind"] == "part":
                continue
            b = order.binding(o["id"], design) or {"features": [], "rejected": []}
            if len(b["features"]) < o.get("count", 1):
                props[o["id"]] = proposals(order, o["id"], features)
            rows.append({"object": o, "binding": b})
    colour = {f["name"]: f["colour"] for f in features["features"]} if features else {}
    carried = [(m, [(oid, order.features_of(oid, design)) for oid in order.objects_named(m)]) for m in order.metrics()]
    return {"order": order, "design": design, "features": features, "rows": rows, "proposals": props, "colour": colour, "carried": carried,
            "designs": home.designs()}
