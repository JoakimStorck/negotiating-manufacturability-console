# Use cases

The tool as its people use it: who they are, what they come to do, how they reach it today, and how the pages should be arranged so
that the next thing to do is always one click away. Written 2026-11-09, after the frame, order 2 and before the dialogue. It
measures the web app as it stands (am-order `1b40717`) and proposes its navigation, as input to the dialogue's order view
(`dialogue-build.md` part 3) and the web app for a person (build 4).

## 1. The method

A *use case* is one goal of one actor, from the moment the actor sets out to the moment the goal is reached or given up. It names
the trigger, what must hold before, the steps, and the result. A use case is not a page. It crosses pages, and the pages serve
the use cases. The analysis therefore:

1. lists the actors and the capacity each acts in (`DEVELOPMENT.md` 2);
2. lists their goals as use cases, each with its path today (the views, the clicks, what the actor must know or scroll to find);
3. maps the views: for each, the actions it offers and the views one click away;
4. finds where a goal takes more clicks or more knowledge than it should;
5. proposes an arrangement where **the view shows the state of what the actor is working on and its next step as one click**.

The measure used throughout is the number of clicks and of things the actor must remember. A step is one click when its control
is on the screen without scrolling, where the actor already is.

## 2. The actors

| Actor | Capacity | Comes to | Knows |
| --- | --- | --- | --- |
| **The orderer** | owner of a product's requirements; decision maker over the order | state a product by method, give the organisation its mandate, place the order, answer what only the owner may, approve the result | the product and its use; the methods (Pahl & Beitz, Ulrich & Eppinger, 29148) at least by name; not the code. Roger Johansson tests the tool in this capacity |
| **The system operator** | rights over the organisation: the roles and their decision makers, the runs | stand the frame up, set who decides in each role, show the organisation at work, keep the runs in order | the organisation's roles; the models and policies by name |
| **The audience** | none: watches | see what the organisation does with an order, at a demonstration or a conference | nothing beforehand |
| **The researcher** | none over an order; reads | compare runs of an experiment, find a condition's run, play it back | the experiments and their conditions |
| **An operator in a role** (later, the role view) | fills a role in place of an agent | act as the design engineer, the planner, the machine operator | the role's domain |

The author is often all of the first four in one sitting, during a demonstration. That is why the capacity must be visible and the
switch between capacities one click.

## 3. The use cases

The paths are today's. "Clicks" counts from the tool's front page.

### The orderer

