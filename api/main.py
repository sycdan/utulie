"""HTTP front for a utulie state repo.

Interactive docs at /docs — that is the interface, there is no UI yet.

    UTULIE_STATE=/path/to/state uvicorn api.main:app --reload

Every mutating call makes exactly one commit in the state repo. Pushing is
explicit: POST /sync.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.responses import PlainTextResponse, RedirectResponse
from pydantic import BaseModel, Field

from state import DriftError, StateError, StateRepo, distance_m

STATE = Path(os.environ.get("UTULIE_STATE", "./state-repo")).resolve()

app = FastAPI(
    title="utulie",
    description=(
        "Photograph a thing, mint a quid, print a QR label, scan it to find the "
        "thing again. State lives in a git repo you own.\n\n"
        f"Reading and writing `{STATE}`."
    ),
    version="0",
)


def repo() -> StateRepo:
    if not (STATE / "kb").exists():
        raise HTTPException(503, f"no state repo at {STATE}; POST /init first")
    return StateRepo(STATE)


@app.exception_handler(StateError)
def _state_error(_request, exc: StateError):
    raise HTTPException(400, str(exc))


def guard(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except DriftError as e:
        # 409: the caller's view is stale, not malformed. Re-read and retry.
        raise HTTPException(409, {"error": str(e), "expected": e.expected,
                                  "head": e.actual}) from e
    except StateError as e:
        raise HTTPException(400, str(e)) from e


EXPECT = Field(
    None,
    description="The `head` you read before acting. Refused with 409 if the repo "
                "has moved since. Omit to write unconditionally.",
)


# -- models ------------------------------------------------------------
class NewThing(BaseModel):
    kind: str = Field("item", pattern="^(item|container)$")
    title: str = Field(..., description="Human title, becomes the `# h1`")
    gist: str = Field("", description="What this thing is, in one line")
    fungible: bool = Field(
        False, description="Stacking stock. Items only; quantity lives on each placement"
    )
    id: str | None = Field(None, description="Reuse an existing quid instead of minting")
    expect: str | None = EXPECT


class Placing(BaseModel):
    container: str | None = Field(None, description="Container id, or null for the tree root")
    quantity: int | None = Field(
        None,
        description="Fungible items only. Sets the count in this container, "
                    "it does not add to it -- so a replayed offline action "
                    "cannot double it.",
    )
    expect: str | None = EXPECT


class Naming(BaseModel):
    name: str = Field(..., description="Lowercase, path-safe. Unique within the kind")
    expect: str | None = EXPECT


class Position(BaseModel):
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)
    expect: str | None = EXPECT


class Quantity(BaseModel):
    container: str
    quantity: int = Field(
        ..., description="The new count in this container. 0 removes the placement."
    )
    expect: str | None = EXPECT


# -- read --------------------------------------------------------------
@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/docs")


@app.get("/things", summary="Every thing that has an identity")
def things():
    r = repo()
    _, placements = r.index()
    placed = {p.id for p in placements}
    return {"head": r.head(), "things": [
        {
            "id": d.id,
            "kind": d.kind,
            "name": d.name,
            "title": d.title,
            "gist": d.gist,
            "fungible": d.fungible,
            "placed": d.id in placed,
        }
        for d in r.docs().values()
    ]}


def _here(from_: str | None) -> dict | None:
    if not from_:
        return None
    try:
        lat, lon = (float(x) for x in from_.split(","))
    except ValueError:
        raise HTTPException(422, "from must look like 'lat,lon'")
    return {"lat": lat, "lon": lon}


def _where(r: StateRepo, id: str, here: dict | None) -> dict:
    """Position, who supplied it, and how far off it is from `here`."""
    found = r.position_of(id)
    if found is None:
        return {"position": None}
    pos, source = found
    out = {"position": pos, "known_from": {"id": source.id, "title": source.title}}
    if here:
        out["distance_m"] = distance_m(here, pos)
    return out


@app.get("/things/{id}", summary="One thing: what it is, and where")
def thing(id: str, from_: str | None = Query(
        None, alias="from", description="Your position as 'lat,lon', to get a distance")):
    r = repo()
    doc = guard(r.doc, id)
    return {
        "id": doc.id,
        "kind": doc.kind,
        "name": doc.name,
        "title": doc.title,
        "gist": doc.gist,
        "fungible": doc.fungible,
        "meta": doc.meta,
        "home": [
            {"id": c.id, "title": c.title} for c in r.path_of(id)
        ],
        "placements": [
            {"path": p.path, "container": p.container, "quantity": p.quantity}
            for p in r.locate(id)
        ],
        **_where(r, id, _here(from_)),
        "head": r.head(),
    }


@app.get("/containers/{id}/contents", summary="What calls this container home")
def contents(id: str, from_: str | None = Query(
        None, alias="from", description="Your position as 'lat,lon'")):
    r = repo()
    guard(r.doc, id)
    here = _here(from_)
    out = []
    for p in r.contents(id):
        d = r.doc(p.id)
        out.append(
            {"id": d.id, "kind": d.kind, "title": d.title, "gist": d.gist,
             "quantity": p.quantity, **_where(r, d.id, here)}
        )
    return {"head": r.head(), "contents": out}


@app.put("/things/{id}/position", summary="Record where a thing was last seen")
def set_position(id: str, body: Position):
    r = repo()
    guard(r.set_position, id, body.lat, body.lon, expect=body.expect)
    return {"ok": True, "head": r.head()}


@app.get("/tree", response_class=PlainTextResponse,
         summary="The whole tree, as a human would draw it")
def tree():
    r = repo()
    containers, placements = r.index()
    docs = r.docs()
    kids: dict[str | None, list] = {}
    for p in placements:
        kids.setdefault(p.container, []).append(p)

    lines: list[str] = []

    def walk(parent, depth):
        for p in sorted(kids.get(parent, []), key=lambda x: str(x.id)):
            d = docs.get(p.id)
            label = f"{d.title} [{d.name}]" if d else f"UNKNOWN {p.id}"
            if p.quantity is not None:
                label += f" x{p.quantity}"
            lines.append("  " * depth + ("+ " if p.id in containers else "- ") + label)
            if p.id in containers:
                walk(p.id, depth + 1)

    walk(None, 0)
    unplaced = [d for d in docs.values() if not r.locate(d.id)]
    if unplaced:
        lines.append("")
        lines.append("checked out (no placement):")
        lines += [f"  - {d.title} [{d.name}]" for d in unplaced]
    return "\n".join(lines) or "(empty)"


@app.get("/check", summary="Integrity problems, empty when healthy")
def check():
    r = repo()
    return {"head": r.head(),
            "problems": [{"kind": p.kind, "id": p.id, "detail": p.detail}
                         for p in r.check()]}


# -- write -------------------------------------------------------------
@app.post("/init", summary="Create an empty state repo at UTULIE_STATE")
def init():
    r = StateRepo(STATE)
    STATE.mkdir(parents=True, exist_ok=True)
    r.init()
    return {"state": str(STATE)}


@app.post("/things", summary="Mint a thing (name starts out equal to its id)")
def mint(body: NewThing):
    r = repo()
    id_ = guard(r.mint, body.kind, body.title, body.gist,
                fungible=body.fungible, id_=body.id, expect=body.expect)
    return {"id": id_, "head": r.head()}


@app.post("/things/{id}/place",
          summary="Put a thing somewhere. Moves it if it was elsewhere")
def place(id: str, body: Placing):
    r = repo()
    guard(r.place, id, body.container, body.quantity, expect=body.expect)
    return {"ok": True, "head": r.head()}


@app.post("/things/{id}/check-out", summary="Take it out; the doc survives")
def check_out(id: str, expect: str | None = Query(None, description="Head you read")):
    r = repo()
    guard(r.check_out, id, expect=expect)
    return {"ok": True, "head": r.head()}


@app.put("/things/{id}/quantity", summary="Set a fungible item's count in one container")
def set_quantity(id: str, body: Quantity):
    r = repo()
    guard(r.set_quantity, id, body.container, body.quantity, expect=body.expect)
    return {"ok": True, "head": r.head()}


@app.put("/things/{id}/name", summary="Rename: kb field and tree entry, one commit")
def rename(id: str, body: Naming):
    r = repo()
    guard(r.rename, id, body.name, expect=body.expect)
    return {"ok": True, "head": r.head()}


@app.get("/last-action", summary="What the most recent action was")
def last_action():
    r = repo()
    return {"head": r.head(), "action": r.last_action()}


@app.post("/undo", summary="Reverse the last action")
def undo(expect: str | None = Query(None, description="Head you read")):
    r = repo()
    return {"undone": guard(r.undo, expect=expect), "head": r.head()}


@app.post("/sync", summary="Push the state repo to its remote")
def sync(remote: str = Body("origin", embed=True)):
    env = dict(os.environ)
    if key := os.environ.get("UTULIE_SSH_KEY"):
        env["GIT_SSH_COMMAND"] = f"ssh -i {key} -o IdentitiesOnly=yes"
    out = subprocess.run(
        ["git", "push", remote, "HEAD"], cwd=STATE, capture_output=True,
        text=True, env=env,
    )
    if out.returncode:
        raise HTTPException(400, out.stderr.strip())
    return {"pushed": out.stderr.strip() or "already up to date"}
