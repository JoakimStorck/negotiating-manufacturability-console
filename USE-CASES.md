# Use cases

The tool as its people use it: who they are, what they come to do, how they reach it today, and how the pages should be arranged so
that the next thing to do is always one click away. It measures the web app as it stands, the orderer's use cases O4–O10 with
the order view (build 6, the dialogue's part 3) and the rest as before it, and proposes the navigation that remains for the web app
for a person (build 4).

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

The paths are today's. "Clicks" counts from the tool's front page; from a product's page, the order view is one click (the tab
*Order*, or the header's badge of the step reached).

### The orderer

| # | Goal | Path today | Clicks | Friction |
| --- | --- | --- | --- | --- |
| O1 | **Start a product**: new, from a design's feature list, or from one that exists | Products: *New product* or *Make a skeleton*; an existing one: select it, then *Derive* in the side panel | 2 | The reference products are read-only. On a product's page nothing says how to get an editable copy: *Derive* is on the products list, in a panel shown only when the product is selected |
| O2 | **State the requirements**: needs, objects, metrics with their conditions, the headings | Product (needs), Objects, Metrics (then each metric's page), Matrix | 1 per tab, 2 per metric | A metric is edited on a page of its own: setting a quantity or a value on fifteen metrics is thirty clicks. The checks' refusals are beside what they concern ✓ |
| O3 | **Bind to a design and confirm** | Binding: choose the design, *Bind*, then *Confirm* per object | 2 + 1 per object | The order's step says that binding and confirming stand between the order and placing it, as its next button (*Bind to a design*, *Confirm 3 bindings*) to the binding |
| O4 | **State this order**: brief, quantity, objective, answering policy, a mandate per metric, which objects are free | Order: the brief and the answering policy, each metric's mandate and each object's fixed or free in its row, the checks beside the row | 2 + 1 per row | The order is seen whole on one page. Each row is applied by itself: giving M6–M9 an interval is four applies on one page, where a column edited at once is build 4's table work |
| O5 | **Save a version** | the *Checks* panel's *Save*, on every product page; in the order view the step's button *Save revision n* | 1 | Good: always on the screen, with the refusals; the order view's button names the revision it makes |
| O6 | **Place the order**, knowing who will take it | Order: the step's button *Place revision n* at the top; who takes it and the runs under *At the frame* | 3 | The step reached is the header's badge on every product page, *Confirmed* → *Placed* → *Being prepared* and on |
| O7 | **Follow the order's run** | Order: *Follow the run* | 3 | The run's facts link its order version back to the order view ✓ |
| O8 | **Give the word on a parked run** | Order (the badge says *Your word*): the showing in words, *Accept* (R12's margins prefilled), *Refuse* with conditions or holds, or *Decline* with the reason; confirmed | 4 (from a parked run's page: 3) | A parked run's page says "Your word is given on the order", one click. The view says what is left unmet, so that a refusal with conditions is the way where an acceptance would stall |
| O9 | **Read the result, approve it** | Order (the badge says *Accepted*): the result card and *Approve for manufacturing*, confirmed | 4 | The approved revision, its plan, its design version with its picture and models, the requirements in force and the dialogue kept are on the order view |
| O10 | **Change and place again**: a new revision, or the same version after deleting its run | Order: edit in the rows, *Save revision n*, *Changed since it was placed: place revision n*; or *Delete* beside the run under *At the frame*, then *Place revision n* | 2 + 1 per row | Good. A draft over a placed or approved version says so on the step line ("saved, it is revision 5, placed anew") |
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
| A product's tabs (Product, Objects, Metrics, Matrix, Specification, Binding, Tables, History) | orderer | each part of the type | the order view (the tab, the header's badge of the step reached), the other tabs, Save and Discard, Compare, Runs | an editable copy of a read-only product (O1) |
| The order (`/products/<lineage>/order`) | orderer, said ("As orderer of …") | the order's steps with the next as one button; the brief, the answering policy, the mandates and the objects' change in rows; who takes it; its runs with *Delete*; the owner's word; the approval | the next step's page, the run, the overview (who takes it), the product's tabs | a metric's column edited at once (O4) |
| A metric | orderer | the metric whole, its mandate | the product's tabs | the previous and next metric |
| Runs (`/runs`) | system operator, researcher | the frame's empty state, its runs, the recorded experiments | a run, a mark's selector | a run's order (S4) |
| A run (`/runs/…`, `/frame/runs/…`) | system operator, audience, researcher | the organisation at the clock's time, the player, the turns or the result | the Runs page, a mark's selector, the run's order view (its facts; a parked run's "Your word is given on the order") | deleting it (S4) |

The header offers *am-order* (products), *Compare* and *Runs*, and a product's tabs with the step reached where one is open. It
does not offer the organisation now as a place of its own, or say which capacity a page other than the order view and the
decision makers' selector is in.

## 5. What the analysis finds

1. **The order has a place of its own**, the order view, where the orderer's main goals (O4, O6, O7, O8, O9) start and end.
2. **The state is shown where the actor is**: the header's badge is the order's step reached on every product page, and the
   order view names what to do next as one button.
3. **The links run both ways between a run and its order**; from the overview's catalogue a run of an order links to its version
   in the products home. The system operator who sees a run stuck still finds its *Delete* through the order (S4).
4. **The capacity is said** in the order view ("As orderer of …") and the decision makers' selector ("As system operator"), and
   the run's page says where the orderer's word is given. The other pages do not say it.
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

- **The dialogue (`dialogue-build.md` part 3)** built the order view with the owner's word and the approval among its steps.
- **The web app for a person (build 4)** takes the rest:
  - the three places in the header;
  - a run's *Delete* beside it in the Frame, for the system operator (S4);
  - the capacity said on every page;
  - the editable copy;
  - the table work (a column of the metrics or the mandates edited at once).
- **A check with the people it is for.** A short session with Roger Johansson, in which he states a product and places it with
  the tool while saying aloud what he looks for (a *think-aloud* test, about an hour), will show what this analysis cannot. It
  should be done once the order view stands, and its findings written here.

## 8. Open

- Whether Experiments stays in the tool or goes with am-llm's own console when the role view comes.
- R2, comparing two runs, is not proposed: it is the paper's work, not the tool's.