| # | Goal | Path today | Clicks | Friction |
| --- | --- | --- | --- | --- |
| O1 | **Start a product**: new, from a design's feature list, or from one that exists | Products: *New product* or *Make a skeleton*; an existing one: select it, then *Derive* in the side panel | 2 | The reference products are read-only. On a product's page nothing says how to get an editable copy: *Derive* is on the products list, in a panel shown only when the product is selected |
| O2 | **State the requirements**: needs, objects, metrics with their conditions, the headings | Product (needs), Objects, Metrics (then each metric's page), Matrix | 1 per tab, 2 per metric | A metric is edited on a page of its own: setting a quantity or a value on fifteen metrics is thirty clicks. The checks' refusals are beside what they concern ✓ |
| O3 | **Bind to a design and confirm** | Binding: choose the design, *Bind*, then *Confirm* per object | 2 + 1 per object | Nothing on the product page says that binding and confirming are what stand between the order and placing it, until the placing section says "not confirmed", without a link |
| O4 | **State this order**: brief, quantity, objective, answering policy, a mandate per metric, which objects are free | Product (*This order*), each metric's page (mandate), Objects (fixed or free) | 1 + 2 per metric + 1 | The order's own fields are on three pages. Giving M6–M9 an interval is four metric pages, and the order is never seen whole |
| O5 | **Save a version** | the *Checks* panel's *Save*, on every product page | 1 | Good: always on the screen, with the refusals |
| O6 | **Place the order**, knowing who will take it | Product, scroll to *At the frame* (below the needs), *Place revision n* | 2 + scroll | The section is at the bottom of the longest page. A product's state at the frame (placed, being prepared, parked, accepted) is not in the header, where its draft/bound/confirmed state is |
| O7 | **Follow the order's run** | *At the frame*: the run's link, then *follow now* | 3 + scroll | From the run's page there is no link back to the order: its facts name `bracket-ge@1` as text |
| O8 | **Give the word on a parked run** (the dialogue's build) | not possible | — | The run parks, says so, and stops. The run's page cannot say where to answer |
| O9 | **Read the result, approve it** (the dialogue's build) | the result card on the order's page and the run's page ✓; approval not possible | — | — |
| O10 | **Change and place again**: a new revision, or the same version after deleting its run | edit, *Save*, *Place*; or *Delete* beside the run, then *Place* | 2–3 | Good once known. A placed and running order can still be edited and saved without a word that this makes a new version not yet placed |
| O11 | **Export, compare, look back**: workbook, ReqIF, history, two versions | Tables (exports), History, Compare (header) | 1–2 | *Compare* in the header compares any two products; for one product's versions it is History. Two ways to one goal |

### The system operator

| # | Goal | Path today | Clicks | Friction |
| --- | --- | --- | --- | --- |
| S1 | **See the organisation now**: the frame up, the roles and who decides, the machines, what waits | Runs: *The standing frame* at the top | 1 | The organisation now, the frame's runs and the recorded experiments are one long page. The overview of the organisation is not a place of its own in the header |
| S2 | **Set who decides** before an order is placed | Runs: click a role's mark, choose | 3 | Good. The marks' being clickable is said in one line on the Runs page, and not on a run's page |
| S3 | **Show a run**: live, or played back at a demonstration | Runs: the run's link; *play* or *follow now* | 2 | Good. The run's page is the demonstration's page |
| S4 | **Keep the runs in order**: delete or withdraw an order's run | the product's page, *At the frame*, *Delete* | 3 + scroll | Deleting is reached through the product only. That is right for the orderer, but the system operator who sees a run stuck in the overview must find its product first |

### The audience and the researcher

| # | Goal | Path today | Clicks | Friction |
| --- | --- | --- | --- | --- |
| A1 | **Watch what the organisation does with an order** | the run's page, put up by the presenter | — | Good since the layout build. The audience sees what the presenter's window shows |
| R1 | **Find and play back an experiment's run** | Runs: the experiment, the condition, the run | 3 | Good. The filter by product exists |
| R2 | **Compare two runs** of an experiment | not possible in the tool | — | One run's page at a time |

## 4. The views

| View | Capacity | What it offers | One click away | Missing one click away |
| --- | --- | --- | --- | --- |
| Products (`/`) | orderer | the tree, filters, new product, skeleton, groups; a selected product's derive, move, tag, archive | a product, Compare, Runs | — |
| A product's tabs (Product, Objects, Metrics, Matrix, Specification, Binding, Tables, History) | orderer | each part of the type; Product holds *This order* and *At the frame* | the other tabs, Save and Discard, Compare, Runs | the order as a whole (O4); the next step towards placing (O3, O6); an editable copy of a read-only product (O1) |
| A metric | orderer | the metric whole, its mandate | the product's tabs | the previous and next metric |
| Runs (`/runs`) | system operator, researcher | the frame's empty state, its runs, the recorded experiments | a run, a mark's selector | a run's order (S4) |
| A run (`/runs/…`, `/frame/runs/…`) | system operator, audience, researcher | the organisation at the clock's time, the player, the turns or the result | the Runs page, a mark's selector | the run's order (O7); where to answer a parked run (O8); deleting it (S4) |

The header offers *am-order* (products), *Compare* and *Runs*, and a product's tabs where one is open. It does not offer the
organisation now as a place of its own, or say which capacity the page is in.

## 5. What the analysis finds

1. **The order has no place of its own.** The order's fields, its state at the frame and its next step are spread over the
   product page (low on it), the metric pages and the objects page. The orderer's main goals (O4, O6, O7, O8, O9) all cross them.
2. **The state is not shown where the actor is.** The header shows draft, bound or confirmed. It does not show placed, being
   prepared, parked, accepted or approved, and it does not show what to do next.
3. **The links run one way.** From the order to its run, but not back; from the overview to a run, but not to its order.
4. **The capacity is implicit.** Only the decision-maker selector says "as system operator". The orderer's acts are not marked as
   such, and nothing says when a page changes capacity.
5. **Per-item pages for table work.** A metric's mandate, value or quantity set one page at a time, where the work is a column.
6. **Read-only without a way out.** A reference product says "read only" and nothing more where it is shown.

## 6. The proposal

**Three places in the header, one per capacity, always shown, the current one marked:**

- **Products**: the orderer's. The products, and in a product its type (the tabs as now) and its order.
- **Frame**: the system operator's. The organisation now (the empty state, the decision makers by their marks), the frame's runs,
  and a run's page. Deleting an order's run is here too, beside the run, since the system operator keeps the runs in order.
- **Experiments**: the researcher's. The recorded runs by experiment and condition, as the folders hold them.

A run's page is reached from the Frame and from the order, and says which order it is with a link.

**An order view: the order whole, with its state as a line of steps** (a new tab, *Order*, first after Product):

```
 Stated  →  Checked  →  Bound  →  Confirmed  →  Placed  →  Being prepared  →  [Your word]  →  Accepted  →  Approved
                                       ▲ you are here                                                         
 Next: confirm the binding of 3 objects   [Go to the binding]
```

- Every step done is a link to where it was done. The current step names what is next as **one button**: "Confirm 3 bindings",
  "Place revision 3", "Follow the run", "Give your word: a showing waits since 07:14", "Approve for manufacturing".
- Under the line, the order whole: the brief, the answering policy, every metric with its value and its mandate in one table
  (edited in the table, not page by page), the objects fixed or free, who will take it at the frame, its runs with their results.
- A word on a parked run (the dialogue) is given here, as "orderer of `bracket-ge@3`".
- The header's state badge becomes this line's current step.

**Links both ways and the capacity said:**
- A run's facts link to its order, and a parked run says "Your word is given on the order", one click.
- The order links to its run.
- The selector says "as system operator", and the order view says "as orderer of …". Moving from one to the other is a link that
  says so.

**One click out of read-only:** a reference product shows, beside "read only", **Make an editable copy** (derive into user, the
id proposed, one confirmation).

**Table work in tables:** the metrics' tab and the order view edit a column (quantity, value, mandate) in place, a row at a time,
with the checks beside the row; the metric's own page stays for the whole of one metric. The metric's page gets the previous and
next metric.

**What stays:** the *Checks* panel with *Save* on every product page; the run's page as it is laid out; the marks' selector.

## 7. Where it goes

- **The dialogue (`dialogue-build.md` part 3)** builds its owner's word into the order view's line of steps (the step *Your word*)
  rather than at the bottom of the product page. It needs the order view first, or builds it as its first item.
- **The web app for a person (build 4)** takes the rest:
  - the three places in the header;
  - the links both ways;
  - the capacity said;
  - the editable copy;
  - the table work.
- **A check with the people it is for.** A short session with Roger Johansson, in which he states a product and places it with
  the tool while saying aloud what he looks for (a *think-aloud* test, about an hour), will show what this analysis cannot. It
  should be done once the order view stands, and its findings written here.

## 8. Open

- Whether the order view is the product's first tab or a page of its own beside the product. It is proposed as a tab, since an
  order is always a product's.
- Whether Experiments stays in the tool or goes with am-llm's own console when the role view comes.
- R2, comparing two runs, is not proposed: it is the paper's work, not the tool's.
