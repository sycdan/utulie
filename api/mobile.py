"""The pages a phone lands on after scanning a label.

No framework, no build step, no CDN — the garage is exactly where a CDN fetch
fails. Scanning is the native camera app following the URL in the QR; the only
thing this has to do is be there when it arrives.
"""

from __future__ import annotations

ADD_CARD = """<button id="addBtn" onclick="openAdd()" aria-label="Add">+</button>
<div id="addSheet" class="sheet" onclick="if(event.target===this)closeAdd()">
  <div class="card">
    <h2>Add</h2>
    <div class="row" id="addKindRow">
      <button id="kindItemBtn" onclick="pickKind('item')">Item</button>
      <button id="kindContainerBtn" onclick="pickKind('container')">Container</button>
    </div>
    <input id="addTitle" class="field" placeholder="Title">
    <label class="row" id="addFungibleRow" style="display:none">
      <input type="checkbox" id="addFungible"> Stacking stock (fungible)
    </label>
    <input id="addPhoto" class="field" type="file" accept="image/*" capture="environment">
    <div class="row" style="margin-top:.8rem">
      <button id="addSaveBtn" class="primary" onclick="submitAdd()">Save</button>
      <button onclick="closeAdd()">Cancel</button>
    </div>
  </div>
</div>"""

