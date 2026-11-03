VELOPOS - HOW TO SHIP WITHOUT "WINDOWS PROTECTED YOUR PC" WARNINGS
===================================================================
1. Build:   run installer\build_windows.bat on your own PC (it refuses to build if the private key or tools\ is present).
            It makes a standalone folder (not --onefile) + VeloPOS_Setup.exe. Onefile exes that unpack to %TEMP%
            on every launch are flagged by antivirus far more often.

2. Sign (this is what replaces "Unknown publisher" with YOUR name).  Facts checked in Nov 2026 (Microsoft Learn "Code signing options"):
   - Azure Artifact Signing (~US$10/month) is only open to organisations in USA/Canada/EU/UK and individuals in USA/Canada -> NOT available
     to a Sri Lankan individual.
   - OV certificate from a normal CA (DigiCert, Sectigo, SSL.com ... or a reseller): about US$150-300/year, worldwide. The key lives on a
     USB token / cloud HSM, identity validation takes several business days. THIS is your realistic option.
   - EV certificates (US$400+) NO LONGER give instant SmartScreen trust (since 2024) -> do not pay extra for EV.
   - Self-signed certificates are blocked for the public. Unsigned = strongest warning.
   signtool sign /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 /a installer\Output\VeloPOS_Setup.exe
   (sign VeloPOS.exe inside run.dist too, before packing, if you can).
   IMPORTANT: even signed, SmartScreen reputation builds up with downloads over weeks - the first customers may still see a warning.
   Use the SAME publisher name + certificate for every release so reputation carries over.

3. Reputation: upload every release to https://www.microsoft.com/wdsi/filesubmission (submit as "software developer")
   and, if Defender flags it, report the false positive. Check the file on virustotal.com before each release.
   Keep the same publisher name + certificate across releases: reputation builds up over time.

4. Until you have a certificate, tell customers on the landing page / WhatsApp:
   "Windows may show 'Unknown publisher' -> click More info -> Run anyway". Put a 20-second video of this in the ad funnel.

5. Trial / licence support
   a) Customer reinstalled Windows or changed PC  ->  the Machine ID changes, the old key stops working:
        1. Check it is really the same customer (name + payment slip; look the old Machine ID up in tools\issued_licenses.csv).
        2. Customer opens VeloPOS -> activation screen -> sends you the NEW Machine ID (WhatsApp).
        3. python tools/keygen.py issue <NEW-MACHINE-ID> --customer "<shop>"   -> send the key.
        4. Decide a policy (e.g. 1 free re-issue per year, Rs. X after that) and write it in your sale message.
      The trial is NOT restarted by a reinstall when TRIAL_SERVER_URL is set (the server also remembers the PC's hardware id).
   b) Forgot Admin password AND lost the Recovery Code -> SUPPORT CODE (you, remotely; the customer never gets the code):
        1. Customer: login screen -> Forgot password -> method "Support code" -> reads you the Machine ID + Challenge.
        2. You:  python tools/support_code.py <MACHINE-ID> <CHALLENGE> --customer "<shop>"
        3. Type / paste the printed code into THEIR screen (AnyDesk etc.), then choose the new Admin password with them.
        The code works only on that PC, only for that challenge, for 30 minutes, once. Every code is logged in tools\support_log.csv.
      Tell customers in your terms that this support option exists (it needs their consent anyway: they must read you the challenge).
