"""The tables, in Markdown and HTML."""
from am_order import render, table
from am_order.render import TABLES


def test_the_bracket_tables(bracket):
    cols, rows = table(bracket, "matrix")
    assert cols[:3] == ["Need", "M1", "M2"] and rows[0][0] == "N1 Carries the handling loads"
    assert [c for c, x in zip(cols[1:], rows[0][1:]) if x] == ["M6", "M7", "M8", "M9"]
    cols, rows = table(bracket, "metrics")
    assert next(r for r in rows if r[0] == "M6")[3] == "5"                        # the highest of its needs' importance
    cols, rows = table(bracket, "specification")
    assert "Mandate (this order)" not in cols and table(bracket, "specification", mandate=True)[0][-1] == "Mandate (this order)"
    cols, rows = table(bracket, "traceability")
    assert ["N4", "M2", "O5 pin hole", "pin-hole", "pin gauge"] in rows
    cols, rows = table(bracket, "requirements")
    assert [r[0] for r in rows if r[0]][:2] == ["M1", "M2"] and any(r[2] == "Transport" and r[4] == "(the owner's statement)" for r in rows)
    cols, rows = table(bracket, "objects")
    assert cols[-1] == "Change" and ["O6", "lug", "wall", "1", "", "free: the design may change around it"] in rows
    assert next(r for r in rows if r[0] == "O2")[-1] == "fixed: an interface the design keeps"
    cols, rows = table(bracket, "order")
    order = {r[0]: r[1] for r in rows}
    assert order["Answering"] == "park: a case the mandates do not cover parks at the frame for your word" and order["Quantity"] == "10"
    assert order["In force"] == order["Accepted"] == "none yet; written when the frame accepts a plan for this order"
    md = render(bracket, "markdown")
    html = render(bracket, "html", mandate=True)
    assert md.count("### ") == len(TABLES) and html.count("<table") == len(TABLES) and "interval" not in md
