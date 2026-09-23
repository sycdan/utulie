"""HTTP front for a utulie state repo.

Interactive docs at /docs — that is the interface, there is no UI yet.

    UTULIE_STATE=/path/to/state uvicorn api.main:app --reload

Every mutating call makes exactly one commit in the state repo. Pushing is
explicit: POST /sync.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import uuid
from pathlib import Path

from fastapi import (Body, FastAPI, Form, HTTPException, Query, Response,
                     UploadFile, WebSocket, WebSocketDisconnect)
from fastapi.responses import (HTMLResponse, PlainTextResponse,
                               RedirectResponse)
from pydantic import BaseModel, Field

from api.code import decode
from api.mobile import esc, render
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


def thing_icon(kind: str, fungible: bool) -> str:
    if kind == "container":
        return "📦"
    return "🔢" if fungible else "🏷️"


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
    name: str = Field(
        ...,
        description="Slugified to lowercase alphanumerics and single dashes, so "
                    "what comes back may differ from what you send. Must be "
                    "unique within the kind.",
    )
    expect: str | None = EXPECT


class Titling(BaseModel):
    title: str = Field(..., description="The human-facing `# h1`")
    expect: str | None = EXPECT


class Gisting(BaseModel):
    gist: str = Field(..., description="What this thing is, in one line")
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
@app.get("/health", include_in_schema=False)
def health():
    """Container healthcheck and ingress liveness probe. Deliberately does not
    touch the state repo -- a broken UTULIE_STATE should not read as the
    process being down; that is what /check is for."""
    return {"ok": True}


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/m")


@app.get("/ca.crt", include_in_schema=False)
def dev_ca():
    """Bootstrap only: fetch this over plain HTTP once, trust it on the phone,
    then use the HTTPS port. Camera and geolocation both require a secure
    context, which a bare LAN IP over HTTP cannot be."""
    ca = os.environ.get("UTULIE_DEV_CA")
    if not ca or not Path(ca).exists():
        raise HTTPException(404, "no dev CA configured (UTULIE_DEV_CA)")
    return Response(Path(ca).read_bytes(), media_type="application/x-x509-ca-cert")


@app.get("/icon.png", include_in_schema=False)
def app_icon():
    """Home-screen icon for Add to Home Screen -- without this iOS falls back
    to rendering a giant first letter of the page title on a solid
    background."""
    icon = Path(__file__).parent / "static" / "icon-180.png"
    return Response(icon.read_bytes(), media_type="image/png")


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


@app.post("/things/{id}/photo", summary="Attach or replace a thing's photo")
async def upload_photo(id: str, file: UploadFile, expect: str | None = Form(None)):
    r = repo()
    guard(r.set_photo, id, await file.read(), expect=expect)
    return {"ok": True, "head": r.head()}


@app.get("/things/{id}/photo", include_in_schema=False)
def get_photo(id: str):
    r = repo()
    data = r.photo(id)
    if data is None:
        raise HTTPException(404, "no photo")
    return Response(data, media_type="image/jpeg")


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


@app.delete("/things/{id}",
            summary="Erase a mis-minted thing. Not the same as checking it out")
def delete(id: str, expect: str | None = Query(None, description="Head you read")):
    r = repo()
    guard(r.delete, id, expect=expect)
    return {"ok": True, "head": r.head()}


@app.put("/things/{id}/quantity", summary="Set a fungible item's count in one container")
def set_quantity(id: str, body: Quantity):
    r = repo()
    guard(r.set_quantity, id, body.container, body.quantity, expect=body.expect)
    return {"ok": True, "head": r.head()}


@app.put("/things/{id}/name", summary="Rename: kb field and tree entry, one commit")
def rename(id: str, body: Naming):
    r = repo()
    name = guard(r.rename, id, body.name, expect=body.expect)
    return {"ok": True, "name": name, "head": r.head()}


@app.put("/things/{id}/title", summary="Edit the human-facing title")
def set_title(id: str, body: Titling):
    r = repo()
    guard(r.set_title, id, body.title, expect=body.expect)
    return {"ok": True, "head": r.head()}


@app.put("/things/{id}/gist", summary="Edit the one-line gist")
def set_gist(id: str, body: Gisting):
    r = repo()
    guard(r.set_gist, id, body.gist, expect=body.expect)
    return {"ok": True, "head": r.head()}


@app.get("/last-action", summary="What the most recent action was")
def last_action():
    r = repo()
    return {"head": r.head(), "action": r.last_action()}


@app.post("/undo", summary="Reverse the last action")
def undo(expect: str | None = Query(None, description="Head you read")):
    r = repo()
    return {"undone": guard(r.undo, expect=expect), "head": r.head()}


@app.get("/sync/status", summary="Current branch and how far ahead of its upstream")
def sync_status():
    return repo().sync_status()


@app.post("/sync", summary="Pull (fast-forward only), then push the state repo to its remote")
def sync(remote: str = Body("origin", embed=True)):
    env = dict(os.environ)
    if key := os.environ.get("UTULIE_SSH_KEY"):
        # A bind-mounted secret carries whatever permissions the host
        # filesystem gives it -- on an NTFS source (Docker Desktop on
        # Windows) that is always wide open, and OpenSSH's client refuses to
        # load a private key with open permissions. There is no client-side
        # override for that refusal; the fix is a real chmod, which has to
        # happen on the container's own filesystem, not the host mount.
        local_key = Path("/tmp/utulie-deploy-key")
        local_key.write_bytes(Path(key).read_bytes())
        local_key.chmod(0o600)
        env["GIT_SSH_COMMAND"] = f"ssh -i {local_key} -o IdentitiesOnly=yes"

    # Sync only ever pushed, so a clone that never runs the app's own mints --
    # production is not the only writer to a branch once a dev clone targets
    # the same remote -- goes stale until someone notices and pulls by hand.
    # Found live: htpc's own clone sat 4 commits behind after a rebase pushed
    # from elsewhere, and a real container's contents were invisible until a
    # manual fast-forward. Pull first, ff-only -- a real divergence needs a
    # human to resolve, not a silent rebase from a button tap.
    branch = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"],
                             cwd=STATE, capture_output=True, text=True).stdout.strip()
    fetch = subprocess.run(["git", "fetch", remote, branch], cwd=STATE,
                            capture_output=True, text=True, env=env)
    if fetch.returncode == 0:
        pull = subprocess.run(["git", "merge", "--ff-only", "FETCH_HEAD"], cwd=STATE,
                               capture_output=True, text=True, env=env)
        if pull.returncode:
            raise HTTPException(
                409, f"remote has diverged -- pull/rebase manually first: {pull.stderr.strip()}")

    out = subprocess.run(
        # -u: a branch pushed for the first time (a fresh dev clone's branch,
        # for instance) needs upstream tracking set, or sync_status can never
        # tell "0 ahead" from "no remote to compare against at all" -- the
        # exact confusion that surfaced testing this live.
        ["git", "push", "-u", remote, "HEAD"], cwd=STATE, capture_output=True,
        text=True, env=env,
    )
    if out.returncode:
        raise HTTPException(400, out.stderr.strip())
    return {"pushed": out.stderr.strip() or "already up to date"}


# -- labels --------------------------------------------------------------
# Spike: prove an outbound websocket from dan-pc can carry a print job at
# all, before investing in labels as a separate service. One relay client
# at a time -- the physical printer only exists in one place, so "whichever
# client is connected" is unambiguous. No persistent queue: a job sent with
# nobody connected just fails, which is fine for proving the concept.
_relay: WebSocket | None = None
_pending: dict[str, asyncio.Future] = {}


@app.websocket("/labels/ws")
async def labels_ws(ws: WebSocket):
    global _relay
    await ws.accept()
    _relay = ws
    try:
        while True:
            msg = json.loads(await ws.receive_text())
            fut = _pending.pop(msg["job_id"], None)
            if fut and not fut.done():
                fut.set_result(msg)
    except WebSocketDisconnect:
        pass
    finally:
        if _relay is ws:
            _relay = None


@app.post("/things/{id}/print", summary="Print a label via the connected dan-pc relay client")
async def print_thing(id: str, media: str = Query(..., description="Media name, e.g. item-50x30"),
                       text: str = Query("", description="Caption printed next to the QR; defaults to the quid")):
    guard(repo().doc, id)
    if _relay is None:
        raise HTTPException(503, "no print client connected")
    job_id = uuid.uuid4().hex
    fut = asyncio.get_event_loop().create_future()
    _pending[job_id] = fut
    await _relay.send_text(json.dumps({"job_id": job_id, "id": id, "media": media, "text": text}))
    try:
        result = await asyncio.wait_for(fut, timeout=30)
    except TimeoutError:
        _pending.pop(job_id, None)
        raise HTTPException(504, "print client did not respond in time")
    if not result.get("ok"):
        raise HTTPException(502, result.get("error") or "print failed")
    return {"ok": True}


# -- phone -------------------------------------------------------------
@app.get("/q/{code}", include_in_schema=False)
@app.get("/Q/{code}", include_in_schema=False)
def scanned(code: str):
    """Where a scanned label lands. The QR carries a crockford-encoded quid.

    Both cases of the path segment are routed: QR alphanumeric mode only has
    uppercase, so every printed label's URL is .../Q/<code>. Path segments are
    case-sensitive in Starlette, so without this a printed label 404s -- found
    by checking before printing rather than after.
    """
    try:
        return RedirectResponse(f"/m/{decode(code)}", status_code=302)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e


@app.get("/m", response_class=HTMLResponse, include_in_schema=False)
def phone_index():
    r = repo()
    containers, placements = r.index()
    nested = {p.id for p in placements if p.container is not None}
    top = [c for c in containers if c not in nested]
    rows = "".join(
        f'<li><a href="/m/{c}"><span>{esc(r.doc(c).title)}</span>'
        f'<span class="qty">{len(r.contents(c))}</span></a></li>'
        for c in sorted(top, key=lambda c: r.doc(c).title.lower())
    )
    body = (f'<div class="card"><h1>Containers</h1>'
            f'<ul>{rows or "<li class=muted>Nothing yet</li>"}</ul></div>')
    return HTMLResponse(render("Containers", body, head=r.head(),
                                add_home="", add_allow_item=False))


@app.get("/m/{id}", response_class=HTMLResponse, include_in_schema=False)
def phone_thing(id: str):
    r = repo()
    try:
        doc = r.doc(id)
    except StateError:
        body = (f'<div class="card"><h1>Not in this repo</h1>'
                f'<p class="gist">Nothing here has the id below. If the label is '
                f'real, the thing needs minting.</p><code>{esc(id)}</code></div>')
        return HTMLResponse(
            render("Unknown", body, id, r.head(),
                   crumbtrail='<a href="/m">Home</a> › <b>Unknown</b>'),
            status_code=404)

    chain = r.path_of(id)
    placements = r.locate(id)
    qty = next((p.quantity for p in placements if p.quantity), None)

    found = r.position_of(id)
    if found:
        pos, source = found
        via = "" if source.id == id else f" · via {esc(source.title)}"
        where = (f'<div class="big" id="dist" data-lat="{pos["lat"]}" '
                 f'data-lon="{pos["lon"]}">…</div>'
                 f'<div class="muted">last seen {esc(pos["at"][:10])}{via}</div>')
    else:
        where = '<div class="muted">No position recorded anywhere above it.</div>'

    here_qty = next((p for p in placements if p.container is not None), None)
    qty_row = ""
    if doc.fungible and here_qty is not None:
        qty_row = (
            f'<div class="row" style="margin-top:.5rem">'
            f'<input id="qtyInput" type="number" inputmode="numeric" min="0" '
            f'value="{here_qty.quantity or 0}" style="flex:0 0 6rem">'
            f'<button onclick="setQty(&quot;{here_qty.container}&quot;)">'
            f'Set count here</button></div>'
        )
    opts = "".join(
        f'<option value="{c}">{esc(r.doc(c).title)}</option>'
        for c in r.index()[0] if c != id
    )
    if doc.kind == "container":
        def _kid_row(p):
            d = r.doc(p.id)
            icon = thing_icon(d.kind, d.fungible)
            qty = p.quantity if p.quantity else ""
            return (f'<li><a href="/m/{p.id}"><span>{icon} {esc(d.title)}</span>'
                    f'<span class="qty">{qty}</span></a></li>')
        kids = "".join(
            _kid_row(p)
            for p in sorted(r.contents(id), key=lambda p: r.doc(p.id).title.lower())
        )
        inside = (f'<div class="card"><h2>Contains</h2><ul>{kids}</ul></div>'
                  if kids else
                  '<div class="card"><h2>Contains</h2>'
                  '<p class="muted">Empty. Room for something.</p></div>')
    else:
        inside = ""

    photo = f"""