SYNC_CARD = """<div id="syncSheet" class="sheet" onclick="if(event.target===this)closeSync()">
  <div class="card">
    <h2>Sync</h2>
    <p class="muted">Branch: <b id="syncBranch">?</b></p>
    <p class="muted" id="syncStatusLine">?</p>
    <div class="row" style="margin-top:.8rem">
      <button class="primary" onclick="doSync()">Sync now</button>
      <button onclick="closeSync()">Close</button>
    </div>
  </div>
</div>"""

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#f6f7f9" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#0f1216" media="(prefers-color-scheme: dark)">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black">
<link rel="apple-touch-icon" href="/icon.png">
<title>__TITLE__ · utulie</title>
<style>
  :root {
    color-scheme: light dark;
    --bg: #f6f7f9; --card: #fff; --ink: #14181d; --dim: #667;
    --line: #dfe3e8; --accent: #1f6feb; --warn: #b3261e;
  }
  @media (prefers-color-scheme: dark) {
    :root { --bg:#0f1216; --card:#181c22; --ink:#e8ecf1; --dim:#9aa4b2;
            --line:#2a313a; --accent:#5b9cf8; --warn:#f2776a; }
  }
  * { box-sizing: border-box; -webkit-tap-highlight-color: transparent; }
  body { margin:0; background:var(--bg); color:var(--ink); font:17px/1.45
         -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
         padding: 0 0 env(safe-area-inset-bottom); }
  main { max-width: 34rem; margin: 0 auto; padding: 1rem 1rem 4rem; }
  .card { background:var(--card); border:1px solid var(--line);
          border-radius:14px; padding:1rem; margin-bottom:.85rem; }
  h1 { font-size:1.55rem; margin:.1rem 0 .3rem; line-height:1.2; }
  h2 { font-size:1.05rem; margin:.1rem 0 .3rem; line-height:1.2; font-weight:650; }
  .gist { color:var(--dim); margin:0 0 .2rem; }
  .kind { display:inline-block; font-size:.72rem; letter-spacing:.08em;
          text-transform:uppercase; color:var(--dim); border:1px solid var(--line);
          border-radius:999px; padding:.1rem .55rem; }
  .big { font-size:1.9rem; font-weight:650; }
  .row { display:flex; gap:.5rem; flex-wrap:wrap; }
  button, select, input:not([type="checkbox"]), .btn {
    font: inherit; border-radius:11px; border:1px solid var(--line);
    background:var(--card); color:var(--ink); padding:.7rem .9rem;
    min-height:2.9rem; flex:1 1 auto; }
  button:active { transform: scale(.985); }
  button:disabled { opacity:.5; }
  .primary { background:var(--accent); border-color:var(--accent); color:#fff; }
  .danger { color:var(--warn); }
  ul { list-style:none; margin:.4rem 0 0; padding:0; }
  li { padding:.6rem 0; border-top:1px solid var(--line); }
  li:first-child { border-top:0; }
  li a { color:inherit; text-decoration:none; display:flex;
         justify-content:space-between; gap:.75rem; align-items:baseline; }
  .qty { color:var(--dim); font-variant-numeric:tabular-nums; }
  .muted { color:var(--dim); font-size:.9rem; }
  #flash { position:fixed; left:0; right:0; bottom:0; padding:.85rem 1rem;
           background:var(--accent); color:#fff; transform:translateY(100%);
           transition:transform .18s; z-index:20; }
  #flash.show { transform:none; }
  #flash.bad { background:var(--warn); }
  code { font-size:.82rem; color:var(--dim); word-break:break-all; }
  #topbar { position:sticky; top:0; z-index:6; background:var(--bg);
            padding:calc(.6rem + env(safe-area-inset-top)) 1rem .6rem;
            margin-bottom:.3rem; border-bottom:1px solid var(--line);
            display:flex; align-items:center; gap:.5rem; }
  #crumbScroll { flex:1 1 auto; min-width:0; overflow-x:auto; white-space:nowrap;
                 -webkit-overflow-scrolling:touch; }
  #crumbScroll a { color:var(--accent); text-decoration:none; font-weight:600; }
  #crumbScroll h1 { display:inline; font-size:1.05rem; font-weight:700; margin:0;
                     color:var(--ink); }
  #syncBtn { flex:0 0 auto; background:none; border:none; padding:0; min-height:auto;
             display:flex; align-items:center; gap:.2rem; color:var(--dim);
             font-size:1.15rem; }
  #syncBtn .count { font-size:.7rem; font-weight:700; color:var(--warn); }
  .photoBox { position:relative; aspect-ratio:4/3; border-radius:14px; overflow:hidden;
              margin-bottom:.85rem; background:var(--card); border:1px solid var(--line); }
  .photoBox img { width:100%; height:100%; object-fit:cover; display:none; }
  .photoPh { position:absolute; inset:0; display:flex; align-items:center;
             justify-content:center; color:var(--dim); font-size:.95rem;
             text-align:center; padding:1rem; }
  .photoBadge { position:absolute; right:.5rem; bottom:.5rem; width:2.1rem;
                height:2.1rem; border-radius:999px; background:rgba(0,0,0,.55);
                color:#fff; display:flex; align-items:center; justify-content:center;
                font-size:1.05rem; pointer-events:none; }
  #addBtn { position:fixed; right:1rem; bottom:calc(1rem + env(safe-area-inset-bottom));
            width:3.4rem; height:3.4rem; border-radius:999px; background:var(--accent);
            color:#fff; font-size:1.7rem; line-height:1; border:none;
            box-shadow:0 2px 10px rgba(0,0,0,.3); z-index:5; }
  .sheet { display:none; position:fixed; inset:0; background:rgba(0,0,0,.45); z-index:10; }
  .sheet.show { display:flex; align-items:flex-end; }
  .sheet .card { width:100%; margin:0; border-radius:16px 16px 0 0;
                 padding-bottom:calc(1rem + env(safe-area-inset-bottom)); }
  .field { width:100%; margin-top:.6rem; }
</style>
</head>
<body>
<nav id="topbar" aria-label="Breadcrumb">
  <div id="crumbScroll">__CRUMBTRAIL__</div>
  <button id="syncBtn" onclick="openSync()" aria-label="Sync status">
    ☁<span class="count" id="syncCount"></span>
  </button>
