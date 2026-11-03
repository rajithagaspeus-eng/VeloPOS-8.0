// VeloPOS owner-dashboard Worker. Deploy: see README_CLOUD.txt
import DASH_HTML from "./dashboard_html.js";

const enc = new TextEncoder();
const MAX_BODY = 64000, SKEW = 600;
const SHOP_RE = /^[0-9a-f]{16}$/, HASH_RE = /^[0-9a-f]{64}$/;
const SEC = { "Cache-Control": "no-store", "Referrer-Policy": "no-referrer", "X-Content-Type-Options": "nosniff" };

const json = (o, status = 200) => new Response(JSON.stringify(o), { status, headers: { "Content-Type": "application/json", ...SEC } });
const now = () => Math.floor(Date.now() / 1000);

function b64u(s) {
  s = s.replace(/-/g, "+").replace(/_/g, "/"); while (s.length % 4) s += "=";
  const bin = atob(s); const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}
async function sha256hex(s) {
  const d = new Uint8Array(await crypto.subtle.digest("SHA-256", enc.encode(s)));
  return [...d].map(b => b.toString(16).padStart(2, "0")).join("");
}
function same(a, b) {            // constant-time string compare
  if (typeof a !== "string" || typeof b !== "string" || a.length !== b.length) return false;
  let r = 0; for (let i = 0; i < a.length; i++) r |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return r === 0;
}
async function verify(pubB64, sigB64, data) {
  try {
    const pub = b64u(pubB64); if (pub.length !== 32) return false;
    const key = await crypto.subtle.importKey("raw", pub, { name: "Ed25519" }, false, ["verify"]);
    return await crypto.subtle.verify({ name: "Ed25519" }, key, b64u(sigB64), data);
  } catch { return false; }
}

async function handlePush(req, env) {
  const shop = req.headers.get("X-Shop") || "", ts = parseInt(req.headers.get("X-Ts") || "0", 10);
  const pub = req.headers.get("X-Pub") || "", sig = req.headers.get("X-Sig") || "";
  const invite = (req.headers.get("X-Invite") || "").toUpperCase().replace(/[^A-Z0-9]/g, "");
  if (!SHOP_RE.test(shop) || !pub || !sig) return json({ error: "bad_request" }, 400);
  if (Math.abs(now() - ts) > SKEW) return json({ error: "clock" }, 400);
  const buf = new Uint8Array(await req.arrayBuffer());
  if (buf.length > MAX_BODY) return json({ error: "too_large" }, 413);
  const msg = new Uint8Array([...enc.encode(ts + "."), ...buf]);
  if (!(await verify(pub, sig, msg))) return json({ error: "bad_signature" }, 401);   // checked BEFORE any invite is used up

  let snap;
  try { snap = JSON.parse(new TextDecoder().decode(buf)); } catch { return json({ error: "bad_json" }, 400); }
  if (!snap || snap.v !== 1 || !HASH_RE.test(snap.view_hash || "")) return json({ error: "bad_snapshot" }, 400);

  let row = await env.DB.prepare("SELECT pub, exp FROM shops WHERE shop_id=?").bind(shop).first();
  if (invite) {
    const inv = await env.DB.prepare("DELETE FROM invites WHERE code=? RETURNING days").bind(invite).first();   // atomic: one use only
    if (!inv) return json({ error: "invalid_invite" }, 403);
    const exp = Math.max(row ? row.exp : 0, now()) + inv.days * 86400;
    await env.DB.prepare("INSERT INTO shops(shop_id, pub, exp) VALUES(?,?,?) ON CONFLICT(shop_id) DO UPDATE SET pub=excluded.pub, exp=excluded.exp")
      .bind(shop, pub, exp).run();
  } else {
    if (!row) return json({ error: "invite_required" }, 403);
    if (row.pub !== pub) return json({ error: "key_mismatch" }, 401);
    if (row.exp < now()) return json({ error: "expired" }, 402);
  }
  await env.DB.prepare("UPDATE shops SET body=?, view_hash=?, updated=? WHERE shop_id=?")
    .bind(JSON.stringify(snap), snap.view_hash, now(), shop).run();
  return json({ ok: true });
}

async function handleSnap(url, env) {
  const shop = url.pathname.split("/")[3] || "", t = url.searchParams.get("t") || "";
  if (!SHOP_RE.test(shop) || !t || t.length > 100) return json({ error: "not_found" }, 404);
  const row = await env.DB.prepare("SELECT exp, view_hash, body, updated FROM shops WHERE shop_id=?").bind(shop).first();
  if (!row || !row.view_hash || !same(row.view_hash, await sha256hex(t))) return json({ error: "not_found" }, 404);
  if (row.exp < now()) return json({ error: "expired" }, 402);
  if (!row.body) return json({ error: "no_data" }, 404);
  return json({ updated: row.updated, snap: JSON.parse(row.body) });
}

// Anti trial-reset: remembers when a PC first started its trial. Public on purpose (machine ids are not secrets); it can only ever
// shorten a trial, never extend it. Add a Cloudflare rate-limit rule on /trial (see README_CLOUD.txt).
async function handleTrial(req, env) {
  let b; try { b = await req.json(); } catch { return json({ error: "bad_json" }, 400); }
  const m = String((b && b.m) || ""), h = String((b && b.h) || "");
  if (!/^POS-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}$/.test(m) || (h && !/^[0-9a-f]{32}$/.test(h))) return json({ error: "bad_request" }, 400);
  const keys = h ? [m, "hw:" + h] : [m];
  const row = await env.DB.prepare("SELECT MIN(first_seen) AS f FROM trials WHERE key IN (?,?)").bind(keys[0], keys[keys.length - 1]).first();
  const first = row && row.f ? row.f : now();
  for (const k of keys) await env.DB.prepare("INSERT OR IGNORE INTO trials(key, first_seen) VALUES(?,?)").bind(k, first).run();
  return json({ first });
}

async function handleInvite(req, env) {
  const auth = (req.headers.get("Authorization") || "").replace(/^Bearer /, "");
  if (!env.ADMIN_KEY || !same(auth, env.ADMIN_KEY)) return json({ error: "forbidden" }, 403);
  let days = 30;
  try { days = Math.max(1, Math.min(3660, parseInt((await req.json()).days || 30, 10))); } catch { /* default */ }
  const A = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789", r = crypto.getRandomValues(new Uint8Array(12));
  const raw = [...r].map(b => A[b % A.length]).join("");
  await env.DB.prepare("INSERT INTO invites(code, days, created) VALUES(?,?,?)").bind(raw, days, now()).run();
  return json({ code: raw.match(/.{4}/g).join("-"), days });
}

export default {
  async fetch(req, env) {
    const url = new URL(req.url), p = url.pathname;
    try {
      if (req.method === "POST" && p === "/push") return await handlePush(req, env);
      if (req.method === "POST" && p === "/trial") return await handleTrial(req, env);
      if (req.method === "POST" && p === "/admin/invite") return await handleInvite(req, env);
      if (req.method === "GET" && p.startsWith("/api/snap/")) return await handleSnap(url, env);
      if (req.method === "GET" && p.startsWith("/d/")) return new Response(DASH_HTML, { headers: { "Content-Type": "text/html; charset=utf-8", ...SEC,
        "Content-Security-Policy": "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'" } });
      if (req.method === "GET" && p === "/") return new Response("VeloPOS dashboard service", { headers: SEC });
    } catch (e) {
      return json({ error: "server_error" }, 500);
    }
    return json({ error: "not_found" }, 404);
  },
};