<div class="photoBox" onclick="document.getElementById('photoInput').click()">
  <img id="photoImg" src="/things/{id}/photo" alt=""
       onload="this.style.display='block';document.getElementById('photoPh').style.display='none'"
       onerror="this.style.display='none'">
  <div id="photoPh" class="photoPh">Tap to add a photo</div>
  <div class="photoBadge">📷</div>
</div>
<input id="photoInput" type="file" accept="image/*" capture="environment"
       style="display:none" onchange="updatePhoto()">
"""
    body = f"""
{photo}
<div class="card">
  {'<span class="kind">Stock</span>' if doc.fungible else ''}
  <p class="gist" onclick="editGist()" style="cursor:pointer">
    <span id="idGist">{esc(doc.gist) or "Tap to add a description"}</span></p>
  {f'<p class="muted"><b>{qty}</b> here</p>' if qty else ''}
</div>
<div class="card">{where}
  <div class="row" style="margin-top:.8rem">
    <button onclick="markHere()">I am at this thing</button>
  </div>
</div>
{inside}
<div class="card">
  <h2>Put it somewhere</h2>
  <div class="row">
    <select onchange="moveTo(this)">
      <option value="">Move to…</option>{opts}
    </select>
  </div>
  {qty_row}
  <div class="row" style="margin-top:.5rem">
    {'<button class="danger" onclick="checkOut()">Check out</button>' if placements else ''}
    <button class="danger" onclick="deleteThing()">Delete</button>
  </div>
