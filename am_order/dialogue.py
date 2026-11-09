"""The dialogue between the order's owner and the frame (`schemas/dialogue-1.json`) as the tool puts it to the owner, and the
approval it ends in.

- In words: what a showing asks (`asked`), what its plan leaves at risk (`at_risk`) or unmet (`unmet`), what a word says
  (`word_text`), each relaxation marked within or beyond the order's mandate as the frame judges it.
- The owner's word from a form (`word`): `accept` with R12's relaxations, each margin at risk relaxed to what the plan reaches;
  `refuse` with the conditions the owner would accept instead and the requirements held as given; `decline` with the reason;
  `answer`. Refused before it is sent where it lacks what its kind needs (`WordError`, in words).
- The approval (`approved`): a new revision of the order whose `order` section records the plan accepted (the run, the order version
  placed with its hash, the plan, the design version and the design's hash, the time) and the requirements in force (each
  relaxation of the run's result, by whom, on which showing, the run and the time). `take_features` brings the accepted version's
  feature list, picture and models from the frame into the products home.

The owner's word is not bounded by the order's mandate, which binds the requester agent; the frame says of each relaxation
whether the mandate covers it, and the tool shows it.
"""
from __future__ import annotations

import copy
import json
import tempfile
from pathlib import Path

from .diff import value_text
from .home import HomeError
from .order import Order
from .schema import SchemaError, validate_word

KINDS = {"accept": "accepted", "refuse": "remark", "decline": "declined", "answer": "answer"}


class WordError(ValueError):
    """A word that lacks what its kind needs, said in words before it is sent."""


def _n(v) -> str:
    return f"{v:g}" if isinstance(v, float) else str(v)


def _unit(u: str | None) -> str:
    return f" {u}" if u and u not in ("1", "-") else ""


def _name(x: dict) -> str:
    return x.get("metric") or x["replaces"]


def _mandate(within) -> str:
    return {True: "within the order's mandate", False: "beyond the order's mandate"}.get(within, "the order gives no metric for it")


def asked(r: dict) -> dict:
    """A relaxation a showing asks, in words ("the margin on M8 from 0.6 to 0.806", "M13 from at most 16 g to at most 20 g"),
    with whether the order's mandate covers it."""
    f, t = r["from"], r["to"]
    if f.get("margin") != t.get("margin") and f.get("body") == t.get("body"):
        text = f"the margin on {_name(r)} from {_n(f.get('margin'))} to {_n(t.get('margin'))}"
    else:
        body_from = {k: v for k, v in (f.get("body") or {}).items() if k != "basis"}
        body_to = {k: v for k, v in (t.get("body") or {}).items() if k != "basis"}
        text = f"{_name(r)} from {value_text(body_from, r.get('unit'))} to {value_text(body_to, r.get('unit'))}"
        if f.get("margin") != t.get("margin"):
            text += f", its margin from {_n(f.get('margin'))} to {_n(t.get('margin'))}"
    return {"replaces": r["replaces"], "text": text, "within": r.get("within_mandate"), "mandate": _mandate(r.get("within_mandate"))}


def at_risk(f: dict) -> str:
    where = f" at {f['feature']}" if f.get("feature") else ""
    return f"{_name(f)}{where} at risk: the plan reaches {_n(f['reaches'])}{_unit(f.get('unit'))} against the margin {_n(f['margin'])}"


def unmet(u: dict) -> str:
    reaches = f": the plan reaches {_n(u['reaches'])}{_unit(u.get('unit'))}" if u.get("reaches") is not None else ""
    return f"{_name(u)} ({u['kind'].replace('_', ' ')}) unmet{reaches}"


def figures(f: dict | None) -> str:
    if not f:
        return "no plan's figures"
    out = []
    if f.get("print_time_s") is not None:
        out.append(f"{f['print_time_s'] / 60:.0f} min print time")
    if f.get("material_g") is not None:
        out.append(f"{f['material_g']:.1f} g material")
    if f.get("mass_g") is not None:
        out.append(f"{f['mass_g']:.2f} g printed")
    return ", ".join(out) or "no plan's figures"