</nav>
<main>__BODY__</main>
<div id="flash"></div>
__ADD_CARD__
__SYNC_CARD__
<script>
const ID = "__ID__";
let head = "__HEAD__";
const ADD_HOME = __ADD_HOME__;
const ADD_ALLOW_ITEM = __ADD_ALLOW_ITEM__;
if (ADD_HOME === null) document.getElementById("addBtn").style.display = "none";

let addKind = ADD_ALLOW_ITEM ? null : "container";

function openAdd() {
  document.getElementById("addKindRow").style.display = ADD_ALLOW_ITEM ? "flex" : "none";
  document.getElementById("addSheet").className = "sheet show";
}

function closeAdd() {
  document.getElementById("addSheet").className = "sheet";
  document.getElementById("addTitle").value = "";
  document.getElementById("addPhoto").value = "";
  document.getElementById("addFungible").checked = false;
  addKind = ADD_ALLOW_ITEM ? null : "container";
  document.getElementById("addFungibleRow").style.display = "none";
  document.getElementById("kindItemBtn").className = "";
  document.getElementById("kindContainerBtn").className = "";
}

function pickKind(k) {
  addKind = k;
  document.getElementById("kindItemBtn").className = k === "item" ? "primary" : "";
  document.getElementById("kindContainerBtn").className = k === "container" ? "primary" : "";
  document.getElementById("addFungibleRow").style.display = k === "item" ? "flex" : "none";
}

async function downscale(file, maxDim, quality) {
  const bitmap = await createImageBitmap(file);
  const scale = Math.min(1, maxDim / Math.max(bitmap.width, bitmap.height));
  const w = Math.round(bitmap.width * scale), h = Math.round(bitmap.height * scale);
  const canvas = document.createElement("canvas");
  canvas.width = w; canvas.height = h;
  canvas.getContext("2d").drawImage(bitmap, 0, 0, w, h);
  return new Promise(res => canvas.toBlob(res, "image/jpeg", quality));
}

let addSubmitting = false;

async function submitAdd() {
  if (addSubmitting) return;   // a double-tap must not mint twice
  addSubmitting = true;
  const saveBtn = document.getElementById("addSaveBtn");
  saveBtn.disabled = true;
  try {
    if (ADD_ALLOW_ITEM && !addKind) return flash("Pick item or container", true);
    const title = document.getElementById("addTitle").value.trim();
    if (!title) return flash("Enter a title", true);
    const fungible = addKind === "item" && document.getElementById("addFungible").checked;
    const minted = await post("/things", { kind: addKind, title, gist: "", fungible });
    if (!minted) return;
    // ADD_HOME is "" for the tree root (a real, meaningful value -- place
    // with container: null), or an id; only null (button hidden) skips this.
    if (ADD_HOME !== null) {
      if (!(await post(`/things/${minted.id}/place`, { container: ADD_HOME || null }))) return;
    }
    const file = document.getElementById("addPhoto").files[0];
    if (file) {
      const blob = await downscale(file, 1600, 0.82);
      const fd = new FormData();
      fd.append("file", blob, "photo.jpg");
      fd.append("expect", head);
      const r = await fetch(`/things/${minted.id}/photo`, { method: "POST", body: fd });
      if (!r.ok) { flash("Minted, but the photo failed to attach", true);
                   setTimeout(() => location.href = `/m/${minted.id}`, 1500); return; }
    }
    location.href = `/m/${minted.id}`;
  } finally {
    addSubmitting = false;
    saveBtn.disabled = false;
  }
}

// Scroll the breadcrumb trail to its end so a long chain shows the current
// item, not "Home", without the pilot having to scroll it themselves.
(function scrollCrumbsToEnd() {
  const cs = document.getElementById("crumbScroll");
  if (cs) cs.scrollLeft = cs.scrollWidth;
})();

let syncStatus = null;

