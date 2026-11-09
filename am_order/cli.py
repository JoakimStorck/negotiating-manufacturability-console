"""`am-order`: the order tool from the command line. Every command calls the Python API (`am_order`).

    am-order [--home DIR] [--allow-own] [--frame URL --token-file FILE] COMMAND ...

    tree [--tag T] [--state S] [--find TEXT]          the groups and their products, filtered
    groups add PATH | rename GROUP NAME | move GROUP [PARENT] | remove GROUP | list
    new LINEAGE [--name N] [--purpose P] [--group G]  a new product, a draft until its checks pass
    derive SOURCE LINEAGE [--name N] [--group G]      a copy in user, the parent recorded, the ids kept
    from-features DESIGN [--lineage L] [--group G]    a skeleton for a design that has no order
    compare A B                                       two products, or PRODUCT@<revision> against another
    check PRODUCT                                     the refusals of the draft, or of the order as it stands
    migrate PRODUCT[@REVISION] | --all [--free OBJECT ...] [--answering park|decline] [--save]
                                                      an order-1 version as an order-2 draft, the migration's notes printed;
                                                      --free states the objects the design may change around, --save saves
                                                      the draft as a new revision once the notes are answered
    show PRODUCT [--mandate] [--format markdown|html] [--table T ...]
    history PRODUCT                                   the versions and the change record
    picture PRODUCT (--set FILE | --design | --clear)
    bind PRODUCT [--design D] [--confirm OBJECT[=FEATURE] ...] [--reject OBJECT=FEATURE ...]
    move PRODUCT GROUP | tag PRODUCT [--add T ...] [--remove T ...] | archive PRODUCT
    xlsx export PRODUCT FILE | xlsx import FILE       the workbook; an import comes in as a draft and is checked
    reqif export PRODUCT FILE
    features list | add DIR                           the feature lists in the home
    serve [--host 127.0.0.1] [--port 8770] [--log DIR] [--runs DIR]
                                                      the web app, on this machine only unless --host says otherwise
                                                      (0.0.0.0 every interface, or one address of this machine)
    runs [show RUN [--at T] | delete RUN]             the frame's runs, a run's state at a time (seconds from its start), or an
                                                      order's run deleted at the frame so that its version may be placed again
    runs set ROLE=MAKER                               a role's decision maker placed at the frame, as system operator: a model's
                                                      key or name, scripted, reference or none; from the role's next waking
    place PRODUCT[@REVISION]                          a confirmed order version placed at the frame, as the home holds it
    dialogue RUN                                      the run's dialogue: what waits for the owner's word, in words
    say RUN accept [--alternative NAME] [--relax REQ=MARGIN ...] [--text T]
    say RUN refuse [--condition REQ:KEY=VALUE ...] [--hold REQ ...] --text T
    say RUN decline --text T | say RUN answer --text T
                                                      the owner's word on what waits, as orderer: an acceptance relaxes each
                                                      margin at risk to what the plan reaches (--relax req-14=0.838); a
                                                      condition is a value (req-20:at_most=20) or a margin (req-14:margin=0.7)
    approve PRODUCT                                   the plan the order's run accepted approved for manufacturing: a new
                                                      revision with the plan and the requirements in force, the accepted
                                                      version's feature list and the run's dialogue taken into the home

The home is `--home` or `AM_ORDER_HOME`. An own product opens read only unless `--allow-own` is given. `--frame URL` is a
standing frame of am-llm, its token read from `--token-file` (its one `NAME=TOKEN` line) or `AM_FRAME_TOKEN`; the frame's help
page at URL says how to obtain one.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import Home, HomeError, Order, Refused, bind, check, confirm, export, import_xlsx, reject, render
from . import runs as R
from . import dialogue as D
from .frame import Frame, FrameError, Reading, maker_text, read_token, saved_version
from .render import TABLES


def _client(url: str):
    """The HTTP client of a frame at a URL; a test gives its own."""
    return None


def _frame(args) -> Frame | None:
    if not args.frame:
        return None
    return Frame(args.frame, read_token(args.token_file), client=_client(args.frame))


def _addresses(host: str, port: int) -> str:
    """Where the web app is reached: for every interface, this machine's name and its addresses on the network."""
    if host not in ("0.0.0.0", "::"):
        return f"http://{host}:{port}/"
    import socket
    names = {socket.gethostname()}
    try:
        names |= {a[4][0] for a in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET) if not a[4][0].startswith("127.")}
    except OSError:
        pass
    return ", ".join(f"http://{n}:{port}/" for n in sorted(names)) + f" (every interface, port {port})"