def items(entry: dict, order: Order | None = None) -> list[dict]:
    """What a refusal may speak to, once each: every requirement the showing's ways relax, leave unmet or leave at risk, with the
    form a condition on it takes (`key`: a value's comparator, `band`, or `margin`) and the value prefilled (what was shown)."""
    out: dict[str, dict] = {}
    for a in entry.get("alternatives") or []:
        for r in a.get("requirements") or []:
            if r["replaces"] in out:
                continue
            f, t = r["from"], r["to"]
            if f.get("margin") != t.get("margin") and f.get("body") == t.get("body"):
                key, value = "margin", t.get("margin")
            else:
                key, value = _key(t.get("body") or f.get("body") or {})
            out[r["replaces"]] = {"replaces": r["replaces"], "text": asked(r)["text"], "key": key, "value": value, "unit": r.get("unit")}
        for u in a.get("unmet") or []:
            if u["replaces"] in out:
                continue
            m = order.metric(u["metric"]) if order is not None and u.get("metric") else None
            key, _ = _key((m or {}).get("value") or {})
            out[u["replaces"]] = {"replaces": u["replaces"], "text": unmet(u), "key": key, "value": u.get("reaches"), "unit": u.get("unit")}
        for f in a.get("at_risk") or []:
            if f["replaces"] not in out:
                out[f["replaces"]] = {"replaces": f["replaces"], "text": at_risk(f), "key": "margin", "value": f["reaches"], "unit": None}
    return list(out.values())


def _key(body: dict) -> tuple[str | None, object]:
    """The comparator a condition on a value states, and the value shown: at most, at least, a band; None where the form is not a
    number the owner can give."""
    for k in ("at_most", "at_least", "equals"):
        if isinstance(body.get(k), (int, float)):
            return k, body[k]
    if isinstance(body.get("band"), dict):
        return "band", f"{_n(body['band']['lower'])} {_n(body['band']['upper'])}"
    return None, None


def _number(text, what: str) -> float:
    try:
        v = float(str(text).replace(",", ".").strip())
    except ValueError:
        raise WordError(f"{what}: {text!r} is not a number")
    if v <= 0:
        raise WordError(f"{what}: give a value above zero")
    return int(v) if v.is_integer() else v


def word(form, waits: dict, order: Order | None = None, keys: dict | None = None) -> dict:
    """The owner's word (`word/1`) from a form's fields, on what waits: `word` (accept, refuse, decline, answer), `text`; an
    acceptance's `alternative` and `relax:<req>` margins; a refusal's `choice:<req>` (hold, instead) and `value:<req>`. `keys`
    names a condition's form where the caller states it (`at_most`, `margin`), for any requirement of the design shown."""
    kind = form.get("word")
    text = (form.get("text") or "").strip()
    entry = waits["entry"]
    if kind == "answer":
        if waits["what"] != "question":
            raise WordError("a showing waits, not a question: accept it, refuse it or decline the order")
        if not text:
            raise WordError("an answer says something: write it")
        doc = {"schema": "word/1", "word": "answer", "question": waits["dialogue"], "text": text}
    elif kind in ("accept", "refuse", "decline"):
        if waits["what"] != "showing":
            raise WordError("a question waits: answer it")
        doc = {"schema": "word/1", "word": kind, "showing": waits["dialogue"]}
        if kind == "accept":
            ways = entry.get("alternatives") or []
            name = form.get("alternative") or None
            way = next((a for a in ways if a["name"] == name), None) if name else (ways[0] if len(ways) == 1 else None)
            if way is None:
                raise WordError(f"the showing offers {len(ways)} ways: accept one of them")
            if name:
                doc["alternative"] = name
            relaxes = []
            for f in way.get("at_risk") or []:
                raw = form.get(f"relax:{f['replaces']}")
                if raw in (None, ""):
                    raise WordError(f"the plan is at risk on {_name(f)}: an acceptance relaxes its margin to what the plan reaches, "
                                    f"{_n(f['reaches'])}; confirm it")
                relaxes.append({"replaces": f["replaces"], "margin": _number(raw, f"the margin on {_name(f)}")})
            for r, f in zip(relaxes, way.get("at_risk") or []):
                if r["margin"] < f["reaches"]:
                    raise WordError(f"the margin on {_name(f)} relaxed to {_n(r['margin'])} still leaves the plan at risk: it reaches "
                                    f"{_n(f['reaches'])}, and a plan at risk is accepted only with its margin relaxed to what it reaches")
            if relaxes:
                doc["relaxes"] = relaxes
        elif kind == "refuse":
            conditions, held = [], []
            known = items(entry, order)
            for req, key in (keys or {}).items():
                found = next((it for it in known if it["replaces"] == req), None)
                if found is None:
                    known.append({"replaces": req, "text": req, "key": key, "value": None, "unit": None})
                else:
                    found["key"] = key
            for req in [k[len("choice:"):] for k in form.keys() if k.startswith("choice:")]:
                if not any(it["replaces"] == req for it in known) and form.get(f"choice:{req}") == "hold":
                    known.append({"replaces": req, "text": req, "key": None, "value": None, "unit": None})
            for it in known:
                choice = form.get(f"choice:{it['replaces']}") or ""
                if choice == "hold":
                    held.append(it["replaces"])
                elif choice == "instead":
                    raw = form.get(f"value:{it['replaces']}")
                    what = f"what you would accept on {it['replaces']}"
                    if it["key"] == "margin":
                        conditions.append({"replaces": it["replaces"], "margin": _number(raw, what)})
                    elif it["key"] == "band":
                        parts = str(raw or "").replace(",", " ").split()
                        if len(parts) != 2:
                            raise WordError(f"{what}: give the band's lower and upper value")
                        conditions.append({"replaces": it["replaces"], "body": {"band": {"lower": _number(parts[0], what), "upper": _number(parts[1], what)}}})
                    elif it["key"]:
                        conditions.append({"replaces": it["replaces"], "body": {it["key"]: _number(raw, what)}})
                    else:
                        raise WordError(f"{it['replaces']} takes no value from here: hold it as given, or say in the text what you would accept")
            if not conditions and not held:
                raise WordError("a refusal states at least one requirement you would accept instead, or one you hold as given")
            if not text:
                raise WordError("a refusal says why in a text")
            if conditions:
                doc["conditions"] = conditions
            if held:
                doc["held"] = held
        elif not text:
            raise WordError("a decline names what you hold that what was shown cannot meet: write it")
        if text:
            doc["text"] = text
    else:
        raise WordError(f"no word {kind!r}: accept, refuse, decline or answer")
    try:
        return validate_word(doc)
    except SchemaError as e:
        raise WordError("; ".join(e.errors))


