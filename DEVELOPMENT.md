# Development

What the order tool is to become, and in what order. The tool as it stands is described in `README.md`; the as-is data model
across this repository and am-llm, and its measure against the ARTI cube, is `../am-llm/probes/data-model-review.md`. This
document is the level above both: what the tool is for, the shape it takes, what is settled, what is open, and the builds.

## 1. What the tool is for

The tool is the person's console against am-llm: everything a person does to the organisation and everything they are shown of
it. The order is its core. A person specifies a product and places the order; am-llm's requester takes it and the organisation
below prepares the product; the person decides what only the owner of a requirement may decide, and in the end approves a
product for manufacturing, bound to a version. The tool must work seamlessly against am-llm, be intuitive for a
person who writes no code, implement the established methods (Pahl & Beitz, Ulrich & Eppinger, ISO/IEC/IEEE 29148) and carry
Johansson's backtracking from a metric to the needs it serves. The mandate and the traceability are central: what the organisation
may decide on its own, and where every value came from.

Its other side is the overview: the organisation at work, for the person as system operator and for a demonstration or a
conference, what the organisation does with an order, as it happens or played back.

## 2. Three views, three authorities

The person at the tool acts in one of three capacities, and the view says which.

- **The overview.** The person is the *system operator*: they see the resources and the decision makers over them, their state, and
  the traffic between them, and they may place or remove a decision maker. This is ARTI's super user with rights over assets.
  Nothing done here is an act on an order.
- **The order view.** The person is the *orderer*: the owner of the product's requirements, the decision maker over the order
  instance, who gives the mandate, answers the requester, consents to a relaxation and approves. Entering it is a visible change of
  capacity ("as orderer of order X"), and leaving it is the way back.
- **The role view.** The person is an *operator* in am-llm's sense: they fill a role (design engineer, process planner, machine
  operator) in place of an agent, placed there by the system operator as the role's decision maker, and act through the role's
  tools as forms, validated by the frame as an agent's calls are. It is a later build; until it exists am-llm's interactive console
  stays, and its command line (`inbox|act|ack ROLE`) serves experiments (decided 2026-11-08).

The tool's interaction log records the capacity with every act. In am-llm's words the orderer is the requirement's owner and
the operator a person filling a role, and the tool keeps both meanings.

## 3. The overview

The overview is the ARTI cube on the screen: the resource instances present now, and over each role the decision maker that fills
it. It is one picture with two uses, the system operator's console and the demonstration.

- **A cell shows what it holds, the mark who decides over it.** The beings exist whether or not a decision maker stands over them,
  and the frame produces within itself with its beings; the decision makers come to it from outside (ARTI, and the paper's A1
  figure). Each role's cell is drawn as a being-box holding what it has at the clock's time: the order with its metrics and
  mandates and what waits for the owner; the design version in force with its picture and the means it was made by; the plan in
  force or the latest candidate with its settings and verdict; the jobs; the machines; the measurements and capability entries;
  "none yet" for what it does not have. The decision maker is a mark joined above the box (a rounded badge): who it is and its
  state (awake with what it does, waiting, asleep, not woken in this run, down), dimmed and dashed where nobody decides, the cell
  then saying that the frame stops there when a decision is needed. The empty state and a run are the same drawing.
- **The end is announced and the result shown.** When a followed run ends or parks, the player says so where the clock is and the
  clock stops; a result card stands beside the picture once the clock reaches the end: the outcome in words, for an accepted run
  the plan's figures with its design version's picture and every relaxation by whom and on which showing, for a parked run what
  waits for whom, for a declined or referred run the reason. The card is the run's `result` as the frame serves it (`runs-1`,
  `events-1`), computed once by the frame from the run's measures; the tool computes none.

- **The frame stands before the order.** am-llm is started empty: the frame comes up with its roles and their decision makers,
  announces itself, and waits. A placed order in the products home is what it reacts to: it makes a run for that order version,
  translates the order into the brief and the reservation through the adapter, prepares, writes the order its outcome, and waits
  again. The experiment runner becomes the special case of a frame started with a scenario instead of an order. Today it is the
  other way round, the runner makes the frame per run, which is why no run reads an order.
