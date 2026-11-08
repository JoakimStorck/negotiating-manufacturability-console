"""The products home: saving, versions and the change record, own products, derive, move, tag, archive, groups, facets, pictures,
the skeleton from a feature list, and a reader never seeing a half-written order."""
import json
import threading
import time

import pytest

from am_order import Home, HomeError, ReadOnly, Refused
from am_order.schema import SchemaError

PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 64


def test_open_filter_and_the_tree(home):
    rows = home.tree()
    assert {r["lineage"] for r in rows} == {"plate", "l-bracket", "bracket-ge", "bracket-mass"}
    assert {r["group"] for r in rows} == {"reference cases/H1"}
    assert [r["lineage"] for r in home.tree(tag="engine bracket")] == ["bracket-ge", "bracket-mass"]
    assert {r["lineage"] for r in home.tree(find="lead screw")} == {"l-bracket"}
    assert all(r["state"] == "confirmed" for r in home.tree(state="confirmed")) and len(home.tree(state="confirmed")) == 4
    f = home.facets("bracket-mass")
    assert (f["design"], f["material"], f["mandates"], f["wishes"]) == ("bracket-mass@v1", "Prusament PLA", 4, 0)
    assert home.facets("bracket-ge")["wishes"] == 1


def test_an_own_product_is_refused_without_allow_own(home, own):
    order = home.working("bracket-ge")
    order.metric("M5")["value"] = {"at_most": 0.15}
    with pytest.raises(ReadOnly, match="read only"):
        home.save(order)
    with pytest.raises(ReadOnly):
        home.tag("bracket-ge", add=["x"])
    with pytest.raises(ReadOnly):
        home.put_draft("bracket-ge", order)
    assert own.save(order).revision == 2


def test_derive_into_user_then_edit_versions_and_the_change_record(home):
    new = home.derive("bracket-ge", "my-bracket", "My bracket")
    assert home.category("my-bracket") == "user" and home.draft("my-bracket") is None
    assert new.data["parent"]["lineage"] == "bracket-ge" and [m["id"] for m in new.data["metrics"]] == [m["id"] for m in home.load("bracket-ge").data["metrics"]]

    def tighten(o):
        o.metric("M5")["value"] = {"at_most": 0.15}
    saved = home.edit("my-bracket", tighten)
    assert saved.revision == 2 and saved.changes[0]["text"] == "value M5: at most 0.2 mm -> at most 0.15 mm"
    assert home.edit("my-bracket", tighten) is None                         # nothing changed: no version
    assert [v["revision"] for v in home.history("my-bracket")] == [1, 2]
    assert home.load("my-bracket@1").metric("M5")["value"] == {"at_most": 0.2}
    assert "value M5: at most 0.2 mm -> at most 0.15 mm" in home.changes("my-bracket")
    assert [c["text"] for c in home.compare("my-bracket@1", "my-bracket")] == ["value M5: at most 0.2 mm -> at most 0.15 mm"]
    first = home.history("my-bracket")[0]["version"]
    assert home.load(f"my-bracket@{first[:10]}").data["revision"] == 1


def test_a_derive_that_fails_leaves_no_product(home):
    def broken(o):
        raise ValueError("the change fails")
    with pytest.raises(ValueError):
        home.derive("bracket-ge", "half", change=broken)
    assert home.folder("half") is None and "half" not in home.lineages()
    with pytest.raises(SchemaError):                              # an order the schema refuses is no product either
        home.derive("bracket-ge", "half", change=lambda o: o.data.__setitem__("metrics", "nonsense"))
    assert home.folder("half") is None
    home.derive("bracket-ge", "half")                              # and the name is free for a derive that works
    assert home.category("half") == "user"


def test_a_refused_save_keeps_the_draft(home):
    home.derive("plate", "p2")
    order = home.working("p2")
    order.metric("M4")["unit"] = None
    with pytest.raises(Refused) as e:
        home.save(order)
    assert [r.rule for r in e.value.refusals] == ["unambiguous"]
    assert home.draft("p2").metric("M4")["unit"] is None and home.load("p2").metric("M4")["unit"] == "mm"
    assert home.facets("p2")["state"] == "draft"
    home.discard_draft("p2")
    assert home.draft("p2") is None


def test_move_tag_archive_and_groups(home):
    home.derive("plate", "p3")
    home.move("p3", "trials/2026")
    assert home.facets("p3")["group"] == "trials/2026"
    home.tag("p3", add=["control", "flat"])
    home.tag("p3", remove=["flat"])
    assert home.facets("p3")["tags"] == ["control"]
    assert "group:" in home.changes("p3") and "tags: +control, +flat" in home.changes("p3")
    gid = home.find_group("trials")
    with pytest.raises(HomeError, match="holds groups"):
        home.remove_group(gid)
    with pytest.raises(HomeError, match="holds products"):
        home.remove_group("trials/2026")
    home.rename_group("trials", "tests")
    assert home.facets("p3")["group"] == "tests/2026"
    home.archive("p3")
    assert home.category("p3") == "archive" and "p3" not in {r["lineage"] for r in home.tree()}
    assert "p3" in {r["lineage"] for r in home.tree(state="archived")}
    with pytest.raises(ReadOnly, match="archived"):
        home.tag("p3", add=["x"])