def word_text(w: dict) -> str:
    """A word in a line, for the log and the page."""
    k = w["word"]
    if k == "accept":
        r = ", ".join(f"the margin on {x['replaces']} to {_n(x['margin'])}" for x in w.get("relaxes") or [])
        return f"accept the showing {w['showing']}" + (f" ({w['alternative']})" if w.get("alternative") else "") + (f", relaxing {r}" if r else "")
    if k == "refuse":
        c = [f"{x['replaces']} " + (f"margin {_n(x['margin'])}" if "margin" in x else value_text(x["body"])) for x in w.get("conditions") or []]
        h = [f"{x} held as given" for x in w.get("held") or []]
        return f"refuse the showing {w['showing']}: " + "; ".join(c + h)
    if k == "decline":
        return f"decline the order on the showing {w['showing']}"
    return f"answer the question {w['question']}"


def confirm_text(kind: str, entry: dict | None = None, alternative: dict | None = None) -> str:
    """What a word does, for its confirmation before it is sent."""
    if kind == "accept":
        r = [f"the margin on {_name(f)} to {_n(f['reaches'])}" for f in (alternative or {}).get("at_risk") or []]
        a = [asked(x)["text"] for x in (alternative or {}).get("requirements") or []]
        return ("Accept what was shown" + (f", relaxing {'; '.join(a + r)}" if a or r else "") +
                "? The run goes on with your acceptance: the design engineer sends the requirements in force down.")
    if kind == "refuse":
        return "Refuse the showing with the conditions and holds you stated? The design engineer takes them up and shows again."
    if kind == "decline":
        return "Decline the order? The run ends declined, with your reason."
    return "Send your answer? The run goes on with it."


# -------------------------------------------------------------------- the approval

def level(side):
    """A requirement's side as an order's level: a number, three sizes, or a band; None where it is no number."""
    if isinstance(side, (int, float)) and not isinstance(side, bool):
        return side
    if isinstance(side, list) and len(side) == 3:
        return side
    if isinstance(side, dict):
        for k in ("at_most", "at_least", "equals"):
            v = side.get(k)
            if isinstance(v, (int, float)) and not isinstance(v, bool) or isinstance(v, list) and len(v) == 3:
                return v
        if isinstance(side.get("band"), dict):
            return {"lower": side["band"]["lower"], "upper": side["band"]["upper"]}
        if "lower" in side and "upper" in side:
            return {"lower": side["lower"], "upper": side["upper"]}
    return None


