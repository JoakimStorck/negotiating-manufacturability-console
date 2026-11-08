"""`am-order`: the order tool from the command line. Every command calls the Python API (`am_order`).

    am-order [--home DIR] [--allow-own] [--frame URL --token-file FILE] COMMAND ...

    tree [--tag T] [--state S] [--find TEXT]          the groups and their products, filtered
    groups add PATH | rename GROUP NAME | move GROUP [PARENT] | remove GROUP | list
    new LINEAGE [--name N] [--purpose P] [--group G]  a new product, a draft until its checks pass
    derive SOURCE LINEAGE [--name N] [--group G]      a copy in user, the parent recorded, the ids kept
    from-features DESIGN [--lineage L] [--group G]    a skeleton for a design that has no order
    compare A B                                       two products, or PRODUCT@<revision> against another
    check PRODUCT                                     the refusals of the draft, or of the order as it stands
    show PRODUCT [--mandate] [--format markdown|html] [--table T ...]
    history PRODUCT                                   the versions and the change record
    picture PRODUCT (--set FILE | --design | --clear)
    bind PRODUCT [--design D] [--confirm OBJECT[=FEATURE] ...] [--reject OBJECT=FEATURE ...]
    move PRODUCT GROUP | tag PRODUCT [--add T ...] [--remove T ...] | archive PRODUCT
    xlsx export PRODUCT FILE | xlsx import FILE       the workbook; an import comes in as a draft and is checked
    reqif export PRODUCT FILE
    features list | add DIR                           the feature lists in the home
    serve [--port 8770] [--log DIR] [--runs DIR]      the web app on 127.0.0.1
    runs [show RUN [--at T]]                          the frame's runs, or a run's state at a time (seconds from its start)
    place PRODUCT[@REVISION]                          a confirmed order version placed at the frame, as the home holds it

The home is `--home` or `AM_ORDER_HOME`. An own product opens read only unless `--allow-own` is given. `--frame URL` is a
standing frame of am-llm, its token read from `--token-file` (its one `NAME=TOKEN` line) or `AM_FRAME_TOKEN`; the frame's help
page at URL says how to obtain one.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import Home, HomeError, Refused, bind, check, confirm, export, import_xlsx, reject, render
from . import runs as R
from .frame import Frame, FrameError, read_token
from .render import TABLES


def _client(url: str):
    """The HTTP client of a frame at a URL; a test gives its own."""
    return None


def _frame(args) -> Frame | None:
    if not args.frame:
        return None
    return Frame(args.frame, read_token(args.token_file), client=_client(args.frame))


def confirmed(order) -> bool:
    """An order version bound to a design with every binding confirmed: what may be placed."""
    design = order.data.get("design")
    bound = [f for b in order.data.get("bindings", []) if b["design"] == design for f in b["features"]] if design else []
    return bool(bound) and all(f["confirmed"] for f in bound)


def _saved(saved, lineage: str) -> str:
    return f"{lineage}: revision {saved.revision}, {saved.version[:12]}" if saved else f"{lineage}: nothing changed, no version made"


def _refused(e: Refused) -> int:
    print(f"{e.lineage}: the save is refused; the draft is kept. Refusals:")
    for r in e.refusals:
        print(f"  {r}")
    return 2


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="am-order", description=__doc__.splitlines()[0])
    ap.add_argument("--home")
    ap.add_argument("--allow-own", action="store_true")
    ap.add_argument("--frame", help="a standing frame of am-llm: its URL")
    ap.add_argument("--token-file", help="the file with the token for the frame (its one NAME=TOKEN line)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("tree")
    t.add_argument("--tag")
    t.add_argument("--state")
    t.add_argument("--find")
    g = sub.add_parser("groups")
    g.add_argument("what", choices=["add", "rename", "move", "remove", "list"])
    g.add_argument("args", nargs="*")
    n = sub.add_parser("new")
    n.add_argument("lineage")
    n.add_argument("--name")
    n.add_argument("--purpose", default="")
    n.add_argument("--group")
    d = sub.add_parser("derive")
    d.add_argument("source")
    d.add_argument("lineage")
    d.add_argument("--name")
    d.add_argument("--group")
    ff = sub.add_parser("from-features")
    ff.add_argument("design")
    ff.add_argument("--lineage")
    ff.add_argument("--group")
    c = sub.add_parser("compare")
    c.add_argument("a")
    c.add_argument("b")
    ch = sub.add_parser("check")
    ch.add_argument("product")
    s = sub.add_parser("show")
    s.add_argument("product")
    s.add_argument("--mandate", action="store_true")
    s.add_argument("--format", default="markdown", choices=["markdown", "html"])
    s.add_argument("--table", action="append", choices=TABLES)
    h = sub.add_parser("history")
    h.add_argument("product")
    p = sub.add_parser("picture")
    p.add_argument("product")
    p.add_argument("--set", dest="file")
    p.add_argument("--design", action="store_true")
    p.add_argument("--clear", action="store_true")
    b = sub.add_parser("bind")
    b.add_argument("product")
    b.add_argument("--design")
    b.add_argument("--confirm", action="append", default=[])
    b.add_argument("--reject", action="append", default=[])
    mv = sub.add_parser("move")
    mv.add_argument("product")
    mv.add_argument("group")
    tg = sub.add_parser("tag")
    tg.add_argument("product")
    tg.add_argument("--add", action="append", default=[])
    tg.add_argument("--remove", action="append", default=[])
    ar = sub.add_parser("archive")
    ar.add_argument("product")
    x = sub.add_parser("xlsx")
    x.add_argument("what", choices=["export", "import"])
    x.add_argument("args", nargs="+")
    r = sub.add_parser("reqif")
    r.add_argument("what", choices=["export"])
    r.add_argument("product")
    r.add_argument("file")
    fe = sub.add_parser("features")
    fe.add_argument("what", choices=["list", "add"])
    fe.add_argument("dir", nargs="?")
    sv = sub.add_parser("serve")
    sv.add_argument("--port", type=int, default=8770)
    sv.add_argument("--log")
    sv.add_argument("--runs", help="the folder am-llm writes its runs under, read only, for the runs pages")
    rn = sub.add_parser("runs")
    rn.add_argument("what", nargs="?", choices=["list", "show"], default="list")
    rn.add_argument("run", nargs="?")
    rn.add_argument("--at", help="seconds from the run's start, or an ISO time; the end when not given")
    pl = sub.add_parser("place")
    pl.add_argument("product")
    args = ap.parse_args(argv)

    try:
        home = None if args.cmd == "runs" else Home(args.home, allow_own=args.allow_own)    # the frame's runs need no home
        return _run(args, home, ap)
    except Refused as e:
        return _refused(e)
    except HomeError as e:
        print(f"am-order: {e}", file=sys.stderr)
        return 1
    except FrameError as e:
        print(f"am-order: {e}" + ("".join(f"\n  {r}" for r in e.reasons)), file=sys.stderr)
        return 1


def _run(args, home: Home, ap) -> int:
    cmd = args.cmd
    if cmd == "tree":
        rows = home.tree(args.tag, args.state, args.find)
        by_group: dict[str, list] = {}
        for row in rows:
            by_group.setdefault(row["group"], []).append(row)
        for group in sorted(by_group):
            print(group or "(no group)")
            for row in by_group[group]:
                print(f"  {row['lineage']:24} {row['state']:9} {row['category']:7} {row['title']}"
                      + (f"  [{', '.join(row['tags'])}]" if row["tags"] else ""))
        return 0
    if cmd == "groups":
        a = args.args
        if args.what == "list":
            for gid in sorted(home.groups(), key=home.group_path):
                print(f"{gid:5} {home.group_path(gid)}")
        elif args.what == "add":
            print(home.add_group(a[0]))
        elif args.what == "rename":
            home.rename_group(a[0], a[1])
        elif args.what == "move":
            home.move_group(a[0], a[1] if len(a) > 1 else None)
        else:
            home.remove_group(a[0])
        return 0
    if cmd == "new":
        home.create(args.lineage, args.name, args.purpose, args.group)
        print(f"{args.lineage}: a draft in user")
        return 0
    if cmd == "derive":
        order = home.derive(args.source, args.lineage, args.name, args.group)
        state = "saved" if home.draft(order.lineage) is None else "a draft (its checks fail)"
        print(f"{order.lineage}: derived from {args.source}, {state}")
        return 0
    if cmd == "from-features":
        order = home.from_features(args.design, args.lineage, args.group)
        print(f"{order.lineage}: a skeleton from {args.design}, {len(order.objects())} objects, a draft")
        return 0
    if cmd == "compare":
        for c in home.compare(args.a, args.b):
            print(f"- {c['text']}")
        return 0
    if cmd == "check":
        order = home.working(args.product)
        refusals = check(order, features=home.features(order.data["design"]) if order.data.get("design") else None)
        for r in refusals:
            print(r)
        print(f"{args.product}: {'every check passes' if not refusals else str(len(refusals)) + ' refusals'}")
        return 1 if refusals else 0
    if cmd == "show":
        print(render(home.working(args.product), args.format, args.table or TABLES, mandate=args.mandate), end="")
        return 0
    if cmd == "history":
        for v in home.history(args.product):
            print(f"revision {v['revision']}: {v['version'][:12]} {v['saved']}")
        print()
        print(home.changes(args.product), end="")
        return 0
    if cmd == "picture":
        if sum(bool(x) for x in (args.file, args.design, args.clear)) != 1:
            ap.error("picture: give one of --set FILE, --design, --clear")
        if args.file:
            saved = home.set_picture(args.product, Path(args.file).read_bytes(), Path(args.file).name)
        elif args.design:
            saved = home.picture_from_design(args.product)
        else:
            saved = home.clear_picture(args.product)
        print(_saved(saved, args.product))
        return 0
    if cmd == "bind":
        order = home.working(args.product)
        design = args.design or order.data.get("design")
        if not design:
            ap.error("bind: the order names no design; give --design")
        features = home.features(design)
        if features is None:
            raise HomeError(f"no feature list of {design} in the home")
        previous = home.features(order.data["design"]) if order.data.get("design") and order.data["design"] != design else None
        report = bind(order, features, previous)
        for item in args.confirm:
            obj, _, feature = item.partition("=")
            confirm(order, obj, feature or None)
        for item in args.reject:
            obj, _, feature = item.partition("=")
            reject(order, obj, feature)
        print(json.dumps({k: v for k, v in report.items()}, indent=1, ensure_ascii=False))
        print(_saved(home.save(order), args.product))
        return 0
    if cmd == "move":
        print(_saved(home.move(args.product, args.group), args.product))
        return 0
    if cmd == "tag":
        print(_saved(home.tag(args.product, args.add, args.remove), args.product))
        return 0
    if cmd == "archive":
        print(f"{args.product}: archived in {home.archive(args.product)}")
        return 0
    if cmd == "xlsx":
        if args.what == "export":
            product, path = args.args
            export(home.working(product), "xlsx", path)
            print(f"{product}: {path}")
            return 0
        order = import_xlsx(Path(args.args[0]).read_bytes())
        if home.folder(order.lineage) is None:
            home.create(order.lineage, order.data.get("title"), order.data["product"].get("purpose", ""), order.data.get("group"))
        print(_saved(home.save(order, note=f"imported from {Path(args.args[0]).name}"), order.lineage))
        return 0
    if cmd == "reqif":
        export(home.working(args.product), "reqif", args.file)
        print(f"{args.product}: {args.file}")
        return 0
    if cmd == "features":
        if args.what == "list":
            for design in home.designs():
                f = home.features(design)
                print(f"{design:28} {len(f['features']):3} features  {f.get('title', '')}")
        else:
            print(home.add_features(args.dir))
        return 0
    if cmd == "serve":
        import uvicorn
        from .web.app import create_app
        frame = _frame(args)
        app = create_app(home, Path(args.log) if args.log else None, Path(args.runs) if args.runs else None, frame=frame)
        print(f"am-order on http://127.0.0.1:{args.port}/ (home {home.root}, session {app.state.log.session}"
              + (f", the frame at {frame.url}" if frame else "") + ")")
        uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")
        return 0
    if cmd in ("runs", "place"):
        frame = _frame(args)
        if frame is None:
            ap.error(f"{cmd}: give the frame with --frame URL (and --token-file FILE)")
        return _runs(args, frame, ap) if cmd == "runs" else _place(args, frame, home)
    return 1


def _runs(args, frame: Frame, ap) -> int:
    if args.what == "list":
        for d in frame.runs()["runs"]:
            e = R.entry_of(d)
            origin = f"order {e.condition}" if e.experiment == "orders" else f"{e.experiment} / {e.condition}"
            minutes = f"{e.minutes:.0f} min" if e.minutes is not None else ""
            print(f"{e.id:40} {origin:32} {e.status:8} {e.started.strftime('%Y-%m-%d %H:%M') if e.started else '':16} {minutes:>7} "
                  f"{e.outcome or ''}{f' ({e.reason})' if e.reason else ''}")
        return 0
    if not args.run:
        ap.error("runs show: name the run")
    doc = frame.events(args.run, 0)
    run = R.from_events(doc["run"], doc["events"], frame.contact.frame_now() if doc["run"]["status"] == "running" else None)
    st = R.state(run, R.parse_at(run, args.at))
    seconds = (st.at - run.start).total_seconds() if run.start else 0
    print(f"{run.entry.id} at {int(seconds) // 3600}:{int(seconds) % 3600 // 60:02d}:{int(seconds) % 60:02d} ({st.at.strftime('%Y-%m-%d %H:%M:%SZ')}),"
          f" {st.seen} of {len(run.events)} events")
    for role in run.roles:
        doing = "at work" + (f", {st.activity[role].word}" if role in st.activity else "") if role in st.awake else st.waiting.get(role, "asleep")
        print(f"  {R.TITLES.get(role, role):24} {run.decision_makers.get(role, 'not woken'):24} {doing}")
    if st.design:
        print(f"  design {st.design}")
    if run.parked:
        print(f"  parked for the owner's word: a {run.parked['what']} on {', '.join(run.parked['metrics']) or 'the order'}")
    if st.outcome:
        print(f"  outcome: {st.outcome}")
    return 0


def _place(args, frame: Frame, home: Home) -> int:
    lineage, _, revision = args.product.partition("@")
    order = home.load(args.product)
    if not confirmed(order):
        raise HomeError(f"{args.product} is not confirmed: bind it to a design and confirm every binding before it is placed")
    version = home.version_of(lineage) if not revision else next(v["version"] for v in home.history(lineage) if v["revision"] == order.data["revision"])
    body = (home._folder(lineage) / "versions" / f"{version}.json").read_bytes()
    answer = frame.place(body)
    print(f"{lineage}@{order.data['revision']} ({version[:12]}) placed at {frame.url}: the run {answer.get('run')}, {answer.get('state', 'placed')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