- **The frame serves, the tool reads.** The tool and am-llm need share no folder: the tool may run on a person's Windows laptop
  and the frame on a Linux machine in the workshop. The standing frame serves every contract over HTTP as JSON documents by hash,
  with a personal bearer token (as Inferno's), and its root is a help page that says what the frame is, how to obtain a token
  (contact Joakim Storck, joc@du.se) and how to connect the tool; the tool points at it with `--frame URL` and a token file, the
  same locally against `127.0.0.1` as across the network, one client and no second path. Decided 2026-11-08
  (`../am-llm/LLM-hierarchy-AM-design-document.md` 2.6).
- **Presence.** Each part of the system announces itself through the frame (who, what kind, since when, latest sign of life,
  declared state); an empty frame has no record to be read from, so presence is the frame's own endpoint (`presence-1.json`).
  Three states are kept apart: *left*, with a farewell; *down*, inferred by the reader from a sign of life older than the limit the
  frame states, measured on the frame's clock and not the reader's, because nobody writes "I am crashing"; *unavailable*, declared
  by the part itself. The organisation under a present requester being down is a state of the system, not a configuration of its own:
  the tool runs either alone or with am-llm.
- **The empty state** is the overview's first picture: the frame up since a time, the roles with their decision makers, no order
  in preparation, the placed orders waiting. A demonstration starts there, and moves when the orderer places an order.
- **Decision makers.** Each role's cell says who fills it: a model by name, the scripted policy, a person, or none (the case stops
  at the frame when a decision is needed). The alternatives that are present are selectable by the system operator; a change is
  logged with the weight of a relaxation and takes effect at the role's next waking, so that the beings are never touched.
- **The clock.** The picture shows exactly the state of the run at the time the clock stands on; nothing is compressed. Playback
  is the clock set to the run's start at a chosen speed; live is the clock at now, speed one. One reading serves both, since the
  record has a time on every row and is read while it is written.
- **The time axis** runs from the run's start to the last time the log knows, every event a mark, decisions larger, the clock's
  position on it, and "next in …" beside it. In playback the axis is there from the start; live it grows, and nothing is known
  beyond now. Jumps (next event, next decision, a click on the axis) move the clock without bending it.
- **The activity lines**, one per role parallel to the axis, show what happens between the events: each waking as a bar, within
  it the model's turns (thinking in one colour on every line, then the calls it chose: reading, analysing, reshaping or planning,
  from the record's turns and tool calls per waking), and on it every word the role said. The cell says the same in words at
  the clock's time. The lines are what makes a long silence legible: who is working, on what, and who is waiting.
- **The turns** are the third step beside events and decisions: a step lands where a turn ends, which is when the record writes
  it and the model's choice is known. The panel beside the block diagram shows the awake role's waking: what woke it, each
  ended turn with the model's own summary of its thinking and the calls it made (a click puts the clock there), and where it
  stands now (thinking for so long, the tools answering, or nothing written yet). The summary is the model's summary, not its
  thinking, and the panel says what a call was about, not its result; the result is a level deeper and am-llm's console's.
- **The page fills the window.** The title and the player (with the legend) at the top, the time picture a strip pinned to the
  bottom as high as it needs (18 px a role), and between them the organisation in the left two thirds, scaled to its area and
  never scrolled, and the right third stacking the result card or the awake role's turns, the design, what happened last and the
  facts, scrolled inside; under 1200 px wide the right third goes below.
- **The catalogue** lists the recorded runs by product, experiment and condition (negotiation, decision makers, when, how long,
  outcome). It reads the folders am-llm leaves today; with the frame it reads the frame's runs (`runs-1.json`) and their events (`events-1.json`),
  and shows running runs beside finished ones.
- **The events** are the run as the frame serves it: one list in the order the frame wrote them, each with its time and a sequence
  number, fetched after the last number read, so that a row written late (a turn written as it ends, a call as it answers) is
  never missed. Nothing in the list changes once served: a waking's end, a call's answer and a case's new state are events of
  their own. Playback reads the list from the start, live follows it; the clock's now is the frame's.

## 4. The order view

The order is the activity instance of a product type, and the tool keeps the two apart.

- **The type** is the product's requirements as the person writes them: objects, needs, metrics with ideal and limit, the bindings
  to a design's features. One requirement, many attachments: the metric is the canonical requirement and everything else cites it.
- **The instance** is the order: quantity, objective, the mandate per metric (an interval the organisation may decide within
  without asking), the owner's answering policy (now, later, never), the dialogue so far, the requirements in force (the type's
  values with each relaxation made within the mandate, by whom and on which showing), the accepted plan.
