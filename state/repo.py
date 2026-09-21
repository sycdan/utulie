"""Read and write a utulie state repo.

Layout:

    kb/<id>.md                 identity, KINGSMetaL frontmatter
    .utulie/<name>/            a container; holds `.container` naming its id
    .utulie/<name>/<name>      an item placement; names its id, and its
                               quantity when the item is fungible

The tree records home. `meta.position` on the kb doc records where the thing
actually was last seen; the two disagreeing is what "checked out" means.

Directory and file names are the kb doc's `name` verbatim, which is the id
until somebody renames it. Identity lives in the kb doc; the tree only says
where things are.
"""

from __future__ import annotations

import re
import subprocess
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import yaml

CONTAINER_MARKER = ".container"
KB = "kb"
TREE = ".utulie"
KINDS = ("item", "container")
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")

# KINGSMetaL field order. Anything else is rejected rather than silently kept.
FIELD_ORDER = ("kind", "id", "name", "gist", "scopes", "meta", "links")


def new_id() -> str:
    """UUIDv7 where available, v4 otherwise. Nothing depends on it being v7."""
    maker = getattr(uuid, "uuid7", uuid.uuid4)
    return str(maker())


def write_lines(path: Path, lines: list[str]) -> None:
    """Always LF. A CRLF state repo diffs badly and reads worse."""
    body = "".join(ln + "\n" for ln in lines)
    path.write_text(body, encoding="utf-8", newline="\n")


@dataclass
class Doc:
    kind: str
    id: str
    name: str
    gist: str
    title: str
    meta: dict = field(default_factory=dict)

    @property
    def fungible(self) -> bool:
        return bool(self.meta.get("fungible"))


@dataclass
class Placement:
    id: str
    path: str          # posix path relative to the repo root
    container: str | None   # id of the containing container, None at tree root
    quantity: int | None


@dataclass
class Problem:
    kind: str
    id: str
    detail: str

    def __str__(self) -> str:
        return f"{self.kind}: {self.id} -- {self.detail}"


class StateError(Exception):
    pass


