# Development

What the order tool is to become, and in what order. The tool as it stands is described in `README.md`; the as-is data model
across this repository and am-llm, and its measure against the ARTI cube, is `../am-llm/probes/data-model-review.md`. This
document is the level above both: what the tool is for, the shape it takes, what is settled, what is open, and the builds.

## 1. What the tool is for

The tool is the orderer's instrument against am-llm. A person specifies a product and places the order; am-llm's requester takes
it and the organisation below prepares the product; the person decides what only the owner of a requirement may decide, and in
the end approves a product for manufacturing, bound to a version. The tool must work seamlessly against am-llm, be intuitive for a
person who writes no code, implement the established methods (Pahl & Beitz, Ulrich & Eppinger, ISO/IEC/IEEE 29148) and carry
Johansson's backtracking from a metric to the needs it serves. The mandate and the traceability are central: what the organisation
may decide on its own, and where every value came from.

Its second use is to show the system: at a demonstration or a conference, what the organisation does with an order, as it happens
or played back.

## 2. Two views, two authorities

The person at the tool acts in two capacities, and the view says which.

- **The overview.** The person is the *system operator*: they see the resources and the decision makers over them, their state, and
  the traffic between them, and they may place or remove a decision maker. This is ARTI's super user with rights over assets.
  Nothing done here is an act on an order.
- **The order view.** The person is the *orderer*: the owner of the product's requirements, the decision maker over the order
  instance, who gives the mandate, answers the requester, consents to a relaxation and approves. Entering it is a visible change of
  capacity ("as orderer of order X"), and leaving it is the way back.

The tool's interaction log records the capacity with every act. In am-llm's words the orderer is the requirement's owner;
"operator" there means a person filling a role in place of an agent, and the tool keeps that meaning.

## 3. The overview

The overview is the ARTI cube on the screen: the resource instances present now, and over each role the decision maker that fills
it. It is one picture with two uses, the system operator's console and the demonstration.

- **The frame stands before the order.** am-llm is started empty: the frame comes up with its roles and their decision makers,
  announces itself, and waits. A placed order in the products home is what it reacts to: it makes a run for that order version,
  translates the order into the brief and the reservation through the adapter, prepares, writes the order its outcome, and waits
  again. The experiment runner becomes the special case of a frame started with a scenario instead of an order. Today it is the
  other way round, the runner makes the frame per run, which is why no run reads an order.
- **Presence.** Each part of the system announces itself on the shared surface (who, what kind, since when, latest sign of life,
  declared state); an empty frame has no record to be read from, so presence has a place of its own, as small as a file per part
  that the part writes every few seconds and the tool reads. Three states are kept apart: *left*, with a farewell; *down*,
  inferred by the reader from a sign of life older than a limit, because nobody writes "I am crashing"; *unavailable*, declared by
  the part itself. The organisation under a present requester being down is a state of the system, not a configuration of its own:
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
- **The catalogue** lists the recorded runs by product, experiment and condition (negotiation, decision makers, when, how long,
  outcome). It reads the folders am-llm leaves today; when the requester stands and registers runs on the shared surface, it
  becomes a view of that contract and shows running runs beside finished ones.

## 4. The order view

The order is the activity instance of a product type, and the tool keeps the two apart.

- **The type** is the product's requirements as the person writes them: objects, needs, metrics with ideal and limit, the bindings
  to a design's features. One requirement, many attachments: the metric is the canonical requirement and everything else cites it.
- **The instance** is the order: quantity, objective, the mandate per metric (an interval the organisation may decide within
  without asking), the owner's answering policy (now, later, never), the dialogue so far, the accepted plan.
- **The flow.** The person places the order, a state of the order beside draft, checked, bound and confirmed; the tool never
  starts a run, the standing frame does, one run per order version, and the order carries the pointer to it. The requester
  translates the order downward into the brief and the organisation prepares. A question the mandate does not cover parks the case at the frame until the owner answers in the
  order view; a change of the order (a relaxation, a design change) is the answer and preparation resumes. Success is a product
  approved for manufacturing, bound to a version hash. A later change reopens preparation on a new version.
- **The dialogue** between the tool and the requester is the third contract between the repositories, beside the order and the
  feature list: the instance log, with the placing, the mandate in force, the questions and answers, the consents and the approval.
  Presence is the fourth.
- **Backtracking** (Johansson) is computed from the type's citations, never stored: from a metric to the needs, from a finding in
  a run to the requirement it judges to the need that requirement serves.

## 5. Settled and open

Settled in discussion: everything in sections 2 to 4 as direction; English on the screen; the demonstration case is the engine
bracket with the mass demand and its held variant.

Open, waiting for the author's reading of the data model review: the type authored inside the ARTI cube; one store for type and
instance or two; the order's `brief` section shrinking to the order's intent; where the limit and the at-risk share live; the form of
"held, and a relaxation declines the order"; the console duplication between the repositories; licence; a remote; Python 3.13; the
default home. These decide the order-2 schema and the dialogue contract, and nothing below waits on them except what says so.

## 6. The builds

Done:

1. **The runs pages** (commit 16fd871): the catalogue and the overview as a still picture at a chosen time, read from the record.

Next, independent of the open decisions:

2. **The overview playing.** The clock in the page, speeds, pause, jumps both ways between events, turns and decisions,
   keyboard; the activity lines with the thinking and the calls; the turns panel; the same page following a running run.

On am-llm's side, as soon as the review is read, in parallel with the builds here; it depends on the brief's form and on where the
mandate becomes the reservation, and on nothing else that is open:

- **The standing frame** (`python -m agents stand`, or so): the frame started empty, presence written for itself and its roles
  with their decision makers from the command line, a placed order version taken from the products home and prepared as a run
  under a folder named by the order version, the outcome written back, the experiment runner on the same code. The presence
  contract is the first of the four contracts written, since the empty frame has nothing else to be seen by.

Then, independent of the open decisions:
3. **Foundations.** CI on Linux, Windows and macOS; Python 3.13 in the range and the tests; `logs/` ignored; the version in one
   place; `Home.derive` leaving no half-made product on failure; a writer lock on the home; the tree not reading every order.
4. **The web app for a person.** Partial page updates instead of whole-body swaps; confirmations before anything is lost; error
   pages in words, including the workbook import's; the message colour from the outcome, not from a word in the text; one log per
   session with the proposals logged; the word tables (synonyms, kinds, compatibility) as data beside the vocabularies.

After the decisions:

5. **Order 2.** The type and the instance in the schema, one requirement with many attachments, the mandate per metric, the
   answering policy; migration from order 1 with the examples re-written.
6. **The dialogue contract** and the order view against it: placing, parking, answering, consenting, approving, bound to versions.
7. **Presence and decision makers** in the overview, against what the standing frame publishes: the empty state, the three
   states of a part, the decision makers selectable where the frame reads its setting at the role's next waking.
8. **Johansson's layers** as the 1.1 build in am-llm describes them, on the order-2 type.

Each build is written as `probes/<name>-build.md` in am-llm, built, and reported, as the first version was.

## 7. How work is done here

The conventions are am-llm's (`../am-llm/CLAUDE.md`): English in code and documents; no defensive writing; one item per commit;
the tool never imports am-llm and am-llm's runs never import the tool; no JavaScript build, loopback, one user; the record and the
runs are read directly and read only. Nothing in am-llm's working tree is touched from here.