- **The flow.** The person places the order, a state of the order beside draft, checked, bound and confirmed; the tool never
  starts a run, the standing frame does, one run per order version, and the order carries the pointer to it. The requester
  translates the order downward into the brief and the organisation prepares. A question the mandate does not cover parks the case at the frame until the owner answers in the
  order view; a change of the order (a relaxation, a design change) is the answer and preparation resumes. Success is a product
  approved for manufacturing, bound to a version hash. A later change reopens preparation on a new version.
- **A run deleted and its version placed again.** The frame prepares one run per order version, so the same version is placed
  again only once its run is gone: the orderer deletes a run of the product's orders from the order's page (`DELETE /runs/<id>`
  at the frame, confirmed first, logged as the orderer's act), its record and the order version placed go, and the version may be
  placed again. The frame deletes only orders' runs (403 for an experiment's) and not one it is preparing (409), in its words;
  stopping a run being prepared is a later step. Decided 2026-11-08 from the author's demonstration; the tool's side built,
  the frame's to build in am-llm.
- **A plan at risk** (R12, decided 2026-11-08) is accepted only by relaxing the margin it exceeds to what the plan reaches, within
  the metric's mandate, recorded as that relaxation. The order view offers no "accept the risk": it shows the findings with their
  values against the margin, and the acceptance names the relaxation it makes. A critical finding is never accepted.
- **The showing's certificate.** A showing that relaxes a requirement carries the secretary's statement of exhausted means, written
  from the record (the versions tried, the means used, the lightest version holding the rest with its figures). The order view
  shows it as one line with its citations, and the owner asks for no other evidence.
- **The dialogue** between the tool and the requester is a contract of its own (`dialogue-1.json`, after order 2): the instance
  log, with the placing, the mandate in force, the questions and answers, the showings with their findings and certificates, the
  relaxations, the consents and the approval. The contracts between the repositories are the order, the feature list, presence,
  the events and the dialogue, every one a schema in `am_order/schemas/`, which am-llm reads through the library and proposes
  changes to (decided 2026-11-08).
- **Backtracking** (Johansson) is computed from the type's citations, never stored: from a metric to the needs, from a finding in
  a run to the requirement it judges to the need that requirement serves.

## 5. Settled and open

Settled in discussion: everything in sections 2 to 4 as direction; English on the screen; the demonstration case is the engine
bracket with the mass demand and its held variant.

Decided 2026-11-08 (the author, from the data model review; written in `../am-llm/LLM-hierarchy-AM-design-document.md` 2.6 and
`../am-llm/TODO.md` 3 B): the type authored inside the ARTI cube, the orderer its requirement part and the design engineer its
design; one requirement, many attachments, where an order exists; two stores, the products home holding what is decided (the orders,
the bindings to the design versions the requester accepted, the accepted plan's metadata, the dialogue's log) and am-llm's record a
run's course; the brief the order's intent (text, objective, quantity), the bounds metrics, relaxation by the metric's mandate, and
what may change said on the objects, each `fixed` or `free`; a metric's value the limit and all the order asks, a margin only where
the order demands a reserve beneath a physical limit (a utilisation), as the adapter already reads it; `held` with the owner's
answering policy deciding between parking the case for the owner and declining on the evidence; this tool the only console toward a
person, am-llm on its own through its command line, its interactive console staying until the role view exists; Apache-2.0 here
and in am-llm, the shim AGPL in its own repository; the tool with a products home of its own, connected to the frame over HTTP
(section 3); every contract's schema here. With them, from stage 1 of am-llm's experiment: R12 and the showing's certificate
(section 4). Open: the source of the L-bracket's margin 0.5 on its toleranced requirements.

## 6. The builds

Done:

1. **The runs pages** (commit 16fd871): the catalogue and the overview as a still picture at a chosen time, read from the record.
2. **The overview playing** (d0dc2cc to 81acac4): the clock in the page, speeds, pause, jumps both ways between events, turns
   and decisions, keyboard; the activity lines with the thinking and the calls; the turns panel; the page filling the window;
   the same page following a running run.
3. **Foundations** (8d296d7 to the commit after 0b5a7bc): the tests on Linux, Windows and macOS with Python 3.12 and 3.13 at
   every push, in `negotiating-manufacturability-console` on GitHub; `logs/` ignored; the version in one place; `Home.derive`
   leaving no half-made product; the writer lock on the home; the tree reading an order once until it changes.