class StateRepo:
    def __init__(self, root: Path | str):
        self.root = Path(root)

    # -- git ------------------------------------------------------------
    def _git(self, *args: str) -> str:
        out = subprocess.run(
            ["git", *args], cwd=self.root, capture_output=True, text=True
        )
        if out.returncode:
            raise StateError(f"git {' '.join(args)}: {out.stderr.strip()}")
        return out.stdout

    def _commit(self, message: str) -> None:
        self._git("add", "-A")
        if not self._git("status", "--porcelain").strip():
            return
        self._git("commit", "-q", "-m", message)

    def init(self) -> None:
        (self.root / KB).mkdir(parents=True, exist_ok=True)
        (self.root / TREE).mkdir(parents=True, exist_ok=True)
        if not (self.root / ".git").exists():
            self._git("init", "-q", ".")
        (self.root / TREE / ".gitkeep").touch()
        self._commit("initialise state repo")

    # -- kb docs --------------------------------------------------------
    def _doc_path(self, id_: str) -> Path:
        return self.root / KB / f"{id_}.md"

    def doc(self, id_: str) -> Doc:
        path = self._doc_path(id_)
        if not path.exists():
            raise StateError(f"no kb doc for {id_}")
        raw = path.read_text(encoding="utf-8")
        _, fm, body = raw.split("---\n", 2)
        data = yaml.safe_load(fm) or {}
        title = next(
            (ln[2:].strip() for ln in body.splitlines() if ln.startswith("# ")), ""
        )
        return Doc(
            kind=data["kind"],
            id=data["id"],
            name=data["name"],
            gist=data.get("gist", ""),
            title=title,
            meta=data.get("meta") or {},
        )

    def _write_doc(self, doc: Doc) -> None:
        # KINGSMetaL field order. Insertion order plus sort_keys=False gives it
        # in one dump; quoting is the yaml library's business, not ours.
        data = {"kind": doc.kind, "id": doc.id, "name": doc.name, "gist": doc.gist}
        if doc.meta:
            data["meta"] = doc.meta
        fm = yaml.safe_dump(data, sort_keys=False, allow_unicode=True, indent=2)
        self._doc_path(doc.id).write_text(
            f"---\n{fm}---\n\n# {doc.title}\n", encoding="utf-8", newline="\n"
        )

    def docs(self) -> dict[str, Doc]:
        return {
            p.stem: self.doc(p.stem) for p in sorted((self.root / KB).glob("*.md"))
        }

    # -- index ----------------------------------------------------------
    def index(self) -> tuple[dict[str, str], list[Placement]]:
        """Walk the tree once. Returns (container id -> path, placements)."""
        containers: dict[str, str] = {}
        placements: list[Placement] = []
        tree = self.root / TREE
        if not tree.exists():
            return containers, placements

        def container_id(d: Path) -> str | None:
            marker = d / CONTAINER_MARKER
            if not marker.exists():
                return None
            return (yaml.safe_load(marker.read_text(encoding="utf-8")) or {}).get("id")

        for d in sorted(p for p in tree.rglob("*") if p.is_dir()):
            cid = container_id(d)
            if cid is None:
                continue
            containers[cid] = d.relative_to(self.root).as_posix()
            parent = container_id(d.parent) if d.parent != tree else None
            placements.append(
                Placement(cid, containers[cid], parent, None)
            )

        for f in sorted(p for p in tree.rglob("*") if p.is_file()):
            if f.name in (CONTAINER_MARKER, ".gitkeep"):
                continue
            data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
            placements.append(
                Placement(
                    id=data.get("id"),
                    path=f.relative_to(self.root).as_posix(),
                    container=container_id(f.parent),
                    quantity=data.get("quantity"),
                )
            )
        return containers, placements

    def locate(self, id_: str) -> list[Placement]:
        return [p for p in self.index()[1] if p.id == id_]

    def contents(self, container_id: str) -> list[Placement]:
        return [p for p in self.index()[1] if p.container == container_id]

    def path_of(self, id_: str) -> list[Doc]:
        """The chain of containers from the tree root down to `id_`."""
        _, placements = self.index()
        chain = []
        cur = next((p for p in placements if p.id == id_), None)
        while cur is not None and cur.container is not None:
            chain.append(self.doc(cur.container))
            cur = next((p for p in placements if p.id == cur.container), None)
        return list(reversed(chain))

    # -- writes ---------------------------------------------------------
    def mint(self, kind: str, title: str, gist: str, *, fungible: bool = False,
             id_: str | None = None) -> str:
        if kind not in KINDS:
            raise StateError(f"kind must be one of {KINDS}, got {kind!r}")
        if fungible and kind != "item":
            raise StateError("only items can be fungible")
        id_ = id_ or new_id()
        if self._doc_path(id_).exists():
            raise StateError(f"{id_} already exists")
        # Minting with name == id makes (kind, name) unique by construction.
        doc = Doc(kind=kind, id=id_, name=id_, gist=gist, title=title,
                  meta={"fungible": True} if fungible else {})
        self._write_doc(doc)
        self._commit(f"mint {kind} {title} ({id_})")
        return id_

    def _entry_path(self, id_: str) -> Path | None:
        hits = self.locate(id_)
        return self.root / hits[0].path if len(hits) == 1 else None

    def place(self, id_: str, container_id: str | None = None,
              quantity: int | None = None) -> None:
        doc = self.doc(id_)
        containers, _ = self.index()
        parent = self.root / TREE
        if container_id is not None:
            if container_id not in containers:
                raise StateError(f"container {container_id} is not in the tree")
            parent = self.root / containers[container_id]

        if quantity is not None:
            if not doc.fungible:
                raise StateError(f"{id_} is not fungible; quantity is meaningless")
            if quantity <= 0:
                raise StateError("quantity must be positive; check out instead")

        if doc.kind == "container":
            target = parent / doc.name
            target.mkdir(parents=True, exist_ok=True)
            write_lines(target / CONTAINER_MARKER, [f"id: {id_}"])
        else:
            if not doc.fungible and self.locate(id_):
                raise StateError(f"{id_} is not fungible and is already placed")
            lines = [f"id: {id_}"]
            if quantity:
                lines.append(f"quantity: {quantity}")
            write_lines(parent / doc.name, lines)

        where = self.doc(container_id).title if container_id else "the tree root"
        self._commit(f"place {doc.title} in {where}")

    def move(self, id_: str, to_container_id: str | None) -> None:
        doc = self.doc(id_)
        src = self._entry_path(id_)
        if src is None:
            raise StateError(f"{id_} is not placed exactly once; move is ambiguous")
        containers, _ = self.index()
        if to_container_id is not None:
            dst_dir = self.root / containers[to_container_id]
        else:
            dst_dir = self.root / TREE
        if doc.kind == "container" and dst_dir.is_relative_to(src):
            raise StateError("a container cannot be moved inside itself")
        self._git("mv", src.relative_to(self.root).as_posix(),
                  (dst_dir / doc.name).relative_to(self.root).as_posix())
        where = self.doc(to_container_id).title if to_container_id else "the tree root"
        self._commit(f"move {doc.title} to {where}")

    def check_out(self, id_: str) -> None:
        doc = self.doc(id_)
        src = self._entry_path(id_)
        if src is None:
            raise StateError(f"{id_} is not placed exactly once")
        if doc.kind == "container":
            # Checked out means "has no placement". A container cannot be
            # checked out and still hold things -- there would be nowhere for
            # its contents to live -- so taking it would delete their
            # placements too. Refuse instead, loudly.
            inside = [self.doc(p.id).title for p in self.contents(id_)]
            if inside:
                raise StateError(
                    f"{doc.title} still holds {len(inside)} thing(s): "
                    + ", ".join(sorted(inside))
                    + ". Empty it or move them first; checking it out would "
                    "drop their placements too.")
        self._git("rm", "-r", "-q", src.relative_to(self.root).as_posix())
        self._commit(f"check out {doc.title}")

    def set_quantity(self, id_: str, container_id: str, quantity: int) -> None:
        doc = self.doc(id_)
        if not doc.fungible:
            raise StateError(f"{id_} is not fungible")
        containers, _ = self.index()
        entry = self.root / containers[container_id] / doc.name
        if not entry.exists():
            raise StateError(f"{id_} is not in {container_id}")
        where = self.doc(container_id).title
        if quantity <= 0:
            # Zero is never written. Absent and zero must not be two spellings
            # of one state.
            self._git("rm", "-q", entry.relative_to(self.root).as_posix())
            self._commit(f"take the last {doc.title} out of {where}")
            return
        write_lines(entry, [f"id: {id_}", f"quantity: {quantity}"])
        self._commit(f"set {doc.title} to {quantity} in {where}")

    def rename(self, id_: str, name: str) -> None:
        if not NAME_RE.match(name):
            raise StateError(
                f"name must match {NAME_RE.pattern} -- lowercase, no spaces")
        doc = self.doc(id_)
        clash = next((d for d in self.docs().values()
                      if d.kind == doc.kind and d.name == name and d.id != id_),
                     None)
        if clash is not None:
            raise StateError(f"{doc.kind} {clash.id} is already named {name!r}")
        src = self._entry_path(id_)
        old = doc.name
        doc.name = name
        self._write_doc(doc)
        if src is not None:
            self._git("mv", src.relative_to(self.root).as_posix(),
                      (src.parent / name).relative_to(self.root).as_posix())
        self._commit(f"rename {old} to {name}")

    def last_action(self) -> str:
        return self._git("log", "-1", "--format=%s").strip()

    def undo(self) -> str:
        """Revert the last action, keeping it in the history.

        A revert rather than a reset, because the repo may already be pushed
        and because losing the record of a mistake loses the evidence of what
        actually happened to the physical thing. Reverting a revert is a redo.
        """
        if len(self._git("log", "--format=%h").split()) < 2:
            raise StateError("nothing to undo")
        subject = self.last_action()
        self._git("revert", "--no-edit", "--no-commit", "HEAD")
        self._git("commit", "-q", "-m", f"undo: {subject}")
        return subject

    # -- integrity ------------------------------------------------------
    def check(self) -> list[Problem]:
        docs = self.docs()
        _, placements = self.index()
        problems: list[Problem] = []
        seen: dict[str, list[Placement]] = {}
        for p in placements:
            seen.setdefault(p.id, []).append(p)

        for id_, hits in seen.items():
            doc = docs.get(id_)
            if doc is None:
                problems.append(Problem(
                    "orphan-placement", str(id_),
                    f"placed at {hits[0].path} but has no kb doc; "
                    "the label exists in the world, so mint one"))
                continue
            if len(hits) > 1 and not doc.fungible:
                problems.append(Problem(
                    "placed-twice", id_,
                    f"{doc.kind} is not fungible but appears at "
                    + ", ".join(h.path for h in hits)))
            for h in hits:
                if h.quantity is not None and not doc.fungible:
                    problems.append(Problem(
                        "quantity-on-non-fungible", id_,
                        f"{h.path} carries quantity {h.quantity}"))
                if h.quantity is not None and h.quantity <= 0:
                    problems.append(Problem(
                        "non-positive-quantity", id_,
                        f"{h.path} carries quantity {h.quantity}; "
                        "remove the placement instead"))
                entry = Path(h.path)
                tree_name = entry.parent.name if entry.name == CONTAINER_MARKER \
                    else entry.name
                if tree_name != doc.name:
                    problems.append(Problem(
                        "name-drift", id_,
                        f"tree says {tree_name!r}, kb says {doc.name!r}"))
        return problems
