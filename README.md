# am-order: the person's console

The person's side of a negotiating organisation, in two capacities. As the orderer: a product's requirements, stated by an
established method, checked, and bound to the features of a design, placed as an order with its mandate. As the system
operator: the overview of the organisation at work, the roles and their decision makers, what is awake and what waits, live
or played back from the record, down to the model's turns.

- **Pahl & Beitz:** the requirements list: demands and wishes under the checklist's headings, each with its source, in a living list whose changes are recorded.
- **Ulrich & Eppinger:** the customer needs with their importance, the metrics with their ideal values, the needs–metrics matrix between them, and, per order, the mandate on each metric: the ideal held, an interval to a marginal value, or the metric released.
- **ISO/IEC/IEEE 29148:** each requirement as stated is checked for its qualities, and the list for its completeness against the checklist.

The person is the order's owner: they define the product, state its needs and metrics and which of its objects the design may change, and, for each order of it, give the requester its mandate and say what happens to a case the mandates do not cover. The tool binds each of the product's objects to features of a design version, which gives the chain need → metric → object → feature.

The tool runs on its own. Its contracts with a design system are two versioned JSON schemas, `am_order/schemas/order-2.json` (the order; `order-1.json` for the versions saved before it) and `am_order/schemas/features-1.json` (a design version's feature list). Its contracts with am-llm's standing frame, sketched before the frame is built, are `am_order/schemas/presence-1.json` (who is up, since when, what waits), `am_order/schemas/runs-1.json` (the frame's catalogue of runs) and `am_order/schemas/events-1.json` (a run's events by sequence number). It reads no CAD file: a design system writes the feature list, with the version's picture and its model as STL and 3MF beside it, and the tool shows them as they are.

## Install

Python 3.12 or 3.13.

```bash
python3.12 -m venv .venv
.venv/bin/pip install -e '.[test]'
.venv/bin/python -m pytest
```

## Start

```bash
.venv/bin/am-order --home examples serve            # http://127.0.0.1:8770/
.venv/bin/am-order --home examples serve --log logs # with the interaction log, one JSON line per action
.venv/bin/am-order --home examples serve --runs ../am-llm/runs/experiments   # with am-llm's recorded runs to look at
.venv/bin/am-order --home examples serve --host 0.0.0.0   # reached from other computers on the network, at this machine's address
```

The web app listens on 127.0.0.1, this machine only, unless `--host` says otherwise: `--host 0.0.0.0` serves it on every network interface, so that another computer reaches it at `http://<this machine's address>:8770/` (the command prints the addresses; a firewall may have to let the port through). It has no login: whoever reaches it can edit the products home and, with `--frame`, act at the frame with the tool's token, so serve it on the network only where that is meant. Many people may use it at once; the interaction log keeps one session for them all. Every page is a URL of its own: the products with their groups and filters; a product with its overview picture, its needs and this order (the brief, the answering policy, the requirements in force and the accepted plan, none until the frame accepts a plan); the metrics heading by heading; a metric with its object, value, conditions and needs, and below them this order's mandate on it; the matrix, edited by its cells; the target specification; the objects with their places, each fixed or free; the binding with the design's picture, its model to download and its features; the history and the comparison of two versions or two products. An edit goes to the product's draft and the page comes back with the checks' refusals beside what they concern; Save makes a version when every check passes.

With `--runs DIR`, the folder am-llm writes its runs under, the Runs page catalogues the recorded runs by experiment and condition (product, negotiation, decision makers per role, when, how long, outcome), and a run opens as the overview of the organisation at a time in it, laid out to fill the window: the organisation in the left two thirds, the result card or the awake role's turns with the design and what happened last in the right third, and the time picture a low strip along the bottom (under 1200 px wide the right third goes below): the roles as cells with their decision makers, which is awake and which waits, the traffic between them, the design version at that time with its picture, and the time axis with every event marked and the clock's position on it. The time is chosen with `?at=` in seconds from the run's start, and the page links to the previous and next event, the next decision, the start and the end. The record is read directly and read only; the tool never imports am-llm, and a run that is still being written is read the same way, up to the last row it holds.

### Connected to a standing frame

am-llm can stand as a frame (`python -m agents stand`): its roles with their decision makers up and waiting, serving its contracts over HTTP with a personal token. The tool connects to it with its URL and a token file, the same on the frame's own machine as across the network:

```bash
am-order --home examples --frame http://127.0.0.1:8780 --token-file ~/.config/am-order/frame-token serve
am-order --frame URL --token-file FILE runs                      # the frame's runs
am-order --frame URL --token-file FILE runs show RUN --at 300    # a run's state 300 s after its start
am-order --home examples --frame URL --token-file FILE place bracket-mass   # the order's saved version placed at the frame
```

The token file holds one line `NAME=TOKEN` (or the token alone); without `--token-file` the token is read from `AM_FRAME_TOKEN`. It is sent as a bearer token and never logged or shown. How to obtain one is on the frame's help page, its URL in a browser.

Connected, the Runs page opens on the frame as it stands, refreshed every few seconds: the frame and since when it is up; each role's cell drawn as a box holding what it has (none yet, in the empty state), with the decision maker over it as a rounded mark above the box, dimmed where nobody decides; each part's state (present, unavailable with why, left, or down when its latest sign of life is older than the frame's limit, measured on the frame's clock), the machines, and the orders placed, being prepared and parked, with what waits for whom. A role's mark opens a selector of the decision makers the frame offers: set them there, as system operator, before an order is placed; a change during a run takes effect at the role's next waking, shown at the mark until then (`am-order --frame URL --token-file FILE runs set ROLE=MAKER` does the same). Below it the frame's runs, each linking to its order in the products home where the tool holds that version, beside the folders' runs. A run from the frame opens as the same overview a folder's run gives, played back from its start or followed live; it also shows what the frame's events carry beyond the folder's tables: a showing's findings and its certificate of exhausted means, the relaxations an acceptance makes ("the margin on M8 relaxed from 0.6 to 0.838 within its mandate"), the accepted version's feature list with its picture and models, and a case parked for the owner's word. A run's cells hold what the run had at the clock's time (the order with its metrics and mandates, the design version in force with its picture, the plan in force or the latest candidate with its settings and verdict, the jobs, the machines), the marks above them who decides and what they do. When the clock reaches the end, the player says that the run has ended and a result card shows what it came to: for an accepted run the plan's settings, print time, material and printed mass with its design version's picture, and every requirement relaxed in words ("the margin on M8 relaxed from 0.6 to 0.838 by the requester, within its mandate, on the showing of …"); for a parked run what waits for whom; for a declined or referred run the reason. The catalogue's row shows the plan's time, material and mass, and the order's page the card of its latest run.

An order's page has a section *At the frame*: a confirmed order's saved version, in the form of order 2, is placed there with one button, exactly as the home holds it, and the section lists the runs of the product's versions with their states. A run that is not being prepared can be deleted there (confirmed first): its record goes at the frame, and its version may be placed again. On the command line: `am-order --frame URL --token-file FILE runs delete RUN`. The frame makes the run; the tool starts nothing and writes nothing at the frame but the order placed. A frame that does not answer is said on the page, which keeps what it last read; a token it refuses, or a document out of its schema's form, is said in the frame's words.

The same is available from the command line and from Python:

```bash
am-order --home examples tree --tag "engine bracket"
am-order --home examples show bracket-mass --mandate
am-order --home examples compare bracket-mass@1 bracket-mass
am-order --home examples check bracket-ge
am-order --home examples --allow-own migrate bracket-ge@1 --free O6 --free O7 --free O9 --save   # an order-1 version as order 2
am-order --home examples xlsx export bracket-ge bracket-ge.xlsx
am-order --home examples reqif export bracket-ge bracket-ge.reqif
```

```python
from am_order import Home, check, bind, render, export
home = Home("examples")
order = home.load("bracket-ge")
print(order.mandate("M13"), order.answering(), [o["name"] for o in order.free()])
print(render(order, "markdown", ["matrix", "traceability"]))
```

The full list of commands is `am-order --help`; each one calls the Python API (`am_order`).

## The products home

A folder, given by `--home` or `AM_ORDER_HOME`:

| Path | Content |
| --- | --- |
| `groups.json` | the tree of groups the owner names and arranges; every product stands in one |
| `own/<lineage>/` | the project's products, read only unless `--allow-own` is given |
| `user/<lineage>/` | products a person defines or derives |
| `archive/<lineage>/` | archived products; a product is archived, never deleted |
| `<category>/<lineage>/order.json` | the order as it stands |
| `<category>/<lineage>/versions/<sha256>.json` | every saved version, by its hash |
| `<category>/<lineage>/changes.md` | the change record: per version, what changed |
| `<category>/<lineage>/draft.json` | the draft a refused save keeps |
| `<category>/<lineage>/pictures/` | the owner's overview pictures (PNG or JPEG), stored as they came |
| `features/<design id>/` | a design version's `features-1.json`, `picture.png`, `model.stl` and `model.3mf` |

A save is atomic: the version is written whole under its hash, then `order.json` is replaced, so another program reading the home takes the version as it stands. A save that changes nothing makes no version, and a save is refused while a check fails.

## The schemas

**The order** (`order-2.json`) is one document per order version in two sections. `type` is the product's requirements, the activity type's product side, the same for every order of the product: the product (its name, purpose and overview picture), the design version it is bound to, the needs (`N<n>`: text, importance 1–5, primary need), the objects (`O<n>`: the product's features as the owner sees them, each with its kind, count, datum, optionally its place as a box or a cylinder in mm, and its change: `fixed`, an interface the design keeps, or `free`, the design may change around it; the part free is its shape free), the metrics (`M<n>`: demand or wish, the checklist's heading, the object, the quantity and unit, the conditions it is measured under, the ideal value, the needs it measures, its sources, how it is verified, the objects that carry it), the headings' statements where nothing applies, and the bindings to a design version's features. `order` is this order, the activity instance: the brief (its text, objective and quantity: the order's intent), the mandates by metric id (`held`, an interval to a far end or `as_needed`, `release`; a metric without one is held), the answering policy (`park`: a case the mandates do not cover parks at the frame for the owner's word; `decline`: the requester declines on the evidence of exhausted means), the requirements in force (each relaxation made within a mandate in a run: the metric, margin or value, from, to, by whom, on which showing, the run and the time) and the accepted plan (the run, the plan, the design version and its hash); the last two are written by the dialogue and empty until then. A new order of the same product is a new version that changes only `order`. An id is kept across versions; a need, object or metric is dropped by marking it. A load is the condition a metric is measured under (`under`), not a metric.

A version saved as order 1 (`order-1.json`, the mandate in each metric and the brief's `may_change` and `may_relax`) stays as it is, named by its hash, and reads in its order-2 form; an edit starts from that form and every save writes order 2. `am-order migrate PRODUCT[@REVISION]` (or `--all`) writes the migrated draft and prints what order 2 says elsewhere: the mandates go to the order, the brief's text, objective and quantity to its brief, the answering policy is `park`, every object is `fixed` but the part where `may_change` named `shape`; `may_relax` goes where its metrics have mandates, and `may_change`'s design parameters and `material` are noted for the owner to state on the objects (`--free OBJECT`) and the material's mandate, since which objects a parameter moves is the design's knowledge. `--save` saves the draft as a new revision.

**The feature list** (`features-1.json`) holds a design version's id, its features (name, kind, axis or normal, centroid, bounding box, labels, declared or recognised, status, its colour in the picture) and the names and hashes of the picture and the model beside it.

**The frame's presence** (`presence-1.json`, a sketch) holds the frame's clock and its limit for a part's silence, the parts (the roles with the decision maker over each, the one chosen for the next waking, the alternatives, what is awake and what waits; the machines with their class and job), each with when it came, its latest sign of life and the state it declares (`present`, `unavailable`, `left`; `down` is the reader's inference), and the runs the frame holds with their order version and state.

**The frame's runs** (`runs-1.json`, a sketch) is the catalogue: every run the frame holds, from an order version or a scenario, with its settings, the decision maker that filled each role, its status (`running`, `parked`, `done`), times and outcome, the last sequence number of its events, and, once it has ended or parked, its `result`: the outcome with its reason; for an accepted run the plan (design version, orientation, settings with their units, print time, material, printed mass, verdict, findings) and the requirements as finally stated with every relaxation, by whom and on which showing; for a parked run what waits for whom; for a declined or referred run the last showing. The frame computes it once from the run's measures and never changes it; `events-1`'s run carries the same.

**A run's events** (`events-1.json`, a sketch) holds the run (its order version or scenario, settings, status, outcome) and its events after a sequence number in the order the frame wrote them: wakings, turns, calls, the protocol's messages, the dialogue's words (a showing with its findings and certificate, an acceptance with the relaxations it makes), designs, plans with their verdicts, the case's state, jobs and the end.

The quantities a metric may state, with their units and value forms, are a table in `am_order/vocab/quantities.json`, extensible by a row; the checklist's headings are `am_order/vocab/headings.json`.

## The examples

`examples/` is a products home: the four reference products of am-llm in `own/` under the group `reference cases/H1` (`plate`, `l-bracket`, `bracket-ge`, and `bracket-mass`, whose held case declines on the evidence), each saved first as order 1 and then as order 2 (`plate`, `l-bracket` and `bracket-ge` revision 2; `bracket-mass` revision 3 the mass case and 4 the held case, from its order-1 revisions 1 and 2), and the feature lists of their designs and of four library parts in `features/` (the MFCAD parts with their faces' feature labels among them). am-llm writes them:

```bash
cd ../am-llm
.venv/bin/python -m design features --all --out ../am-order/examples/features
cp -r products/own products/groups.json ../am-order/examples/
```

## Licence

Copyright 2026 Joakim Storck. Licensed under the Apache License, Version 2.0 (`LICENSE`). The vendored web libraries keep their own licences beside them (`am_order/web/static/`).
