VELOPOS OWNER PHONE DASHBOARD - DEPLOY GUIDE (you, the developer, do this ONCE)
================================================================================
You need: a free Cloudflare account, Node.js 20+ on your PC.  Nothing here goes to customers (keep the cloud\ folder out of the installer).

1. Open a terminal in the cloud\ folder and log in:
       npx wrangler login
2. Create the database (copy the database_id it prints into wrangler.toml):
       npx wrangler d1 create velopos
       npx wrangler d1 execute velopos --remote --file=schema.sql
3. Set the admin secret (long random text; keep it private - it is how you issue invites):
       npx wrangler secret put ADMIN_KEY
4. Deploy:
       npx wrangler deploy
   It prints your address, e.g.  https://velopos-dashboard.<yourname>.workers.dev   <- customers type this in Settings 4h.
5. Issue an invite code for a customer (one code = one shop, 30 days; change "days" for the plan you sell):
       curl -X POST https://velopos-dashboard.<yourname>.workers.dev/admin/invite -H "Authorization: Bearer <ADMIN_KEY>" -d "{\"days\":30}"
   -> {"code":"AB12-CD34-EF56","days":30}.  Give the code to the customer (WhatsApp).
   - Renewal: issue a new code; the customer enters it in Settings 4h and presses "Upload now". Days are ADDED to what is left.
   - Customer moved to a new PC / reinstalled Windows: they need a new code too (the shop's signing key lives in that PC's vault).
   - Stop a customer: do nothing - the subscription simply ends at its date (the phone page then says it has ended).

CUSTOMER SIDE (Settings 4h in VeloPOS)
   - tick "Owner phone dashboard" in the feature list, type the address + invite code, press "Upload now (test)",
     then "Show / copy phone link" or "Send link to owner WhatsApp". Open the link on the phone -> Add to Home screen.

HOW IT IS PROTECTED
   - Each shop signs every upload with its own Ed25519 key (private key never leaves the PC). The Worker keeps only the public key.
   - A new shop is accepted only with a one-time invite code; the code is burned atomically, and only AFTER the signature is valid.
   - The phone link has a random token; the Worker stores only its SHA-256 hash. "New link" in the POS replaces it.
   - Uploads older than 10 minutes are refused (replay); bodies over 64 KB are refused; the page is served with a strict CSP.
   - Only a summary is uploaded - no customer names/phones, no bills, no cost prices.

COSTS / LIMITS (check Cloudflare's current free-tier numbers before selling widely)
   - One small database write per shop every 15 minutes while sales change (nothing is re-sent when nothing changed).
   - Add Cloudflare's rate-limiting rule on /push and /admin/invite from the dashboard if you ever see abuse.
   - Data privacy: you are now storing shops' sales summaries. Tell customers (a short line in your terms) and delete a shop's row on request:
       npx wrangler d1 execute velopos --remote --command "DELETE FROM shops WHERE shop_id='<id>'"

ANTI TRIAL-RESET (optional, same Worker)
   - After deploying, open velopos\branding.py and set TRIAL_SERVER_URL = "https://velopos-dashboard.<yourname>.workers.dev" BEFORE you build the exe.
   - The POS then asks the Worker (once per program start, 4 s timeout) when this PC first started its trial; the Worker remembers the Machine ID
     and a hash of the PC's hardware id (so a Windows reinstall does not restart the trial). Offline shops simply use the local rules.
   - Weak spot you should know: a PC that is NEVER online can still wipe its local files; it is caught the first time it connects.
   - Add a Cloudflare rate-limiting rule for POST /trial, /push and /admin/invite (Dashboard -> Security -> WAF -> Rate limiting rules), otherwise
     someone could fill your free database with junk ids.
   - Re-run:  npx wrangler d1 execute velopos --remote --file=schema.sql   (adds the new "trials" table) and  npx wrangler deploy.

LOCAL TEST (no Cloudflare needed):  python -m unittest tests.test_phase7_1 -v     (needs Node 22+; it runs worker.js against an in-memory database)
