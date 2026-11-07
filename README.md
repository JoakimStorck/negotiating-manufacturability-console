# am-order: the order tool

A product's requirements, stated by an established method, checked, and bound to the features of a design.

- **Pahl & Beitz:** the requirements list: demands and wishes under the checklist's headings, each with its source, in a living list whose changes are recorded.
- **Ulrich & Eppinger:** the customer needs with their importance, the metrics with their ideal values, the needs–metrics matrix between them, and in each metric the mandate: the ideal held, an interval to a marginal value, or the metric released.
- **ISO/IEC/IEEE 29148:** each requirement as stated is checked for its qualities, and the list for its completeness against the checklist.

The person is the order's owner: they define the product, state its needs and metrics, and give the requester its mandate. The tool binds each of the product's objects to features of a design version, which gives the chain need → metric → object → feature.

The tool runs on its own. Its contracts with a design system are two versioned JSON schemas, `am_order/schemas/order-1.json` (the order) and `am_order/schemas/features-1.json` (a design version's feature list). It reads no CAD file: a design system writes the feature list, with the version's picture and its model as STL and 3MF beside it, and the tool shows them as they are.

## Install

Python 3.12.

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
```

The web app listens on 127.0.0.1 only and serves one user. Every page is a URL of its own: the products with their groups and filters; a product with its overview picture and its needs; the metrics heading by heading; a metric with its object, value, conditions, needs and mandate; the matrix, edited by its cells; the target specification; the objects with their places; the binding with the design's picture, its model to download and its features; the history and the comparison of two versions or two products. An edit goes to the product's draft and the page comes back with the checks' refusals beside what they concern; Save makes a version when every check passes.

With `--runs DIR`, the folder am-llm writes its runs under, the Runs page catalogues the recorded runs by experiment and condition (product, negotiation, decision makers per role, when, how long, outcome), and a run opens as the overview of the organisation at a time in it: the roles as cells with their decision makers, which is awake and which waits, the traffic between them, the design version at that time with its picture, and the time axis with every event marked and the clock's position on it. The time is chosen with `?at=` in seconds from the run's start, and the page links to the previous and next event, the next decision, the start and the end. The record is read directly and read only; the tool never imports am-llm, and a run that is still being written is read the same way, up to the last row it holds.

The same is available from the command line and from Python:

```bash
am-order --home examples tree --tag "engine bracket"
am-order --home examples show bracket-mass --mandate
am-order --home examples compare bracket-mass@1 bracket-mass
am-order --home examples check bracket-ge
am-order --home examples xlsx export bracket-ge bracket-ge.xlsx
am-order --home examples reqif export bracket-ge bracket-ge.reqif
```

```python
from am_order import Home, check, bind, render, export
home = Home("examples")
order = home.load("bracket-ge")
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

**The order** (`order-1.json`) holds the product (its name, purpose and overview picture), the needs (`N<n>`: text, importance 1–5, primary need), the objects (`O<n>`: the product's features as the owner sees them, each with its kind, count, datum and optionally its place as a box or a cylinder in mm), the metrics (`M<n>`: demand or wish, the checklist's heading, the object, the quantity and unit, the conditions it is measured under, the ideal value, the needs it measures, its sources, how it is verified, the objects that carry it, and the mandate), the headings' statements where nothing applies, the brief, and the bindings to a design version's features. An id is kept across versions; a need, object or metric is dropped by marking it. A load is the condition a metric is measured under (`under`), not a metric.

**The feature list** (`features-1.json`) holds a design version's id, its features (name, kind, axis or normal, centroid, bounding box, labels, declared or recognised, status, its colour in the picture) and the names and hashes of the picture and the model beside it.

The quantities a metric may state, with their units and value forms, are a table in `am_order/vocab/quantities.json`, extensible by a row; the checklist's headings are `am_order/vocab/headings.json`.

## The examples

`examples/` is a products home: the four reference products of am-llm in `own/` under the group `reference cases/H1` (`plate`, `l-bracket`, `bracket-ge`, and `bracket-mass`, whose second version is the held case), and the feature lists of their designs and of four library parts in `features/` (the MFCAD parts with their faces' feature labels among them). am-llm writes them:

```bash
cd ../am-llm
.venv/bin/python -m design features --all --out ../am-order/examples/features
cp -r products/own products/groups.json ../am-order/examples/
```