def confirmed(order) -> bool:
    """An order version bound to a design with every binding confirmed: what may be placed."""
    design = order.type.get("design")
    bound = [f for b in order.type.get("bindings", []) if b["design"] == design for f in b["features"]] if design else []
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
    mg = sub.add_parser("migrate")
    mg.add_argument("product", nargs="?")
    mg.add_argument("--all", action="store_true")
    mg.add_argument("--free", action="append", default=[], help="an object the design may change around (its id)")
    mg.add_argument("--answering", choices=["park", "decline"])
    mg.add_argument("--save", action="store_true")
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
    sv.add_argument("--host", default="127.0.0.1",
                    help="the address to listen on: 127.0.0.1 this machine only (the default), 0.0.0.0 every network interface")
    sv.add_argument("--port", type=int, default=8770)
    sv.add_argument("--log")
    sv.add_argument("--runs", help="the folder am-llm writes its runs under, read only, for the runs pages")
    rn = sub.add_parser("runs")
    rn.add_argument("what", nargs="?", choices=["list", "show", "delete", "set"], default="list")
    rn.add_argument("run", nargs="?")
    rn.add_argument("--at", help="seconds from the run's start, or an ISO time; the end when not given")
    pl = sub.add_parser("place")
    pl.add_argument("product")
    dl = sub.add_parser("dialogue")
    dl.add_argument("run")
    sy = sub.add_parser("say")
    sy.add_argument("run")
    sy.add_argument("word", choices=["accept", "refuse", "decline", "answer"])
    sy.add_argument("--alternative")
    sy.add_argument("--relax", action="append", default=[], help="REQ=MARGIN: a margin at risk relaxed to what the plan reaches")
    sy.add_argument("--condition", action="append", default=[], help="REQ:KEY=VALUE, KEY a value's comparator (at_most, at_least) or margin")
    sy.add_argument("--hold", action="append", default=[], help="REQ: a requirement held as given")
    sy.add_argument("--text", default="")
    ap_ = sub.add_parser("approve")
    ap_.add_argument("product")
    args = ap.parse_args(argv)

    try:
        home = None if args.cmd in ("runs", "dialogue", "say") else Home(args.home, allow_own=args.allow_own)    # the frame's runs need no home
        return _run(args, home, ap)
    except Refused as e:
        return _refused(e)
    except HomeError as e:
        print(f"am-order: {e}", file=sys.stderr)
        return 1
    except FrameError as e:
        print(f"am-order: {e}" + ("".join(f"\n  {r}" for r in e.reasons)), file=sys.stderr)
        return 1
    except D.WordError as e:
        print(f"am-order: not sent: {e}", file=sys.stderr)
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
        refusals = check(order, features=home.features(order.type["design"]) if order.type.get("design") else None)
        for r in refusals:
            print(r)
        print(f"{args.product}: {'every check passes' if not refusals else str(len(refusals)) + ' refusals'}")
        return 1 if refusals else 0
    if cmd == "migrate":
        return _migrate(args, home, ap)
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
        design = args.design or order.type.get("design")
        if not design:
            ap.error("bind: the order names no design; give --design")
        features = home.features(design)
        if features is None:
            raise HomeError(f"no feature list of {design} in the home")
        previous = home.features(order.type["design"]) if order.type.get("design") and order.type["design"] != design else None
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
            home.create(order.lineage, order.data.get("title"), order.type["product"].get("purpose", ""), order.data.get("group"))
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
        print(f"am-order on {_addresses(args.host, args.port)} (home {home.root}, session {app.state.log.session}"
              + (f", the frame at {frame.url}" if frame else "") + ")")
        if args.host not in ("127.0.0.1", "localhost", "::1"):
            print("am-order: the web app has no login: whoever reaches it on the network can edit the products home"
                  + (" and act at the frame with this tool's token" if frame else "") + "; serve it on a network you trust", file=sys.stderr)
        uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
        return 0
    if cmd in ("runs", "place", "dialogue", "say", "approve"):
        frame = _frame(args)
        if frame is None:
            ap.error(f"{cmd}: give the frame with --frame URL (and --token-file FILE)")
        return {"runs": lambda: _runs(args, frame, ap), "dialogue": lambda: _dialogue(args, frame), "say": lambda: _say(args, frame),
                "approve": lambda: _approve(args, frame, home)}.get(cmd, lambda: _place(args, frame, home))()
    return 1