</div>
<div class="card">
  <h2>Identification</h2>
  <p class="muted" onclick="editName()" style="cursor:pointer">
    Name: <span id="idName">{esc(doc.name)}</span></p>
  <p style="margin:.5rem 0 0"><code>{esc(id)}</code></p>
  <div class="row" style="margin-top:.8rem">
    <select id="printMedia">
      <option value="item-50x30" {"selected" if doc.kind != "container" else ""}>Item (50×30)</option>
      <option value="container-40x70" {"selected" if doc.kind == "container" else ""}>Big bin (40×70)</option>
      <option value="container-50x50-round">Round (50×50)</option>
    </select>
    <button data-title="{esc(doc.title)}"
            onclick="printThing(this, document.getElementById('printMedia').value)">🖨️ Print label</button>
  </div>
</div>
"""
    add_home = id if doc.kind == "container" else None
    ancestors = "".join(f'<a href="/m/{c.id}">{esc(c.title)}</a> › ' for c in chain)
    icon = thing_icon(doc.kind, doc.fungible)
    crumbtrail = (f'<a href="/m">Home</a> › {ancestors}'
                  f'<h1 onclick="editTitle()" style="cursor:pointer">'
                  f'{icon} <span id="idTitle">{esc(doc.title)}</span></h1>')
    return HTMLResponse(render(doc.title, body, id, r.head(),
                                add_home=add_home, add_allow_item=True,
                                crumbtrail=crumbtrail))