def test_pictures(home):
    home.derive("bracket-ge", "b2")
    assert home.picture(home.load("b2"))[0].name == "picture.png"           # none of its own: the design's
    home.set_picture("b2", PNG, "sketch.png")
    path, kind = home.picture(home.load("b2"))
    assert kind == "image/png" and path.read_bytes() == PNG and path.parent.name == "pictures"
    assert "picture: the design's" in home.changes("b2") or "picture: none" in home.changes("b2")
    with pytest.raises(HomeError, match="neither a PNG nor a JPEG"):
        home.set_picture("b2", b"GIF89a....")
    home.clear_picture("b2")
    home.create("bare")
    assert home.picture(home.working("bare")) is None


def test_a_skeleton_from_a_feature_list(home):
    order = home.from_features("nist-am-artifact@v1", "nist", "library")
    names = {o["name"]: o for o in order.objects()}
    assert {"central hole", "central boss", "lateral hole d3", "lateral hole d6", "pin d4", "part"} <= set(names)
    assert order.features_of(names["central hole"]["id"]) == ["central-hole"]
    assert home.facets("nist")["state"] == "draft"


def test_a_reader_never_sees_a_half_written_order(home):
    home.derive("bracket-ge", "busy")
    path = home.folder("busy") / "order.json"
    stop, seen, bad = threading.Event(), [], []

    def read():
        while not stop.is_set():
            try:
                seen.append(json.loads(path.read_bytes())["revision"])
            except (ValueError, KeyError) as e:
                bad.append(e)
            except PermissionError:
                pass                # Windows refuses the open while the file is being replaced; a reader tries again
    reader = threading.Thread(target=read)
    reader.start()
    for i in range(40):
        home.edit("busy", lambda o, i=i: o.metric("M5").update(value={"at_most": 0.2 - 0.001 * (i + 1)}))
    stop.set()
    reader.join()
    assert not bad and seen and max(seen) == 41


def test_one_writer_at_a_time_in_the_home(home, home_dir):
    """Two homes on the same root, as two processes would be: an edit's read, change and save are one held write, so that
    edits from both sides all count; and a writer waits for the one holding the lock."""
    home.derive("bracket-ge", "shared")
    other = Home(home_dir)

    def bump(h, n):
        for _ in range(n):
            h.edit("shared", lambda o: o.metric("M5").update(value={"at_most": round(o.metric("M5")["value"]["at_most"] - 0.001, 3)}))
    a, b = threading.Thread(target=bump, args=(home, 8)), threading.Thread(target=bump, args=(other, 8))
    a.start(); b.start(); a.join(); b.join()
    assert home.load("shared").metric("M5")["value"] == {"at_most": 0.184} and home.load("shared").data["revision"] == 17

    released, saved = [], []
    def hold():
        with home.writing():
            time.sleep(0.4)
            released.append(time.monotonic())
    t = threading.Thread(target=hold)
    t.start()
    time.sleep(0.05)
    other.tag("shared", add=["waited"])
    saved.append(time.monotonic())
    t.join()
    assert released and saved[0] > released[0]                     # the other home's write came after the lock was let go
    assert (home_dir / ".lock").exists() and "waited" in home.facets("shared")["tags"]


def test_the_tree_reads_an_order_once_until_it_changes(home, monkeypatch):
    reads = []
    original = Home._read
    monkeypatch.setattr(Home, "_read", lambda self, path, lineage: reads.append(path.name) or original(self, path, lineage))
    first = home.tree(archived=True)
    assert len(reads) == len(first) > 0
    reads.clear()
    assert home.tree(archived=True) == first and reads == []                 # the second tree reads no order
    home.derive("plate", "p3")
    reads.clear()
    home.tree(archived=True)
    assert reads == ["order.json"]                                           # only the new one
    home.edit("p3", lambda o: o.data.update(tags=["fresh"]))
    reads.clear()
    rows = {r["lineage"]: r for r in home.tree(archived=True)}
    assert reads == ["order.json"] and rows["p3"]["tags"] == ["fresh"]      # the changed one is read again, and read right
    home.add_group("Trials")
    home.move("p3", "Trials")
    reads.clear()
    assert {r["lineage"]: r["group"] for r in home.tree(archived=True)}["p3"] == "Trials" and reads == ["order.json"]