def _migrate(args, home: Home, ap) -> int:
    """Each order-1 version named (`PRODUCT` its draft or latest, `PRODUCT@REVISION` that revision) migrated to an order-2 draft,
    the notes printed; with --save the draft saved as a new revision."""
    if bool(args.all) == bool(args.product):
        ap.error("migrate: name a product, or give --all")
    if args.all and args.free:
        ap.error("migrate: --free names the objects of one product; migrate the products one by one to state them")
    refs = [lin for lin in home.lineages() if home.category(lin) != "archive"] if args.all else [args.product]
    code = 0
    for ref in refs:
        lineage = ref.partition("@")[0]
        source = home.load(ref) if "@" in ref else (home.draft(lineage) or home.load(lineage))
        if source.form == 2:
            print(f"{ref}: order 2 already")
            continue
        order = Order.from_v1(source.raw)
        for oid in args.free:
            if order.obj(oid) is None:
                raise HomeError(f"{lineage} has no object {oid}; its objects are {', '.join(o['id'] for o in order.objects())}")
            order.set_change(oid, "free")
        if args.answering:
            order.instance["answering"] = args.answering
        home.put_draft(lineage, order)
        print(f"{ref}: migrated to order 2, a draft" + ("" if order.notes else "; nothing to state"))
        for note in order.notes:
            print(f"  {note}")
        if args.free:
            print(f"  free: {', '.join(f'{o} ({order.obj(o)['name']})' for o in args.free)}")
        if args.save:
            try:
                saved = home.save(order, note=f"migrated from order 1 ({ref})" + (f"; free: {', '.join(args.free)}" if args.free else "")
                                  + (f"; answering: {args.answering}" if args.answering else ""))
            except Refused as e:
                code = _refused(e)
                continue
            print(f"  {_saved(saved, lineage)}")
    return code


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
        ap.error(f"runs {args.what}: name the run")
    if args.what == "set":
        role, _, key = args.run.partition("=")
        if not key:
            ap.error("runs set: give ROLE=MAKER")
        maker = {"none": {"kind": "none", "name": None}, "scripted": {"kind": "scripted", "name": "scripted"},
                 "reference": {"kind": "scripted", "name": "reference"}}.get(key, {"kind": "model", "name": key})
        presence = frame.set_maker(role, maker)
        r = next(p["role"] for p in presence["parts"] if p["id"] == role)
        print(f"{role}: {maker_text(r['maker'])}" + (f", {maker_text(r['next'])} from its next waking" if r.get("next") else ""))
        return 0
    if args.what == "delete":
        frame.delete_run(args.run)
        print(f"{args.run} deleted at {frame.url}; its version may be placed again")
        return 0
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
        print(f"  parked for the owner's word: a {run.parked['what']} on {', '.join(run.parked['metrics']) or 'the order'}; "
              f"read it with am-order dialogue {run.entry.id}")
    if st.outcome:
        print(f"  outcome: {st.outcome}")
    return 0


