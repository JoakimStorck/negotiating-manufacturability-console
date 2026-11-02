"""The web app: the person's interface to the products home, served on 127.0.0.1 for one user, rendered on the server with htmx.

    am-order serve [--home DIR] [--port 8765] [--log DIR] [--allow-own]

Every page is a URL of its own. An edit goes to the product's draft and the page comes back with the checks' refusals beside what
they concern; Save makes a version when no check fails, and a refused save keeps the draft. With `--log DIR` every action is one
JSON line in `DIR/<session>.jsonl` (time, session, page, action, the refusals shown), the session an id drawn at the start.
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
from ..diff import diff, mandate_text, value_text
from ..export import export
from ..home import Home, HomeError, ReadOnly, Refused
from ..order import Order
from ..render import TABLES, TITLES, metric_name, table

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
        with self.path.open("a") as f:
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


# -------------------------------------------------------------------- the app

def create_app(home: Home, log_dir: Path | None = None) -> FastAPI:
    app = FastAPI(title="am-order", docs_url=None, redoc_url=None, openapi_url=None)
    templates = Jinja2Templates(directory=str(HERE / "templates"))
    templates.env.globals.update(value_text=value_text, mandate_text=mandate_text, heading_name=V.heading_name, place_text=place_text,
                                 sources_text=sources_text, TITLES=TITLES)
    app.mount("/static", StaticFiles(directory=str(HERE / "static")), name="static")
    log = Log(log_dir)
    app.state.home, app.state.log = home, log

    def features_of(order: Order):
        return home.features(order.data["design"]) if order.data.get("design") else None

    def refusals_of(lineage: str, order: Order):
        previous = home.load(lineage) if home.folder(lineage) and (home._folder(lineage) / "order.json").exists() else None
        return check(order, features=features_of(order), previous=previous)

    def page(request: Request, template: str, lineage: str | None, action: str, message: str | None = None, status: int = 200, **ctx):
        message = message or request.query_params.get("message")
        order = ctx.get("order")
        refusals = refusals_of(lineage, order) if order is not None and lineage else []
        by_item: dict[str, list] = {}
        for r in refusals:
            by_item.setdefault(r.item, []).append(r)
        facets = home.facets(lineage) if lineage and home.folder(lineage) else None
        writable = home.writable(lineage) if lineage and home.folder(lineage) else True
        log.write(request.url.path, action, refusals, {"message": message} if message else None)
        return templates.TemplateResponse(request, template, {"home": home, "lineage": lineage, "refusals": refusals, "by_item": by_item,
                                                              "message": message, "facets": facets, "writable": writable, "V": V,
                                                              "session": log.session, **ctx}, status_code=status)

    def working(lineage: str) -> Order:
        if home.folder(lineage) is None:
            raise HTTPException(404, f"{lineage} is not in the products home")
        return home.working(lineage)

    def edit(request: Request, lineage: str, change, template: str, action: str, **ctx):
        """Apply a change to the draft and show the page, or the reason the change is not made."""
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
        return page(request, template, lineage, action, message, status, order=order, **ctx)

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
        return page(request, "product.html", lineage, "view", order=working(lineage))

    @app.post("/products/{lineage}/product", response_class=HTMLResponse)
    async def product_edit(request: Request, lineage: str):
        form = await request.form()

        def change(o: Order):
            o.data["title"] = form.get("title") or o.data.get("title")
            o.data["product"]["name"] = form.get("name") or o.data["product"]["name"]
            o.data["product"]["purpose"] = form.get("purpose") or ""
            b = o.data.setdefault("brief", {})
            b["objective"] = form.get("objective") or None
            b["quantity"] = int(_num(form.get("quantity"))) if _num(form.get("quantity")) else None
            b["may_change"] = [t.strip() for t in (form.get("may_change") or "").split(",") if t.strip()]
            b["may_relax"] = [t.strip() for t in (form.get("may_relax") or "").split(",") if t.strip()]
            if form.get("brief_text") is not None:
                b["text"] = form.get("brief_text")
        return edit(request, lineage, change, "product.html", "edit product")

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
                m["dropped"] = True
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
                         "direction": _vec(form.get("direction")), "at": form.get("at") or None, "held_by": form.getlist("held_by")}
            if form.getlist("datums"):
                under["datums"] = form.getlist("datums")
            if form.get("under_name"):
                under["name"] = form["under_name"]
            if form.get("under_text"):
                under["text"] = form["under_text"]
            m["under"] = {k: v for k, v in under.items() if v not in (None, [], "")} or None
            m["needs"] = form.getlist("needs")
            o.sort_needs(m)
            m["source"] = sources_from_text(form.get("source") or "")
            m["verified_by"] = form.get("verified_by") or None
            m["carried_by"] = form.getlist("carried_by")
            m["mandate"] = mandate_from_form(form)
        return _metric_edit(request, lineage, mid, change, form)

    def _metric_edit(request, lineage, mid, change, form):
        order = working(lineage)
        try:
            change(order)
            home.put_draft(lineage, order)
            message, status = None, 200
        except ReadOnly as e:
            order, message, status = working(lineage), str(e), 403
        except (ValueError, KeyError) as e:
            order, message, status = working(lineage), str(e), 400
        return page(request, "metric.html", lineage, "drop metric" if form.get("action") == "drop" else "edit metric", message, status,
                    order=order, m=order.metric(mid), quantities=V.quantities(), loads=V.loads())

    @app.post("/products/{lineage}/headings", response_class=HTMLResponse)
    async def headings(request: Request, lineage: str):
        form = await request.form()

        def change(o: Order):
            stated = dict(o.data.get("headings") or {})
            for h in V.heading_ids():
                if f"h_{h}" in form:
                    text = (form.get(f"h_{h}") or "").strip()
                    if text:
                        stated[h] = text
                    else:
                        stated.pop(h, None)
            o.data["headings"] = stated
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
                         parse_place(form.get("place") or ""))
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
            place = parse_place(form.get("place") or "")
            if place is None:
                obj.pop("place", None)
            else:
                obj["place"] = place
        return edit(request, lineage, change, "objects.html", "drop object" if form.get("action") == "drop" else "edit object")

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
                design = form.get("design") or o.data.get("design")
                features = home.features(design) if design else None
                if features is None:
                    raise KeyError(f"no feature list of {design!r} in the products home")
                previous = home.features(o.data["design"]) if o.data.get("design") and o.data["design"] != design else None
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

    return app


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
    design = design or order.data.get("design") or ""
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