async function refreshSyncStatus() {
  try {
    const r = await fetch("/sync/status");
    syncStatus = await r.json();
    const el = document.getElementById("syncCount");
    // No upstream is a distinct, riskier state than "0 ahead" -- there is
    // nothing to compare against, so real commits could be sitting
    // unpushed with no way to detect it. Never render that as blank/clean.
    if (!syncStatus.upstream) el.textContent = "!";
    else el.textContent = syncStatus.ahead > 0 ? syncStatus.ahead : "";
  } catch (e) { /* offline or state repo not ready -- leave the badge blank */ }
}
refreshSyncStatus();

function openSync() {
  document.getElementById("syncBranch").textContent = syncStatus ? syncStatus.branch : "?";
  const line = document.getElementById("syncStatusLine");
  if (!syncStatus) line.textContent = "?";
  else if (!syncStatus.upstream) line.textContent = "Never pushed -- no remote branch to compare against.";
  else if (syncStatus.ahead > 0) line.textContent = `${syncStatus.ahead} commit(s) not yet pushed`;
  else line.textContent = "Up to date.";
  document.getElementById("syncSheet").className = "sheet show";
}

function closeSync() {
  document.getElementById("syncSheet").className = "sheet";
}

async function doSync() {
  const r = await fetch("/sync", { method: "POST", headers: {"content-type": "application/json"},
                                    body: "{}" });
  const d = await r.json().catch(() => ({}));
  if (!r.ok) return flash(d.detail || "Sync failed", true);
  flash("Synced");
  closeSync();
  refreshSyncStatus();
}

async function updatePhoto() {
  const file = document.getElementById("photoInput").files[0];
  if (!file) return;
  const blob = await downscale(file, 1600, 0.82);
  const fd = new FormData();
  fd.append("file", blob, "photo.jpg");
  fd.append("expect", head);
  const r = await fetch(`/things/${ID}/photo`, { method: "POST", body: fd });
  if (!r.ok) return flash("Photo upload failed", true);
  location.reload();
}

function flash(msg, bad) {
  const f = document.getElementById("flash");
  f.textContent = msg; f.className = "show" + (bad ? " bad" : "");
  setTimeout(() => f.className = "", bad ? 4500 : 1800);
}

async function act(url, opts) {
  try {
    const r = await fetch(url, opts);
    const d = await r.json().catch(() => ({}));
    if (!r.ok) {
      const m = d.detail && d.detail.error ? d.detail.error : (d.detail || r.statusText);
      flash(typeof m === "string" ? m : JSON.stringify(m), true);
      return null;
    }
    if (d.head) head = d.head;
    return d;
  } catch (e) { flash("Cannot reach utulie: " + e.message, true); return null; }
}

async function post(path, body) {
  return act(path, { method: "POST", headers: {"content-type": "application/json"},
                     body: JSON.stringify(Object.assign({expect: head}, body || {})) });
}

async function put(path, body) {
  return act(path, { method: "PUT", headers: {"content-type": "application/json"},
                     body: JSON.stringify(Object.assign({expect: head}, body || {})) });
}

async function editTitle() {
  const v = prompt("Title:", document.getElementById("idTitle").textContent);
  if (v === null || !v.trim()) return;
  if (await put(`/things/${ID}/title`, { title: v.trim() })) location.reload();
}

async function editGist() {
  const cur = document.getElementById("idGist").textContent;
  const v = prompt("Gist (one line):", cur === "(tap to add one)" ? "" : cur);
  if (v === null) return;
  if (await put(`/things/${ID}/gist`, { gist: v })) location.reload();
}

async function editName() {
  const v = prompt("Name (used in the tree path):", document.getElementById("idName").textContent);
  if (v === null || !v.trim()) return;
  if (await put(`/things/${ID}/name`, { name: v.trim() })) location.reload();
}

async function checkOut() {
  if (!confirm("Check this out of its container?")) return;
  if (await post(`/things/${ID}/check-out?expect=${head}`)) location.reload();
}

