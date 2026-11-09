"""The command line, each command once against a copy of the examples."""
import importlib.metadata
import json

from am_order import Home
from am_order.cli import main

PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 32


def run(home_dir, *args, own=False):
    return main(["--home", str(home_dir)] + (["--allow-own"] if own else []) + list(args))


def test_the_commands(home_dir, tmp_path, capsys):
    assert run(home_dir, "tree", "--tag", "engine bracket") == 0
    assert "bracket-mass" in capsys.readouterr().out
    assert run(home_dir, "check", "bracket-ge") == 0
    assert run(home_dir, "show", "bracket-mass", "--mandate", "--table", "specification") == 0
    assert "interval, as needed" not in capsys.readouterr().out          # the held case: the mass held
    assert run(home_dir, "show", "bracket-mass@1", "--mandate", "--table", "specification") == 0
    assert "interval, as needed" in capsys.readouterr().out
    assert run(home_dir, "history", "bracket-mass") == 0 and "mandate M13: interval, as needed -> held" in capsys.readouterr().out
    assert run(home_dir, "compare", "bracket-ge", "bracket-mass@1") == 0 and "value M13: at most 40 g -> at most 16 g" in capsys.readouterr().out
    assert run(home_dir, "tag", "plate", "--add", "x") == 1 and "read only" in capsys.readouterr().err
    assert run(home_dir, "derive", "plate", "plate-2") == 0
    assert run(home_dir, "groups", "add", "trials/cli") == 0
    assert run(home_dir, "move", "plate-2", "trials/cli") == 0 and run(home_dir, "tag", "plate-2", "--add", "control") == 0
    (tmp_path / "p.png").write_bytes(PNG)
    assert run(home_dir, "picture", "plate-2", "--set", str(tmp_path / "p.png")) == 0
    assert run(home_dir, "xlsx", "export", "plate-2", str(tmp_path / "p.xlsx")) == 0
    assert run(home_dir, "xlsx", "import", str(tmp_path / "p.xlsx")) == 0 and "nothing changed" in capsys.readouterr().out
    assert run(home_dir, "reqif", "export", "plate-2", str(tmp_path / "p.reqif")) == 0
    assert run(home_dir, "from-features", "mfcad-simple@v1", "--group", "library") == 0
    assert run(home_dir, "check", "mfcad-simple") == 1
    assert run(home_dir, "bind", "plate-2", "--confirm", "O2") == 0
    assert run(home_dir, "archive", "plate-2") == 0
    capsys.readouterr()
    assert run(home_dir, "features", "list") == 0 and "nist-am-artifact@v1" in capsys.readouterr().out
    f = Home(home_dir).facets("plate-2")
    assert (f["category"], f["group"], f["tags"]) == ("archive", "trials/cli", ["control"])


def test_the_version_is_the_packages():
    import am_order
    assert importlib.metadata.version("am-order") == am_order.__version__     # pyproject.toml reads it from the package


def test_serve_listens_where_it_is_told(home_dir, monkeypatch, capsys):
    import uvicorn
    seen = {}
    monkeypatch.setattr(uvicorn, "run", lambda app, **kw: seen.update(kw))
    assert main(["--home", str(home_dir), "serve"]) == 0
    assert seen["host"] == "127.0.0.1" and seen["port"] == 8770
    assert "no login" not in capsys.readouterr().err
    assert main(["--home", str(home_dir), "serve", "--host", "0.0.0.0", "--port", "8771"]) == 0
    assert seen["host"] == "0.0.0.0" and seen["port"] == 8771
    out = capsys.readouterr()
    assert "every interface, port 8771" in out.out and "the web app has no login" in out.err


def test_migrate_writes_the_draft_prints_the_notes_and_saves_once_stated(home_dir, capsys):
    assert run(home_dir, "migrate", "--all", own=True) == 0
    assert capsys.readouterr().out.count("order 2 already") == 4                      # the examples are order 2 as they stand
    assert run(home_dir, "migrate", "bracket-ge@1", own=True) == 0
    out = capsys.readouterr().out
    assert "bracket-ge@1: migrated to order 2, a draft" in out
    assert "may_change named lug_thickness, fillet_radius, underside_angle: state which objects are free" in out
    draft = Home(home_dir).draft("bracket-ge")
    assert draft.form == 2 and draft.free() == []
    assert run(home_dir, "migrate", "bracket-ge@1", "--free", "O99", own=True) == 1 and "has no object O99" in capsys.readouterr().err
    assert run(home_dir, "migrate", "bracket-ge@2", "--free", "O6", "--free", "O7", "--free", "O9", "--save", own=True) == 0
    assert "nothing changed, no version made" in capsys.readouterr().out          # revision 3 is that migration already
    assert run(home_dir, "migrate", "plate@2", "--answering", "decline", "--save", own=True) == 0
    assert "plate: revision 4" in capsys.readouterr().out
    assert Home(home_dir).load("plate").answering() == "decline"
    assert run(home_dir, "check", "plate") == 0 and run(home_dir, "show", "plate", "--table", "order") == 0
    assert "decline: a case the mandates do not cover is declined by the requester" in capsys.readouterr().out