def _place(args, frame: Frame, home: Home) -> int:
    lineage, _, revision = args.product.partition("@")
    order = home.load(args.product)
    if not confirmed(order):
        raise HomeError(f"{args.product} is not confirmed: bind it to a design and confirm every binding before it is placed")
    if order.accepted():
        raise HomeError(f"{args.product} is approved for manufacturing, bound to {order.accepted()['plan']}: a change of the order is a new "
                        "revision, placed again")
    if order.form == 1:
        raise HomeError(f"{args.product} is saved as order 1: migrate it (am-order migrate {lineage}), state what the notes ask and save, "
                        "then place the order-2 revision")
    version, body = saved_version(home, lineage, order.data["revision"])
    answer = frame.place(body)
    print(f"{lineage}@{order.data['revision']} ({version[:12]}) placed at {frame.url}: the run {answer.get('run')}, {answer.get('state', 'placed')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())


def _dialogue(args, frame: Frame) -> int:
    """What waits for the owner's word in a run, in words."""
    doc = frame.dialogue(args.run)
    w = doc["waits"]
    print(f"{args.run}: {doc['run']['status']}, {len(doc['thread'])} words in its dialogue")
    if w is None:
        print("  nothing waits for the owner's word")
        return 0
    e = w["entry"]
    print(f"  a {w['what']} waits since {w['since'][:19].replace('T', ' ')}Z ({w['dialogue']})" + (f", on {', '.join(w['metrics'])}" if w["metrics"] else ""))
    print(f"  the {e['role'].replace('_', ' ')}: {e['text']}")
    for a in e.get("alternatives") or []:
        print(f"  {a['name'] or 'the way shown'}: {a['design']}, {D.figures(a.get('figures'))}" + (f" ({a['plan']})" if a.get("plan") else ""))
        for r in a.get("requirements") or []:
            x = D.asked(r)
            print(f"    relaxes {x['text']} ({x['mandate']})")
        for f in a.get("at_risk") or []:
            print(f"    {D.at_risk(f)}: an acceptance relaxes it (--relax {f['replaces']}={f['reaches']})")
        for u in a.get("unmet") or []:
            print(f"    {D.unmet(u)}")
    if e.get("certificate"):
        c = e["certificate"]
        print(f"  The certificate of exhausted means: {c['text']}" + (f" (cites {', '.join(c['cites'])})" if c.get("cites") else ""))
    return 0


def _say(args, frame: Frame) -> int:
    """The owner's word on what waits, built as the order view builds it and sent; the frame's answer in its words."""
    doc = frame.dialogue(args.run)
    if doc["waits"] is None:
        raise D.WordError(f"nothing waits for the owner's word in {args.run}")
    form = {"word": args.word, "text": args.text, "alternative": args.alternative or ""}
    entry = doc["waits"]["entry"]
    if args.word == "accept":
        way = next((a for a in entry.get("alternatives") or [] if a["name"] == args.alternative), None) \
            or ((entry.get("alternatives") or [None])[0] if len(entry.get("alternatives") or []) == 1 else None)
        given = dict(r.split("=", 1) for r in args.relax)
        missing = [f for f in (way or {}).get("at_risk") or [] if f["replaces"] not in given]
        if missing:
            raise D.WordError("the plan is at risk: relax each margin to what the plan reaches, " +
                              " ".join(f"--relax {f['replaces']}={f['reaches']}" for f in missing))
        form.update({f"relax:{k}": v for k, v in given.items()})
    for c in args.condition:
        req, _, rest = c.partition(":")
        key, _, value = rest.partition("=")
        form[f"choice:{req}"], form[f"value:{req}"] = "instead", value
    for req in args.hold:
        form[f"choice:{req}"] = "hold"
    word = D.word(form, doc["waits"], keys={c.partition(":")[0]: c.partition(":")[2].partition("=")[0] for c in args.condition})
    said = frame.say(args.run, word)
    print(f"{D.word_text(word)}: recorded at {frame.url} ({said['call']}); the run {said['run']} goes on, {said['status']}")
    return 0


def _approve(args, frame: Frame, home: Home) -> int:
    saved, run = D.approve(home, Reading(frame), args.product)
    plan = run["result"]["plan"]
    print(f"{args.product}: approved for manufacturing as revision {saved.revision} ({saved.version[:12]}): {plan['id']} for {plan['design']}, "
          f"accepted in {run['id']}")
    return 0