async function printThing(btn, media) {
  const text = prompt("Caption to print next to the QR (blank uses the quid):", btn.dataset.title || "");
  if (text === null) return;
  btn.disabled = true;
  try {
    const qs = new URLSearchParams({media, text});
    if (await act(`/things/${ID}/print?${qs}`, { method: "POST" })) flash("Printed");
  } finally {
    btn.disabled = false;
  }
}

async function deleteThing() {
  if (!confirm("Delete this for good? Can't be undone -- for a real thing you "
               + "just want out of a container, use Check out instead.")) return;
  if (await act(`/things/${ID}?expect=${head}`, { method: "DELETE" })) location.href = "/m";
}

async function moveTo(sel) {
  if (!sel.value) return;
  if (await post(`/things/${ID}/place`, { container: sel.value || null })) location.reload();
}

async function setQty(container) {
  const n = parseInt(document.getElementById("qtyInput").value, 10);
  if (isNaN(n) || n < 0) return flash("Enter a count of 0 or more", true);
  if (n === 0 && !confirm("Set to 0? That removes it from here.")) return;
  if (await post(`/things/${ID}/place`, { container, quantity: n })) location.reload();
}

function markHere() {
  if (!navigator.geolocation) return flash("No geolocation on this device", true);
  flash("Getting a fix…");
  navigator.geolocation.getCurrentPosition(async p => {
    const r = await act(`/things/${ID}/position`, {
      method: "PUT", headers: {"content-type": "application/json"},
      body: JSON.stringify({ lat: p.coords.latitude, lon: p.coords.longitude,
                             expect: head })});
    if (r) location.reload();
  }, e => flash("Location failed: " + e.message, true), { enableHighAccuracy: true, timeout: 15000 });
}

// Distance is worked out on the phone: the server has no idea where you are.
(function showDistance() {
  const el = document.getElementById("dist");
  if (!el || !navigator.geolocation) return;
  const lat = parseFloat(el.dataset.lat), lon = parseFloat(el.dataset.lon);
  navigator.geolocation.getCurrentPosition(p => {
    const R = 6371008.8, t = x => x * Math.PI / 180;
    const dp = t(lat - p.coords.latitude), dl = t(lon - p.coords.longitude);
    const h = Math.sin(dp/2)**2 + Math.cos(t(p.coords.latitude)) * Math.cos(t(lat))
              * Math.sin(dl/2)**2;
    const m = 2 * R * Math.asin(Math.sqrt(h));
    el.textContent = m < 1000 ? Math.round(m) + " m away" : (m/1000).toFixed(1) + " km away";
  }, () => { el.textContent = ""; }, { enableHighAccuracy: true, timeout: 15000 });
})();
</script>
</body>
</html>
"""


def render(title: str, body: str, id_: str = "", head: str = "",
           add_home: str | None = None, add_allow_item: bool = False,
           crumbtrail: str = "") -> str:
    """add_home is the container a new thing should land in: an id, "" for
    the tree root, or None to hide the add button entirely (an unknown-thing
    page, or an item's own page, where "add inside this" makes no sense).

    crumbtrail is pre-built header HTML: ancestor links plus the current
    thing as a trailing bold, non-link segment -- doubles as the page's
    title, since a big duplicate <h1> right below it added nothing. Empty on
    the /m root itself, the top of the hierarchy, which has nothing above it
    to show -- the header (and its sync button) still renders, just with an
    empty crumb area."""
    return (PAGE.replace("__TITLE__", esc(title)).replace("__BODY__", body)
                .replace("__ID__", id_).replace("__HEAD__", head)
                .replace("__ADD_CARD__", ADD_CARD).replace("__SYNC_CARD__", SYNC_CARD)
                .replace("__CRUMBTRAIL__", crumbtrail)
                .replace("__ADD_HOME__", "null" if add_home is None else f'"{esc(add_home)}"')
                .replace("__ADD_ALLOW_ITEM__", "true" if add_allow_item else "false"))


def esc(s: str) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))
