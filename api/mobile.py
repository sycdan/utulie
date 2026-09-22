"""The pages a phone lands on after scanning a label.

No framework, no build step, no CDN — the garage is exactly where a CDN fetch
fails. Scanning is the native camera app following the URL in the QR; the only
thing this has to do is be there when it arrives.
"""

from __future__ import annotations

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#111418">
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
         padding: env(safe-area-inset-top) 0 env(safe-area-inset-bottom); }
  main { max-width: 34rem; margin: 0 auto; padding: 1rem 1rem 4rem; }
  .card { background:var(--card); border:1px solid var(--line);
          border-radius:14px; padding:1rem; margin-bottom:.85rem; }
  h1 { font-size:1.55rem; margin:.1rem 0 .3rem; line-height:1.2; }
  .gist { color:var(--dim); margin:0 0 .2rem; }
  .kind { display:inline-block; font-size:.72rem; letter-spacing:.08em;
          text-transform:uppercase; color:var(--dim); border:1px solid var(--line);
          border-radius:999px; padding:.1rem .55rem; }
  .crumbs { color:var(--dim); font-size:.95rem; }
  .crumbs a { color:var(--accent); text-decoration:none; }
  .big { font-size:1.9rem; font-weight:650; }
  .row { display:flex; gap:.5rem; flex-wrap:wrap; }
  button, select, .btn {
    font: inherit; border-radius:11px; border:1px solid var(--line);
    background:var(--card); color:var(--ink); padding:.7rem .9rem;
    min-height:2.9rem; flex:1 1 auto; }
  button:active { transform: scale(.985); }
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
           transition:transform .18s; }
  #flash.show { transform:none; }
  #flash.bad { background:var(--warn); }
  code { font-size:.82rem; color:var(--dim); word-break:break-all; }
</style>
</head>
<body>
<main>__BODY__</main>
<div id="flash"></div>
<script>
const ID = "__ID__";
let head = "__HEAD__";

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

async function checkOut() {
  if (!confirm("Check this out of its container?")) return;
  if (await post(`/things/${ID}/check-out?expect=${head}`)) location.reload();
}

async function moveTo(sel) {
  if (!sel.value) return;
  if (await post(`/things/${ID}/place`, { container: sel.value || null })) location.reload();
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


def render(title: str, body: str, id_: str = "", head: str = "") -> str:
    return (PAGE.replace("__TITLE__", title).replace("__BODY__", body)
                .replace("__ID__", id_).replace("__HEAD__", head))


def esc(s: str) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))
