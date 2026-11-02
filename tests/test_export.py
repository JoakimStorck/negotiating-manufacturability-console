"""The workbook round trip for each example, an edited workbook checked as a draft, and the ReqIF export parsed back."""
import io

import pytest
from openpyxl import load_workbook

from am_order import Refused, check, export, import_xlsx, read_reqif
from am_order.order import canonical
from conftest import REFERENCE


@pytest.mark.parametrize("lineage", REFERENCE)
def test_a_workbook_exported_and_imported_unchanged_gives_the_same_order(home, lineage):
    order = home.load(lineage)
    back = import_xlsx(export(order, "xlsx"))
    assert canonical(back.data) == canonical(order.data)
    for version in home.history(lineage):
        old = home.load(f"{lineage}@{version['revision']}")
        assert canonical(import_xlsx(export(old, "xlsx")).data) == canonical(old.data)


def test_an_edited_workbook_comes_in_as_a_draft_and_is_checked(home):
    home.derive("bracket-ge", "edited")
    wb = load_workbook(io.BytesIO(export(home.load("edited"), "xlsx")))
    ws = wb["Requirements list"]
    head = [c.value for c in ws[1]]
    row = next(r for r in ws.iter_rows(min_row=2) if r[0].value == "M5")
    row[head.index("unit")].value = None                              # a unit lost
    row[head.index("comparator")].value = "at_most"
    row[head.index("value")].value = 0.1                               # a value tightened
    m = wb["Needs-metrics matrix"]
    col = [c.value for c in m[1]].index("M5")
    for r in m.iter_rows(min_row=2):
        r[col].value = None                                            # the matrix's ticks for M5 cleared
    buf = io.BytesIO()
    wb.save(buf)
    order = import_xlsx(buf.getvalue())
    assert order.metric("M5")["value"] == {"at_most": 0.1} and order.metric("M5")["needs"] == []
    with pytest.raises(Refused) as e:
        home.save(order)
    assert {(r.rule, r.item) for r in e.value.refusals} == {("unambiguous", "M5"), ("necessary", "M5"), ("covered", "N2")}
    assert home.draft("edited").metric("M5")["value"] == {"at_most": 0.1}


def test_reqif_of_the_bracket_parsed_back(bracket):
    data = export(bracket, "reqif")
    assert data.startswith(b'<?xml') and b"http://www.omg.org/spec/ReqIF/20110401/reqif.xsd" in data
    parsed = read_reqif(data)
    d = bracket.data
    assert {k: len(v) for k, v in parsed["objects"].items()} == {"Metric": len(d["metrics"]), "Need": len(d["needs"]), "Object": len(d["objects"])}
    measures = [(s, t) for kind, s, t in parsed["relations"] if kind == "measures"]
    assert sorted(measures) == sorted((m["id"], n) for m in d["metrics"] for n in m["needs"])
    assert len([r for r in parsed["relations"] if r[0] == "concerns"]) == len(d["metrics"])
    m6 = next(o for o in parsed["objects"]["Metric"] if o["id"] == "M6")["attributes"]
    assert m6["quantity"] == "utilisation" and '"at_most": 0.6' in m6["value"] and m6["importance"] == "5"
