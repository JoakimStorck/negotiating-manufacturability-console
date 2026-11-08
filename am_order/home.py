"""The products home: a folder of products, each in a folder of its own named by its lineage.

    <home>/groups.json                                   the tree of groups the owner names and arranges
    <home>/own|user|archive/<lineage>/order.json         the order as it stands (the latest version, whole)
    <home>/own|user|archive/<lineage>/versions/<sha>.json   every saved version, by its hash
    <home>/own|user|archive/<lineage>/changes.md         per version, what changed
    <home>/own|user|archive/<lineage>/draft.json         the draft a refused save keeps
    <home>/own|user|archive/<lineage>/pictures/<sha>.png|jpg   the owner's pictures, stored as they came
    <home>/features/<design id>/features-1.json          a design version's feature list, its picture and its model

A save is atomic: the version is written whole under its hash, then `order.json` is replaced, so a reader takes the version as
it stands and never a part of one. A save that changes nothing makes no version. `own` products (the project's) open read only
unless the home is opened with `allow_own`; a person tries changes on a copy in `user`. A product is archived, never deleted.
"""
from __future__ import annotations

import contextlib
import functools
import json
import os
import re
import shutil
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

try:
    import fcntl
except ImportError:                      # Windows
    fcntl = None
    import msvcrt

from . import schema as S
from .check import Refusal, check
from .diff import diff
from .order import Order, canonical, sha256, slug

CATEGORIES = ("own", "user", "archive")
LINEAGE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
PICTURE_TYPES = {b"\x89PNG\r\n\x1a\n": ("image/png", "png"), b"\xff\xd8\xff": ("image/jpeg", "jpg")}
PICTURE_LIMIT = 10 * 1024 * 1024
DEFAULT_GROUP = "unsorted"


class HomeError(ValueError):
    pass


class ReadOnly(HomeError):
    pass


class Refused(HomeError):
    """A save refused by the checks; the draft is kept."""

    def __init__(self, lineage: str, refusals: list[Refusal]):
        self.lineage, self.refusals = lineage, refusals
        super().__init__(f"{lineage}: the save is refused, {len(refusals)} checks fail; the draft is kept:\n  "
                         + "\n  ".join(str(r) for r in refusals))


@dataclass
class Saved:
    lineage: str
    version: str               # the hash
    revision: int
    changes: list[dict] = field(default_factory=list)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def write_atomic(path: Path, data: bytes) -> None:
    """The file written whole beside its place, then renamed into it, so that a reader sees the old file or the new and never
    a half. On Windows the rename is refused while a reader holds the file open, and a reader opening it during the rename is
    refused too: the writer retries for a moment here, and a reader on Windows retries a PermissionError on open."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{id(data)}.tmp")
    tmp.write_bytes(data)
    for attempt in range(200):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if attempt == 199:
                raise
            time.sleep(0.01)


def picture_type(data: bytes) -> tuple[str, str]:
    """The picture's media type and extension, by its first bytes; refuses anything but PNG and JPEG and anything too large."""
    if len(data) > PICTURE_LIMIT:
        raise HomeError(f"the picture is {len(data) / 1e6:.1f} MB; at most {PICTURE_LIMIT / 1e6:.0f} MB is kept")
    for magic, kind in PICTURE_TYPES.items():
        if data.startswith(magic):
            return kind
    raise HomeError("the picture is neither a PNG nor a JPEG")


def _lock(fd: int) -> None:
    if fcntl is not None:
        fcntl.flock(fd, fcntl.LOCK_EX)
        return
    while True:                           # msvcrt gives up after ten seconds; a writer waits as long as it takes
        try:
            msvcrt.locking(fd, msvcrt.LK_LOCK, 1)
            return
        except OSError:
            continue


def _unlock(fd: int) -> None:
    if fcntl is not None:
        fcntl.flock(fd, fcntl.LOCK_UN)
    else:
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)


def _writer(method):
    """A method that writes the home: it runs holding the home's writer lock."""
    @functools.wraps(method)
    def wrapped(self, *args, **kwargs):
        with self.writing():
            return method(self, *args, **kwargs)
    return wrapped