On am-llm's side, done: **the standing frame** (`python -m agents stand`; `../am-llm/probes/frame-build-report.md`, am-llm
037d936 to 7441414): the frame started empty or with a scenario, serving over HTTP with a personal token the help page,
`presence-1`, `runs-1`, a run's `events-1` after a sequence number the record itself keeps (schema version 6), `POST /orders`
with an `order-1` version (stored by the products home's hash, 409 when placed already, 422 with the schema's reasons), the
accepted version's `features-1` with its picture and models, and the picture of every version a run made. The five reference
orders reach their scenarios' outcomes through it, the held one parked for the owner's word. Not served yet: the dialogue,
and the placing of a decision maker (`next` is null, the alternatives the frame's configuration).

Here, done:

11. **The run's page laid out for what it shows** (3f16177; `../am-llm/probes/layout-build-report.md`): the organisation first, in
    the left two thirds at the page's small size; the time strip small and pinned to the bottom, drawn in percent of its width;
    the height shared, the side column scrolling; the same for playback and live.

10. **The overview shows what is** (25765bf and c622ea8; `../am-llm/probes/overview-build-report.md`): the contract of a run's
    `result` in `runs-1` and `events-1`, an example of every outcome; each role's cell a being-box with its beings at the clock and
    the decision maker as a mark joined above it, dimmed where nobody decides, the same drawing for the empty state and a run;
    the end announced where the clock is and the result as one card, in the catalogue's row (the plan's time, material and mass)
    and on the order's page. am-llm serves `result` next.

7. **The tool connected to the frame** (3a13fd5 and b08d587; `../am-llm/probes/frame-client-build-report.md`): one client
   (`am_order.frame`, `--frame URL --token-file FILE`) reading `presence-1`, `runs-1` and `events-1` and validating each as it
   arrives, a refused token said in the frame's words, a frame that does not answer a state of the page, which keeps what it last
   read; the Runs page opening on the frame's presence, the empty state with `down` inferred on the frame's clock, and its
   catalogue beside the folders'; a run read from the frame's events into the same picture the folders give, played back and
   followed after the last number read, its pictures, findings, relaxations, certificate and accepted version through the tool;
   an order's confirmed version placed from its page; `runs`, `runs show` and `place` on the command line. Tried against a frame
   of am-llm standing outside its tree: the plate's order placed, prepared and accepted, read through every page.

Here, in this order:

5. **Order 2**: the type and the instance in the schema, the brief as intent with the objects `fixed` or `free` (`may_change` and
   `may_relax` gone), the mandate per metric, the answering policy, the requirements in force; migration from order 1 with the
   examples re-written; am-llm's adapter follows and the pin moves.
6. **The dialogue contract** (`dialogue-1.json`) over the frame and the order view against it: parking answered, consenting, the
   acceptance of a plan at risk as a relaxation, the certificate, approving, bound to versions; the accepted version's feature
   list, picture and models published into the person's products home.
4. **The web app for a person.** Partial page updates instead of whole-body swaps; confirmations before anything is lost; error
   pages in words, including the workbook import's; the message colour from the outcome, not from a word in the text; one log per
   session with the proposals logged; the word tables (synonyms, kinds, compatibility) as data beside the vocabularies. Taken
   in beside the others where they touch the same pages.
8. **Johansson's layers** as the 1.1 build in am-llm describes them, on the order-2 type.
9. **The role view and the decision makers placed**: a person filling a role, placed by the system operator, with the role's
   tools as forms; the system operator choosing a role's decision maker, taking effect at its next waking (the frame's endpoint
   for it with this build); am-llm's interactive console goes with it.

Each build is written as `probes/<name>-build.md` in am-llm, built, and reported, as the first version was.

## 7. How work is done here

The conventions are am-llm's (`../am-llm/CLAUDE.md`): English in code and documents; no defensive writing; one item per commit;
the tool never imports am-llm and am-llm's runs never import the tool; every contract's schema lives here, and a change to one is
written into both plans before it is built; no JavaScript build, the web app on loopback for one user; the record and the runs
are read directly and read only where no frame serves them; a frame is read over HTTP only (build 7). Nothing in am-llm's working tree is touched
from here.