def accepted_at(dialogue: dict, showing: str | None) -> str | None:
    """When the acceptance of a showing was given, from the dialogue's thread; the latest acceptance where none names it."""
    accepts = [e for e in (dialogue or {}).get("thread") or [] if e["kind"] == "accepted"]
    named = [e for e in accepts if e.get("shown") == showing]
    found = (named or accepts)[-1:] if (named or accepts) else []
    return found[0]["time"] if found else None


def in_force(result: dict, run_id: str, dialogue: dict, ended: str | None = None) -> list[dict]:
    """The requirements in force as the run's result states them: each relaxation, by whom, on which showing, the run and the
    time of the acceptance that made it, within the order's mandate or beyond it."""
    out = []
    for q in result.get("requirements") or []:
        r = q.get("relaxed")
        if not r or not q.get("metric"):
            continue
        frm, to = level(r["from"]), level(r["to"])
        if frm is None or to is None:
            continue
        entry = {"metric": q["metric"], "what": r["what"], "from": frm, "to": to, "by": dict(r["by"]), "showing": r.get("showing"),
                 "run": run_id, "time": accepted_at(dialogue, r.get("showing")) or ended}
        if r.get("within_mandate") is not None:
            entry["within_mandate"] = r["within_mandate"]
        out.append(entry)
    return out


def approved(order: Order, run: dict, dialogue: dict, features: dict) -> Order:
    """The order version placed, approved: a copy whose `order` section records the plan the run accepted and the requirements
    in force. `run` is the run as the catalogue gives it (its order version and its result), `features` the accepted version's
    feature list as the frame serves it."""
    result = run["result"]
    plan = result["plan"]
    showing = next((q["relaxed"].get("showing") for q in result.get("requirements") or [] if q.get("relaxed")), None)
    out = Order(copy.deepcopy(order.data), validate=False)
    out.instance["accepted"] = {"run": run["id"], "order": dict(run["order"]), "plan": plan["id"], "design": plan["design"],
                                "design_sha256": features["sha256"], "time": accepted_at(dialogue, showing) or run.get("ended")}
    out.instance["in_force"] = in_force(result, run["id"], dialogue, run.get("ended"))
    return out.validate()


def take_features(home, frame, run_id: str, design: str) -> dict:
    """The accepted version's feature list, picture and models from the frame into the products home (`features/<design>/`),
    each file checked against its hash; the list as served."""
    features = frame.features(run_id, design)
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp) / design
        folder.mkdir()
        (folder / "features-1.json").write_text(json.dumps(features, indent=1, ensure_ascii=False), encoding="utf-8")
        for f in [features["picture"]] + features["models"]:
            data, _ = frame.file(run_id, design, f["file"])
            (folder / f["file"]).write_bytes(data)
        home.add_features(folder)
    return features


class NotAtStep(HomeError):
    """An approval asked where the order's step is not accepted."""


def approve(home, reading, lineage: str):
    """The order approved for manufacturing at its step *Accepted*: the run's dialogue read, the accepted version's feature list
    taken into the home, and the version placed saved again as a new revision with the plan and the requirements in force, the
    dialogue kept beside it. Returns what the home saved and the run as the catalogue gives it. The frame is not told."""
    from .check import check
    from .steps import steps
    home._require_writable(lineage)
    order = home.working(lineage)
    previous = home.load(lineage) if (home._folder(lineage) / "order.json").exists() else None
    refusals = check(order, features=home.features(order.type["design"]) if order.type.get("design") else None, previous=previous)
    error = reading.read_catalogue() or reading.read_presence()
    if error is not None:
        raise error
    st = steps(home, lineage, refusals, reading)
    if st.reached != "accepted":
        raise NotAtStep(f"the order's step is {st.label.lower()}, not accepted")
    run = next(r for r in reading.catalogue["runs"] if r["id"] == st.run["id"])
    dialogue = reading.frame.dialogue(run["id"])
    features = take_features(home, reading.frame, run["id"], run["result"]["plan"]["design"])
    placed = home.load(f"{lineage}@{run['order']['revision']}")
    placed = placed if placed.form == 2 else Order.from_v1(placed.raw)
    return home.approve(approved(placed, run, dialogue, features), dialogue, run["id"]), run
