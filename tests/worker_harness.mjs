// Test helper: runs cloud/worker.js against an in-memory SQLite "D1" and serves it on a random local port.
// Prints "PORT <n>" when ready. Used by tests/test_phase7_1.py.
import http from "node:http";
import { DatabaseSync } from "node:sqlite";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const worker = (await import(path.join(here, "..", "cloud", "worker.js"))).default;
const db = new DatabaseSync(":memory:");
db.exec(fs.readFileSync(path.join(here, "..", "cloud", "schema.sql"), "utf8"));

function stmt(sql) {
  let args = [];
  const o = {
    bind(...a) { args = a; return o; },
    async first() { const r = db.prepare(sql).get(...args); return r === undefined ? null : { ...r }; },
    async run() { db.prepare(sql).run(...args); return { success: true }; },
  };
  return o;
}
const env = { DB: { prepare: stmt }, ADMIN_KEY: "test-admin-key" };
const srv = http.createServer(async (req, res) => {
  const chunks = []; for await (const c of req) chunks.push(c);
  if (req.url === "/__seed") {                       // test-only: pretend a PC first ran its trial in the past
    const b = JSON.parse(Buffer.concat(chunks).toString());
    db.prepare("INSERT OR REPLACE INTO trials(key, first_seen) VALUES(?,?)").run(b.key, b.first_seen);
    res.writeHead(200); return res.end("ok");
  }
  const url = "http://" + req.headers.host + req.url;
  const r = new Request(url, { method: req.method, headers: req.headers, body: ["GET", "HEAD"].includes(req.method) ? undefined : Buffer.concat(chunks) });
  const out = await worker.fetch(r, env);
  res.writeHead(out.status, Object.fromEntries(out.headers));
  res.end(Buffer.from(await out.arrayBuffer()));
});
srv.listen(0, "127.0.0.1", () => console.log("PORT " + srv.address().port));
