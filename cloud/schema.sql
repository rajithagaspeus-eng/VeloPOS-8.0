CREATE TABLE IF NOT EXISTS shops (
  shop_id   TEXT PRIMARY KEY,
  pub       TEXT NOT NULL,              -- the shop's Ed25519 public key (base64url)
  exp       INTEGER NOT NULL,           -- subscription end (unix seconds)
  view_hash TEXT NOT NULL DEFAULT '',   -- sha256 of the phone-link token
  body      TEXT,                       -- latest summary (JSON)
  updated   INTEGER
);
CREATE TABLE IF NOT EXISTS invites (
  code    TEXT PRIMARY KEY,
  days    INTEGER NOT NULL,
  created INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS trials (
  key        TEXT PRIMARY KEY,          -- machine id, or "hw:" + hash of the PC's hardware id
  first_seen INTEGER NOT NULL           -- unix seconds
);
