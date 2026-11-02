"""The command line, each command once against a copy of the examples."""
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
