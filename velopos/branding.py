"""Developer branding & payment info shown on the activation / about screens."""
DEV_COMPANY   = "VeloPOS (Powered by RG)"
DEV_COPYRIGHT = "© 2026 VeloPOS Software Solutions. All Rights Reserved."
DEV_WARNING   = ("WARNING: This computer program is protected by copyright law and international "
                 "treaties. Unauthorized reproduction or distribution of this program, or any portion "
                 "of it, may result in severe civil and criminal penalties.")
DEV_PHONE     = "+94 76 2875735 / +94 71 5853860 (WhatsApp / Hotline)"
DEV_WHATSAPP  = "94762875735"
DEV_EMAIL     = "rajithagaspe@gmail.com"
DEV_WEBSITE   = "https://rajithagaspe.gumroad.com/l/velopos"
PRICE_LKR     = "Rs. 9,999/="
PRICE_USD     = "$59 USD"          # single source of truth (old code showed $59 and $39)
DEV_BANK      = "Sampath Bank | Wariyapola | A/C 104454513502 | G M R L KUMARA GASPE"
DEV_BINANCE   = "Binance Pay ID: 38102333 (USDT / BUSD / BTC)"
TRIAL_DAYS    = 30
# Address of YOUR Cloudflare Worker (cloud/README_CLOUD.txt). When set, the program asks it when this PC FIRST started its trial, so deleting
# the local trial files no longer gives a new 30 days (while the PC is online). Leave "" to disable. Example: "https://velopos-dashboard.you.workers.dev"
TRIAL_SERVER_URL = "https://velopos-dashboard.velopos-rg.workers.dev"
# Pre-filled for every customer (they can still change them in Settings). Put YOUR Worker address / version.json link here BEFORE building.
DEFAULT_DASH_URL   = "https://velopos-dashboard.velopos-rg.workers.dev"      # e.g. "https://velopos-dashboard.you.workers.dev"
DEFAULT_UPDATE_URL = ""      # e.g. "https://yoursite.com/velopos/version.json"