class Home:
    def __init__(self, root: Path | str | None = None, allow_own: bool = False):
        root = root or os.environ.get("AM_ORDER_HOME")
        if not root:
            raise HomeError("no products home: give --home or set AM_ORDER_HOME")
        self.root = Path(root)
        self.allow_own = allow_own
        self._guard = threading.RLock()
        self._depth = 0
        self._fd: int | None = None
        self._facets: dict[str, tuple[tuple, dict]] = {}     # path -> (the file's signature, its facets), for the tree

    @contextlib.contextmanager
    def writing(self):
        """One writer at a time in the home, across processes and threads: the file `.lock` at the root, held with the
        platform's file lock for the write. Re-entrant, so that an edit's read, change and save are one held write and a
        derive's create and save are one. Readers take no lock; the atomic writes keep what they read whole."""
        with self._guard:
            if self._depth == 0:
                self.root.mkdir(parents=True, exist_ok=True)
                self._fd = os.open(self.root / ".lock", os.O_RDWR | os.O_CREAT, 0o644)
                try:
                    _lock(self._fd)
                except BaseException:
                    os.close(self._fd)
                    self._fd = None
                    raise
            self._depth += 1
            try:
                yield
            finally:
                self._depth -= 1
                if self._depth == 0 and self._fd is not None:
                    try:
                        _unlock(self._fd)
                    finally:
                        os.close(self._fd)
                        self._fd = None

    # ------------------------------------------------------------------ products

    def folder(self, lineage: str) -> Path | None:
        for cat in CATEGORIES:
            p = self.root / cat / lineage
            if (p / "order.json").exists() or (p / "draft.json").exists():
                return p
        return None

    def category(self, lineage: str) -> str:
        f = self._folder(lineage)
        return f.parent.name

    def _folder(self, lineage: str) -> Path:
        f = self.folder(lineage)
        if f is None:
            raise HomeError(f"{lineage} is not in the products home {self.root}")
        return f

    def lineages(self, category: str | None = None) -> list[str]:
        out = []
        for cat in CATEGORIES if category is None else (category,):
            d = self.root / cat
            if d.is_dir():
                out += sorted(p.name for p in d.iterdir() if p.is_dir() and ((p / "order.json").exists() or (p / "draft.json").exists()))
        return out

    def writable(self, lineage: str) -> bool:
        cat = self.category(lineage)
        return cat == "user" or (cat == "own" and self.allow_own)

    def _require_writable(self, lineage: str) -> None:
        cat = self.category(lineage)
        if cat == "archive":
            raise ReadOnly(f"{lineage} is archived; derive a new product from it to change it")
        if cat == "own" and not self.allow_own:
            raise ReadOnly(f"{lineage} is the project's own product and opens read only; derive a copy into user to try changes, "
                           "or open the home with --allow-own")

    def load(self, ref: str) -> Order:
        """A product as it stands, or a version of it: `PRODUCT`, `PRODUCT@<revision>` or `PRODUCT@<hash prefix>`."""
        lineage, _, version = ref.partition("@")
        folder = self._folder(lineage)
        if not version:
            path = folder / "order.json"
            if not path.exists():
                raise HomeError(f"{lineage} has no saved version yet, only a draft")
            return self._read(path, lineage)
        return self._read(self._version_path(folder, version), lineage)

    def _read(self, path: Path, lineage: str) -> Order:
        data = json.loads(path.read_bytes())
        order = Order(data)
        if order.lineage != lineage:
            raise HomeError(f"{path} holds {order.lineage}, not {lineage}")
        return order

    def _version_path(self, folder: Path, version: str) -> Path:
        versions = folder / "versions"
        if version.isdigit() and len(version) < 6:
            for p in versions.glob("*.json"):
                if json.loads(p.read_bytes()).get("revision") == int(version):
                    return p
            raise HomeError(f"{folder.name} has no revision {version}")
        found = sorted(versions.glob(f"{version}*.json"))
        if len(found) != 1:
            raise HomeError(f"{folder.name}@{version}: {'no' if not found else 'more than one'} version with that hash")
        return found[0]

    def draft(self, lineage: str) -> Order | None:
        path = self._folder(lineage) / "draft.json"
        return self._read(path, lineage) if path.exists() else None

    def working(self, ref: str) -> Order:
        """What an edit starts from: the draft where one is kept, else the order as it stands; `PRODUCT@<version>` that version."""
        if "@" in ref:
            return self.load(ref)
        return self.draft(ref) or self.load(ref)

    @_writer
    def put_draft(self, lineage: str, order: Order) -> None:
        self._require_writable(lineage)
        order.validate()
        write_atomic(self._folder(lineage) / "draft.json", canonical(order.data))

    @_writer
    def discard_draft(self, lineage: str) -> None:
        self._require_writable(lineage)
        p = self._folder(lineage) / "draft.json"
        if p.exists():
            p.unlink()

    def history(self, lineage: str) -> list[dict]:
        """The saved versions, oldest first: {revision, version, saved, previous}."""
        out = []
        for p in (self._folder(lineage) / "versions").glob("*.json"):
            d = json.loads(p.read_bytes())
            out.append({"revision": d["revision"], "version": p.stem, "saved": d["saved"], "previous": d.get("previous")})
        return sorted(out, key=lambda v: v["revision"])

    def changes(self, lineage: str) -> str:
        p = self._folder(lineage) / "changes.md"
        return p.read_text(encoding="utf-8") if p.exists() else ""

    # ------------------------------------------------------------------ saving

    @_writer
    def create(self, lineage: str, name: str | None = None, purpose: str = "", group: str | None = None,
               category: str = "user") -> Order:
        """A new product, kept as a draft until its checks pass."""
        if not LINEAGE.match(lineage or ""):
            raise HomeError(f"{lineage!r}: a product's id is lowercase letters, digits and hyphens, starting with a letter or digit")
        if self.folder(lineage) is not None:
            raise HomeError(f"{lineage} is in the products home already")
        if category == "own" and not self.allow_own:
            raise ReadOnly("an own product is made only with --allow-own")
        order = Order.new(lineage, name, purpose, group=self._group_id(group))
        folder = self.root / category / lineage
        folder.mkdir(parents=True)
        write_atomic(folder / "draft.json", canonical(order.data))
        return order

    @_writer
    def save(self, order: Order, note: str = "") -> Saved | None:
        """Save a new version when the checks pass; refused, the draft is kept (`Refused`). Nothing changed, no version (None)."""
        lineage = order.lineage
        folder = self._folder(lineage)
        self._require_writable(lineage)
        order.validate()
        previous = self.load(lineage) if (folder / "order.json").exists() else None
        refusals = check(order, features=self.features(order.data["design"]) if order.data.get("design") else None, previous=previous)
        if refusals:
            write_atomic(folder / "draft.json", canonical(order.data))
            raise Refused(lineage, refusals)
        if previous is not None and previous.content_hash() == order.content_hash():
            self._drop_draft(folder)
            return None
        data = dict(order.content())
        data["revision"] = (previous.data.get("revision", 0) if previous else 0) + 1
        data["previous"] = self.version_of(lineage) if previous else None
        data["saved"] = utc_now()
        body = canonical(data)
        version = sha256(body)
        write_atomic(folder / "versions" / f"{version}.json", body)
        write_atomic(folder / "order.json", body)
        changes = diff(previous, order) if previous else self._from_parent(order)
        self._record(folder, data["revision"], version, data["saved"], changes, note)
        self._drop_draft(folder)
        order.data.update(revision=data["revision"], previous=data["previous"], saved=data["saved"])
        return Saved(lineage, version, data["revision"], changes)

    def _from_parent(self, order: Order) -> list[dict]:
        """A new product's first change record: created, and where it is derived, what differs from its parent."""
        out = [{"what": "product", "id": "product", "text": "created"}]
        parent = order.data.get("parent")
        if parent:
            try:
                origin = self.load(f"{parent['lineage']}@{parent['version']}")
            except HomeError:
                return out
            out[0]["text"] = f"created from {parent['lineage']}@{parent['version'][:12]}"
            out += [c for c in diff(origin, order) if c["what"] not in ("title",)]
        return out

    def version_of(self, lineage: str) -> str | None:
        p = self._folder(lineage) / "order.json"
        return sha256(p.read_bytes()) if p.exists() else None

    def _drop_draft(self, folder: Path) -> None:
        p = folder / "draft.json"
        if p.exists():
            p.unlink()

    def _record(self, folder: Path, revision: int, version: str, saved: str, changes: list[dict], note: str) -> None:
        path = folder / "changes.md"
        text = path.read_text(encoding="utf-8") if path.exists() else f"# {folder.name}: the change record\n"
        text += f"\n## Revision {revision}, {version[:12]}, {saved}\n\n"
        if note:
            text += f"{note}\n\n"
        text += "".join(f"- {c['text']}\n" for c in changes)
        write_atomic(path, text.encode())

    @_writer
    def edit(self, lineage: str, change, note: str = "") -> Saved | None:
        """Apply `change(order)` to what an edit starts from, then save: refused, the draft is kept."""
        self._require_writable(lineage)
        order = self.working(lineage)
        change(order)
        return self.save(order, note)

    # ------------------------------------------------------------------ managing

    @_writer
    def derive(self, source: str, lineage: str, name: str | None = None, group: str | None = None, category: str = "user",
               change=None) -> Order:
        """A new product in `user` (`own` with allow_own) from a saved one (`PRODUCT` or `PRODUCT@<version>`): the metrics' ids kept, the parent recorded,
        saved at once where its checks pass, else kept as a draft."""
        src_lineage = source.partition("@")[0]
        origin = self.load(source)
        folder = self._folder(src_lineage)
        version = sha256((folder / "order.json").read_bytes()) if "@" not in source else self._version_path(folder, source.partition("@")[2]).stem
        self.create(lineage, name or origin.data.get("title"), origin.data["product"].get("purpose", ""),
                    group or self.group_path(origin.data.get("group")), category=category)
        made = self.root / category / lineage
        try:
            data = {k: v for k, v in origin.content().items()}
            data = json.loads(json.dumps(data))
            data["lineage"] = lineage
            data["title"] = name or origin.data.get("title")
            data["product"]["name"] = name or data["product"]["name"]
            data["parent"] = {"lineage": src_lineage, "version": version}
            data["group"] = self._group_id(group) if group else data.get("group") or self._group_id(None)
            order = Order(data)
            if change is not None:
                change(order)
            try:
                self.save(order)
            except Refused:
                pass                            # refused by a check: the draft stands, as a refused save leaves it
            return order
        except BaseException:
            shutil.rmtree(made, ignore_errors=True)   # anything else leaves no half-made product behind
            raise

    def compare(self, a: str, b: str) -> list[dict]:
        """The changes from one product or version to another (`PRODUCT`, `PRODUCT@<version>`)."""
        return diff(self.load(a), self.load(b))

    @_writer
    def move(self, lineage: str, group: str) -> Saved | None:
        gid = self._group_id(group)
        return self.edit(lineage, lambda o: o.data.update(group=gid), note=f"moved to {self.group_path(gid)}")

    @_writer
    def tag(self, lineage: str, add=(), remove=()) -> Saved | None:
        def change(o):
            tags = [t for t in o.data.get("tags", []) if t not in remove]
            o.data["tags"] = tags + [t for t in add if t not in tags]
        return self.edit(lineage, change)

    @_writer
    def archive(self, lineage: str) -> Path:
        folder = self._folder(lineage)
        if folder.parent.name == "archive":
            raise HomeError(f"{lineage} is archived already")
        self._require_writable(lineage)
        target = self.root / "archive" / lineage
        target.parent.mkdir(parents=True, exist_ok=True)
        folder.rename(target)
        return target

    @_writer
    def from_features(self, design: str, lineage: str | None = None, group: str | None = None) -> Order:
        """A skeleton for a design that has no order: the product's objects from the design's declared features, each bound
        `declared`; kept as a draft, its needs and metrics for the owner to state."""
        from .bind import skeleton_objects
        features = self.features(design)
        if features is None:
            raise HomeError(f"no feature list of {design} in the products home")
        lineage = lineage or slug(features["lineage"])
        order = self.create(lineage, features.get("title") or features["lineage"], "", group)
        order.data["design"] = design
        skeleton_objects(order, features)
        self.put_draft(lineage, order)
        return order

    # ------------------------------------------------------------------ pictures

    @_writer
    def set_picture(self, lineage: str, data: bytes, name: str = "") -> Saved | None:
        kind, ext = picture_type(data)
        self._require_writable(lineage)
        sha = sha256(data)
        target = self._folder(lineage) / "pictures" / f"{sha}.{ext}"
        if not target.exists():
            write_atomic(target, data)
        picture = {"source": "owner", "sha256": sha, "type": kind, **({"name": name} if name else {})}
        return self.edit(lineage, lambda o: o.data["product"].update(picture=picture))

    @_writer
    def picture_from_design(self, lineage: str) -> Saved | None:
        return self.edit(lineage, lambda o: o.data["product"].update(picture={"source": "design"}))

    @_writer
    def clear_picture(self, lineage: str) -> Saved | None:
        return self.edit(lineage, lambda o: o.data["product"].update(picture=None))

    def picture(self, order: Order) -> tuple[Path, str] | None:
        """The overview picture's file and type: the owner's, else the bound design's, else none."""
        p = order.data["product"].get("picture")
        if p and p["source"] == "owner":
            folder = self._folder(order.lineage)
            ext = "png" if p["type"] == "image/png" else "jpg"
            path = folder / "pictures" / f"{p['sha256']}.{ext}"
            return (path, p["type"]) if path.exists() else None
        design = order.data.get("design")
        if design:
            f = self.features(design)
            if f is not None:
                return self.root / "features" / design / f["picture"]["file"], "image/png"
        return None

    # ------------------------------------------------------------------ feature lists

    def features(self, design: str) -> dict | None:
        path = self.root / "features" / design / "features-1.json"
        if not path.exists():
            return None
        return S.validate_features(json.loads(path.read_bytes()))

    def feature_file(self, design: str, name: str) -> Path:
        """A file beside a feature list (its picture, its model), by the name the list gives it."""
        f = self.features(design)
        if f is None:
            raise HomeError(f"no feature list of {design}")
        names = {f["picture"]["file"]} | {m["file"] for m in f["models"]}
        if name not in names:
            raise HomeError(f"{design} has no file {name!r} beside its feature list")
        return self.root / "features" / design / name

    def designs(self) -> list[str]:
        d = self.root / "features"
        return sorted(p.name for p in d.iterdir() if (p / "features-1.json").exists()) if d.is_dir() else []

    @_writer
    def add_features(self, source: Path | str) -> str:
        """A feature list's folder taken into the home, its files checked against their hashes; a version's list never changes."""
        source = Path(source)
        data = S.validate_features(json.loads((source / "features-1.json").read_bytes()))
        for f in [data["picture"]] + data["models"]:
            if sha256((source / f["file"]).read_bytes()) != f["sha256"]:
                raise HomeError(f"{source / f['file']} does not match its hash in the list")
        target = self.root / "features" / data["design"]
        if target.exists():
            if (target / "features-1.json").read_bytes() != (source / "features-1.json").read_bytes():
                raise HomeError(f"{data['design']} has another feature list in the home; a version's list never changes")
            return data["design"]
        tmp = target.with_name(f".{target.name}.tmp")
        shutil.copytree(source, tmp)
        os.replace(tmp, target)
        return data["design"]

    # ------------------------------------------------------------------ groups

    def groups(self) -> dict:
        p = self.root / "groups.json"
        return json.loads(p.read_text(encoding="utf-8"))["groups"] if p.exists() else {}

    @_writer
    def _write_groups(self, groups: dict) -> None:
        write_atomic(self.root / "groups.json", (json.dumps({"groups": groups}, indent=1, sort_keys=True, ensure_ascii=False) + "\n").encode())

    def group_path(self, gid: str | None, groups: dict | None = None) -> str:
        groups, parts = self.groups() if groups is None else groups, []
        while gid and gid in groups:
            parts.append(groups[gid]["name"])
            gid = groups[gid]["parent"]
        return "/".join(reversed(parts))

    def find_group(self, path: str) -> str | None:
        parent = None
        for name in [p for p in path.split("/") if p]:
            gid = next((g for g, v in self.groups().items() if v["name"] == name and v["parent"] == parent), None)
            if gid is None:
                return None
            parent = gid
        return parent

    def _group_id(self, group: str | None) -> str:
        """A group by its id or its path; a path not there yet is made."""
        group = group or DEFAULT_GROUP
        if group in self.groups():
            return group
        return self.find_group(group) or self.add_group(group)

    def add_group(self, path: str) -> str:
        parent = None
        for name in [p for p in path.split("/") if p]:
            groups = self.groups()
            gid = next((g for g, v in groups.items() if v["name"] == name and v["parent"] == parent), None)
            if gid is None:
                gid = f"G{max((int(g[1:]) for g in groups), default=0) + 1}"
                groups[gid] = {"name": name, "parent": parent}
                self._write_groups(groups)
            parent = gid
        if parent is None:
            raise HomeError("a group needs a name")
        return parent

    def rename_group(self, group: str, name: str) -> None:
        gid, groups = self._existing_group(group), self.groups()
        if any(v["name"] == name and v["parent"] == groups[gid]["parent"] for g, v in groups.items() if g != gid):
            raise HomeError(f"a group {name!r} stands there already")
        groups[gid]["name"] = name
        self._write_groups(groups)

    def move_group(self, group: str, parent: str | None) -> None:
        gid, groups = self._existing_group(group), self.groups()
        pid = self._existing_group(parent) if parent else None
        at = pid
        while at:
            if at == gid:
                raise HomeError("a group cannot stand under itself")
            at = groups[at]["parent"]
        groups[gid]["parent"] = pid
        self._write_groups(groups)

    def remove_group(self, group: str) -> None:
        gid, groups = self._existing_group(group), self.groups()
        if any(v["parent"] == gid for v in groups.values()):
            raise HomeError(f"{self.group_path(gid)} holds groups; move them first")
        holding = [lin for lin in self.lineages() if self._summary_order(lin).data.get("group") == gid]
        if holding:
            raise HomeError(f"{self.group_path(gid)} holds products ({', '.join(holding)}); a group that holds products is not removed")
        del groups[gid]
        self._write_groups(groups)

    def _existing_group(self, group: str) -> str:
        if group in self.groups():
            return group
        gid = self.find_group(group)
        if gid is None:
            raise HomeError(f"no group {group!r}")
        return gid

    # ------------------------------------------------------------------ facets and the tree

    def _summary_order(self, lineage: str) -> Order:
        return self.draft(lineage) or self.load(lineage)

    def facets(self, lineage: str, groups: dict | None = None) -> dict:
        """What is read from the order itself: its state, its design, its material, its counts. Kept per file signature
        (inode, time, size, which the atomic write renews), so that the tree reads an order once until it changes."""
        folder = self._folder(lineage)
        draft = (folder / "draft.json").exists()
        path = folder / ("draft.json" if draft else "order.json")
        st = path.stat()
        signature = (st.st_ino, st.st_mtime_ns, st.st_size)
        kept = self._facets.get(str(path))
        if kept is None or kept[0] != signature:
            order = self._read(path, lineage)
            metrics = order.metrics()
            design = order.data.get("design")
            if draft:
                state = "draft"
            elif design:
                bound = [f for b in order.data.get("bindings", []) if b["design"] == design for f in b["features"]]
                state = "confirmed" if bound and all(f["confirmed"] for f in bound) else "bound"
            else:
                state = "checked"
            material = next((str(next(iter((m.get("value") or {"": None}).values()))) for m in metrics if m.get("quantity") == "material"), None)
            kept = (signature, {"lineage": lineage, "title": order.data.get("title"), "category": folder.parent.name, "state": state,
                                "design": design, "material": material, "group_id": order.data.get("group"),
                                "tags": list(order.data.get("tags", [])),
                                "demands": sum(m.get("class") == "demand" for m in metrics), "wishes": sum(m.get("class") == "wish" for m in metrics),
                                "mandates": sum(order.mandate(m)["form"] != "held" for m in metrics)})
            self._facets[str(path)] = kept
        f = dict(kept[1])
        f["group"] = self.group_path(f.pop("group_id"), groups)
        f["tags"] = list(f["tags"])
        return f

    def tree(self, tag: str | None = None, state: str | None = None, find: str | None = None, facet: dict | None = None,
             archived: bool = False) -> list[dict]:
        """The products with their facets, filtered, each with its group's path."""
        out, groups = [], self.groups()
        for lineage in self.lineages():
            f = self.facets(lineage, groups)
            if f["category"] == "archive" and not archived and state != "archived":
                continue
            if tag and tag not in f["tags"]:
                continue
            if state and not (f["state"] == state or (state == "archived" and f["category"] == "archive")):
                continue
            if find and find.lower() not in json.dumps(self._summary_order(lineage).data, ensure_ascii=False).lower():
                continue
            if facet and any(str(f.get(k)) != str(v) for k, v in facet.items()):
                continue
            out.append(f)
        return sorted(out, key=lambda f: (f["group"], f["lineage"]))
