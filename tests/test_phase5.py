"""Headless tests for Phase 5 (assistant engine, voice helpers, daily summary). Run from the project root:
    python -m unittest tests.test_phase5 -v
Uses a throw-away temp folder; never touches your real data."""
import os, re, sys, tempfile, types, unittest
from datetime import datetime, timedelta

os.environ.setdefault("VELOPOS_HOME", tempfile.mkdtemp(prefix="velopos_test5_"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.test_phase4 import _FakeSmtp, fresh                                              # noqa: E402  (shared helpers)
from velopos import assistant as A, assistant_i18n as I, database as dbm, otp as otpmod, security, services as svc, voice   # noqa: E402

import socketserver, threading                                                              # noqa: E402

TODAY = datetime.now().strftime("%Y-%m-%d")
YESTERDAY = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")


def seed():
    """Shop data with known numbers."""
    soon = (datetime.now() + timedelta(days=10)).strftime("%Y-%m-%d")
    with dbm.db() as c:
        ins = ("INSERT INTO products(barcode,name_en,name_local,keywords,cost_price,selling_price,stock_qty,expiry_date) VALUES (?,?,?,?,?,?,?,?)")
        c.execute(ins, ("8901", "Sugar", "සීනි", "chini, சர்க்கரை, चीनी, سكر, azucar", 100, 150, 3, ""))
        c.execute(ins, ("8902", "Rice", "සහල්", "", 80, 120, 40, ""))
        c.execute(ins, ("8903", "Milk Powder", "", "", 300, 420, 0, ""))
        c.execute(ins, ("8904", "Coconut Oil", "පොල්තෙල්", "", 200, 260, 12, ""))
        c.execute(ins, ("8905", "Sunflower Oil", "", "", 250, 330, 9, ""))
        c.execute(ins, ("8906", "Soap", "", "", 40, 60, 25, YESTERDAY))
        c.execute(ins, ("8907", "Biscuit", "", "", 30, 50, 60, soon))
        c.execute("INSERT INTO customers(name,phone,credit_balance) VALUES('Kamal','0771',2500)")
        c.execute("INSERT INTO customers(name,phone,credit_balance) VALUES('Nimal','0772',900)")
        c.execute("INSERT INTO customers(name,phone,credit_balance) VALUES('Paid Up','0773',0)")
        c.execute("INSERT INTO expenses(date,category,description,amount,added_by) VALUES (?,?,?,?,?)", (TODAY, "Electricity", "bill", 500, "admin"))
        c.execute("INSERT INTO expenses(date,category,description,amount,added_by) VALUES (?,?,?,?,?)", (TODAY, "Transport", "van", 250, "admin"))
        c.execute("INSERT INTO sales(invoice_no,date,time,subtotal,discount,total_amount,paid_amount,balance,payment_method,profit,cashier,customer_name,status) "
                  "VALUES ('Y-1',?, '10:00',1000,0,1000,1000,0,'Cash',300,'admin','Walk-in','OK')", (YESTERDAY,))
        c.execute("INSERT INTO sale_items(invoice_no,barcode,item_name,qty,cost_price,selling_price,total) VALUES ('Y-1','8902','Rice',5,80,120,600)")
    sid = svc.open_shift("admin", 1000)
    svc.create_sale([dict(barcode="8902", name="Rice", qty=2, price=120)], 0, 0, 240, "Cash", "", None, "admin", sid)
    svc.create_sale([dict(barcode="8904", name="Coconut Oil", qty=1, price=260)], 0, 0, 0, "Credit", "", 1, "admin", sid)
    return sid


def ctx(lang="English", can=None, admin=True, user="admin"):
    return A.Ctx(cur="Rs.", shop="Test Shop", user=user, is_admin=admin, can=can or (lambda p: True), lang=lang, cfg=dbm.settings)


class Base(unittest.TestCase):
    def setUp(self):
        fresh()
        dbm.settings.set_many({"shop_name": "Test Shop", "feat_shift": "1", "low_stock_level": "5"})
        self.sid = seed()


# ============================================================================ translation data
class I18nTests(unittest.TestCase):
    def test_every_language_has_every_string_with_the_same_placeholders(self):
        ph = lambda s: sorted(re.findall(r"\{(\w+)\}", s))               # noqa: E731
        base = I.STR["en"]
        for lg, d in I.STR.items():
            self.assertEqual(set(base), set(d), lg)
            for k in base:
                self.assertEqual(ph(base[k]), ph(d[k]), f"{lg}.{k}")

    def test_help_topics_complete_and_mention_real_menu_names(self):
        need = {"bill": "Billing", "product": "Inventory", "return": "Returns & Refunds", "void": "Reports & Insights", "shift": "Shift & Cash Drawer",
                "backup": "Backup & Restore", "printer": "Settings", "credit": "Credit Book", "password": "Settings", "expense": "Expenses"}
        for lg in I.LANGS:
            self.assertEqual(set(I.TOPIC_TEXT[lg]), set(I.TOPIC_ORDER))
            self.assertEqual(len(I.TOPIC_LABEL[lg]), len(I.TOPIC_ORDER))
            self.assertEqual(len(I.CHIPS[lg]), len(I.CHIP_INTENTS))
            for t, term in need.items():
                self.assertIn(term, I.TOPIC_TEXT[lg][t], f"{lg}.{t}")

    def test_language_labels_round_trip(self):
        for code, label in I.LANGS.items():
            self.assertEqual(I.LANG_LABELS[label], code)
        self.assertEqual(I.LANG_LABELS[I.AUTO_LABEL], "auto")


# ============================================================================ understanding the question
class IntentTests(Base):
    def intent(self, q, lang="Auto (match my question)"):
        return A.respond(q, ctx(lang)).intent

    def test_english(self):
        table = [("what are today's sales", "sales"), ("how much did we sell today", "sales"), ("profit today", "profit"),
                 ("what is the profit this month", "profit"), ("show me low stock items", "low_stock"), ("which items are running out", "low_stock"),
                 ("best selling items this month", "top_sellers"), ("top sellers this week", "top_sellers"), ("who owes the most money", "credit_owed"),
                 ("expenses this week", "expenses"), ("what is expiring soon", "expiry"), ("is the shift open", "shift_status"),
                 ("give me the daily summary", "daily_summary"), ("hello", "greeting"), ("thanks a lot", "thanks"), ("help", "help"),
                 ("stock of sugar", "stock_of"), ("how many sugar left", "stock_of"), ("do we have rice", "stock_of"), ("sugar", "stock_of")]
        for q, want in table:
            self.assertEqual(self.intent(q), want, q)

    def test_typos_are_forgiven(self):
        for q, want in (("profitt today", "profit"), ("expence today", "expenses"), ("stok of sugar", "stock_of"), ("sugr", "stock_of"),
                        ("expirng soon", "expiry"), ("low stok", "low_stock")):
            self.assertEqual(self.intent(q), want, q)

    def test_singlish(self):
        table = [("ada wikunum kiyada", "sales"), ("ada laba kiyada", "profit"), ("adu thoga monawada", "low_stock"), ("sugar thoga kiyada", "stock_of"),
                 ("naya thiyenne kawda", "credit_owed"), ("iye wikunum", "sales"), ("meya masaya waya", "expenses"), ("ayubowan", "greeting"),
                 ("istuti", "thanks"), ("dawase saaramshaya", "daily_summary"), ("kal ikuth wena items", "expiry"), ("shift eka open da", "shift_status"),
                 ("wadama wikunena items meya sathiya", "top_sellers"), ("vikunuma ada", "sales")]
        for q, want in table:
            r = A.respond(q, ctx("Auto (match my question)"))
            self.assertEqual(r.intent, want, q)
            self.assertEqual(r.lang, "si", q)                               # Singlish is answered in Sinhala when set to Auto

    def test_sinhala_tamil_hindi_arabic_spanish(self):
        table = [("අද විකුණුම් කීයද", "sales"), ("අද ලාභය", "profit"), ("අඩු තොග", "low_stock"), ("වැඩිපුරම ණය ඇත්තේ කාටද", "credit_owed"),
                 ("අද වියදම්", "expenses"), ("කල් ඉකුත් වෙන භාණ්ඩ", "expiry"), ("ෂිෆ්ට් තත්ත්වය", "shift_status"), ("දවසේ සාරාංශය", "daily_summary"),
                 ("ආයුබෝවන්", "greeting"), ("ස්තූතියි", "thanks"), ("සීනි තොග කීයද", "stock_of"),
                 ("இன்றைய விற்பனை", "sales"), ("இன்றைய இலாபம்", "profit"), ("குறைந்த இருப்பு", "low_stock"), ("யார் அதிக கடன் வைத்திருக்கிறார்கள்", "credit_owed"),
                 ("இன்றைய செலவுகள்", "expenses"), ("வணக்கம்", "greeting"), ("நன்றி", "thanks"), ("சர்க்கரை இருப்பு", "stock_of"),
                 ("आज की बिक्री", "sales"), ("आज का मुनाफ़ा", "profit"), ("कम स्टॉक", "low_stock"), ("सबसे ज्यादा उधार किस पर है", "credit_owed"),
                 ("आज का खर्च", "expenses"), ("नमस्ते", "greeting"), ("धन्यवाद", "thanks"), ("चीनी का स्टॉक", "stock_of"),
                 ("مبيعات اليوم", "sales"), ("أرباح اليوم", "profit"), ("مخزون منخفض", "low_stock"), ("من عليه أكبر دين", "credit_owed"),
                 ("مصاريف اليوم", "expenses"), ("الأصناف التي تنتهي صلاحيتها", "expiry"), ("مرحبا", "greeting"), ("شكرا", "thanks"), ("مخزون السكر", "stock_of"),
                 ("ventas de hoy", "sales"), ("ganancia de hoy", "profit"), ("stock bajo", "low_stock"), ("más vendidos esta semana", "top_sellers"),
                 ("quién debe más", "credit_owed"), ("gastos de hoy", "expenses"), ("artículos por caducar", "expiry"), ("estado del turno", "shift_status"),
                 ("hola", "greeting"), ("gracias", "thanks"), ("existencias de azúcar", "stock_of")]
        for q, want in table:
            self.assertEqual(self.intent(q), want, q)

    def test_howto_in_every_language(self):
        table = [("how do I make a return", "return", "en"), ("how to cancel a bill", "void", "en"), ("how do I print a receipt", "printer", "en"),
                 ("how do I take a backup", "backup", "en"), ("how do i add a product", "product", "en"), ("how do I open a shift", "shift", "en"),
                 ("how do I give credit to a customer", "credit", "en"), ("how do I change my password", "password", "en"),
                 ("how do I add an expense", "expense", "en"), ("how do I make a bill", "bill", "en"),
                 ("return ekak kohomada karanne", "return", "si"), ("backup එකක් ගන්නේ කොහොමද", "backup", "si"), ("return එකක් කරන්නේ කොහොමද", "return", "si"),
                 ("ரிட்டர்ன் எப்படி செய்வது", "return", "ta"), ("रिटर्न कैसे करें", "return", "hi"), ("बैकअप कैसे लें", "backup", "hi"),
                 ("كيف أجري عملية إرجاع", "return", "ar"), ("كيف اضيف مصروف", "expense", "ar"),
                 ("como hago una devolucion", "return", "es"), ("cómo hago una copia de seguridad", "backup", "es")]
        for q, topic, lang in table:
            r = A.respond(q, ctx("Auto (match my question)"))
            self.assertEqual((r.intent, r.data.get("topic"), r.lang), ("howto", topic, lang), q)
            self.assertEqual(r.text, I.TOPIC_TEXT[lang][topic])

    def test_howto_without_topic_lists_the_topics(self):
        r = A.respond("how do I", ctx("English"))
        self.assertEqual(r.intent, "howto")
        self.assertIn("making a bill", r.text)

    def test_data_questions_are_not_mistaken_for_howto(self):
        self.assertEqual(A.respond("how many sugar do we have", ctx()).intent, "stock_of")
        self.assertEqual(A.respond("how much did we sell yesterday", ctx()).intent, "sales")

    def test_garbage_input_never_crashes(self):
        for q in ("", "   ", "???", "'; DROP TABLE products; --", "a" * 5000, "😀😀😀", "\x00\x01", "SELECT * FROM users"):
            r = A.respond(q, ctx())
            self.assertTrue(r.text)
        with dbm.db() as c:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM products").fetchone()[0], 7)
            self.assertEqual(c.execute("SELECT COUNT(*) FROM users").fetchone()[0], 2)

    def test_unknown_question(self):
        r = A.respond("what is the meaning of life", ctx("English"))
        self.assertEqual(r.intent, "unknown")

    def test_language_detection(self):
        for text, want in (("sales today", "en"), ("ada wikunum", "si"), ("අද විකුණුම්", "si"), ("இன்று", "ta"), ("आज", "hi"), ("اليوم", "ar"),
                           ("ventas de hoy", "es"), ("¿cuánto?", "es"), ("12345", "en")):
            self.assertEqual(A.detect_lang(text), want, text)

    def test_fixed_language_overrides_the_question_language(self):
        r = A.respond("sales today", ctx("සිංහල (Sinhala)"))
        self.assertEqual(r.lang, "si")
        self.assertRegex(r.text, "[\u0D80-\u0DFF]")
        r = A.respond("අද විකුණුම්", ctx("English"))
        self.assertEqual(r.lang, "en")
        self.assertIn("Sales for today", r.text)


# ============================================================================ answers come from the database
class AnswerTests(Base):
    def ask(self, q, lang="English", **k):
        return A.respond(q, ctx(lang, **k))

    def test_sales_and_profit_numbers(self):
        r = self.ask("sales today")
        self.assertIn("Rs. 500.00 from 2 bill(s)", r.text)                        # 240 cash + 260 credit
        self.assertIn("Returns Rs. 0.00", r.text)
        self.assertIn("Profit for today", r.text)
        rd = svc.report_data(TODAY, TODAY)
        self.assertIn(f"{rd['profit']:,.2f}", r.text)
        self.assertIn("Rs. 1,000.00", self.ask("sales yesterday").text)
        self.assertIn("Rs. 1,500.00", self.ask("sales last 7 days").text)         # yesterday 1000 + today 500
        self.assertIn("Profit for today", self.ask("profit today").text.splitlines()[0])

    def test_no_sales_message(self):
        with dbm.db() as c:
            c.execute("DELETE FROM sales")
        self.assertIn("No sales are recorded for today", self.ask("sales today").text)

    def test_stock_answers(self):
        self.assertIn("Sugar: only 3 left (low)", self.ask("stock of sugar").text)
        self.assertIn("Rice: 38 in stock", self.ask("how many rice left").text)
        self.assertIn("Milk Powder: OUT OF STOCK", self.ask("stock of milk powder").text)

    def test_fuzzy_names_local_names_keywords_and_barcodes(self):
        self.assertIn("Sugar", self.ask("stock of sugr").text)
        self.assertIn("Milk Powder", self.ask("mlk powder stock").text)
        self.assertIn("Coconut Oil", self.ask("cocnut oil stock").text)
        self.assertIn("Sugar", self.ask("සීනි තොග කීයද").text)                    # local (Sinhala) name
        self.assertIn("Sugar", self.ask("चीनी का स्टॉक").text)                    # keyword
        self.assertIn("Sugar", self.ask("مخزون السكر").text)
        self.assertIn("Sugar", self.ask("existencias de azúcar").text)
        self.assertIn("Rice", self.ask("stock 8902").text)                         # exact barcode
        self.assertIn("Coconut Oil", self.ask("පොල්තෙල් තොග").text)

    def test_ambiguous_item_lists_candidates(self):
        t = self.ask("stock of oil").text
        self.assertIn("Coconut Oil", t)
        self.assertIn("Sunflower Oil", t)
        self.assertIn("Several items match", t)

    def test_unknown_item_and_missing_item(self):
        self.assertIn("couldn't find", self.ask("stock of xyzzyplugh").text)
        self.assertIn("Which item", self.ask("how many left").text)

    def test_low_stock_uses_the_setting(self):
        t = self.ask("low stock").text
        self.assertIn("Sugar: 3", t)
        self.assertIn("Milk Powder: 0", t)
        self.assertNotIn("Coconut Oil", t)
        dbm.settings.set_many({"low_stock_level": "10"})
        self.assertIn("Sunflower Oil: 9", self.ask("low stock").text)
        dbm.settings.set_many({"low_stock_level": "0"})
        t = self.ask("low stock").text
        self.assertIn("Milk Powder", t)
        self.assertNotIn("Sugar: 3", t)
        with dbm.db() as c:
            c.execute("UPDATE products SET stock_qty=99")
        self.assertIn("no item is at or below", self.ask("low stock").text)

    def test_top_sellers(self):
        t = self.ask("top sellers today").text
        self.assertIn("1. Coconut Oil", t) if "Coconut" in t.splitlines()[1] else self.assertIn("Rice", t)
        self.assertIn("Rice", self.ask("top sellers this month").text)

    def test_credit_book(self):
        t = self.ask("who owes the most").text
        lines = t.splitlines()
        self.assertIn("total outstanding Rs. 3,660.00", lines[0])      # 2500 + 900 + 260 credit sale made in seed()
        self.assertIn("1. Kamal - Rs. 2,760.00", lines[1])
        self.assertIn("2. Nimal - Rs. 900.00", lines[2])
        self.assertNotIn("Paid Up", t)

    def test_expenses(self):
        t = self.ask("expenses today").text
        self.assertIn("Rs. 750.00", t)
        self.assertIn("Electricity: Rs. 500.00", t)
        self.assertIn("No expenses are recorded for yesterday", self.ask("expenses yesterday").text)

    def test_expiry(self):
        t = self.ask("expiring soon").text
        self.assertIn("2 item(s)", t)
        self.assertIn("Soap", t)
        self.assertIn("EXPIRED", t)
        self.assertIn("Biscuit", t)
        self.assertIn("in 10 day(s)", t)
        self.assertIn("CADUCADO", self.ask("artículos por caducar", "Español (Spanish)").text)

    def test_shift_status(self):
        self.assertIn(f"Shift #{self.sid} (admin) is OPEN", self.ask("shift status").text)
        self.assertIn("Expected cash in the drawer: Rs. 1,240.00", self.ask("shift status").text)          # 1000 + 240 cash
        svc.close_shift(self.sid, 1240, "", "admin")
        self.assertIn("No shift is open", self.ask("shift status").text)
        dbm.settings.set_many({"feat_shift": "0"})
        self.assertIn("switched off", self.ask("shift status").text)
        dbm.settings.set_many({"feat_shift": "1"})
        with dbm.db() as c:
            c.execute("DELETE FROM shifts")
        self.assertIn("No shift has been opened", self.ask("shift status").text)

    def test_cashier_only_sees_their_own_shift(self):
        r = self.ask("shift status", admin=False, user="someone_else")
        self.assertNotIn("OPEN", r.text)

    def test_every_language_answers_with_real_numbers(self):
        for label in I.LANGS.values():
            for q in ("sales today", "low stock", "who owes the most", "expenses today", "expiring soon", "shift status", "top sellers this week"):
                r = A.respond(q, ctx(label))
                self.assertNotIn("{", r.text, (label, q))
                self.assertNotIn("}", r.text, (label, q))
        r = A.respond("sales today", ctx("العربية (Arabic)"))
        self.assertIn("Rs. 500.00", r.text)

    def test_howto_texts_are_returned_as_written(self):
        for lang, label in I.LANGS.items():
            r = A.respond("how do I make a return", ctx(label))
            self.assertEqual(r.text, I.TOPIC_TEXT[lang]["return"])


class PermissionTests(Base):
    def test_cashier_without_permissions_is_refused(self):
        deny = ctx(can=lambda p: False, admin=False)
        for q in ("sales today", "profit today", "top sellers", "expenses today", "daily summary"):
            r = A.respond(q, deny)
            self.assertEqual(r.intent, "denied", q)
            self.assertNotRegex(r.text, r"\d{3}")
        for q in ("stock of sugar", "low stock", "who owes the most", "expiring soon", "how do I make a return", "hello"):
            self.assertNotEqual(A.respond(q, deny).intent, "denied", q)

    def test_permissions_are_granular(self):
        only_exp = ctx(can=lambda p: p == "expenses", admin=False)
        self.assertEqual(A.respond("expenses today", only_exp).intent, "expenses")
        self.assertEqual(A.respond("profit today", only_exp).intent, "denied")
        only_rep = ctx(can=lambda p: p == "reports", admin=False)
        self.assertEqual(A.respond("sales today", only_rep).intent, "sales")
        self.assertEqual(A.respond("expenses today", only_rep).intent, "denied")


# ============================================================================ daily summary
class SummaryTests(Base):
    def test_summary_content_in_every_language(self):
        for lang, label in I.LANGS.items():
            s = A.build_daily_summary(ctx(label), lang)
            self.assertIn("Test Shop", s["title"])
            self.assertIn(TODAY, s["title"])
            self.assertIn("500.00", s["text"])
            self.assertIn("750.00", s["text"])                                   # expenses
            self.assertIn("3,660.00", s["text"])                                 # credit owed
            self.assertNotIn("{", s["text"])
            self.assertEqual(("dir='rtl'" in s["html"]), lang == "ar")
            self.assertIn(I.STR[lang]["sum_footer"], s["text"])

    def test_cashier_summary_has_no_money_beyond_sales(self):
        s = A.build_daily_summary(ctx(can=lambda p: False, admin=False), "en")
        self.assertIn("Sales: Rs. 500.00", s["text"])
        for word in ("Profit", "Expenses", "Credit owed", "Returns"):
            self.assertNotIn(word, s["text"])

    def test_html_is_escaped(self):
        with dbm.db() as c:
            c.execute("INSERT INTO sale_items(invoice_no,barcode,item_name,qty,cost_price,selling_price,total) "
                      "SELECT invoice_no,'X','<script>alert(1)</script>',9,1,1,99999 FROM sales WHERE date=? LIMIT 1", (TODAY,))
        s = A.build_daily_summary(ctx(), "en")
        self.assertIn("<script>", s["text"])                                      # plain text keeps it
        self.assertNotIn("<script>", s["html"])
        self.assertIn("&lt;script&gt;", s["html"])

    def test_chat_reply_carries_the_summary(self):
        r = A.respond("daily summary", ctx("Auto (match my question)"))
        self.assertEqual(r.intent, "daily_summary")
        self.assertIn("title", r.data["summary"])

    def test_due_logic(self):
        cfg = dbm.settings
        at = lambda h, m: datetime.now().replace(hour=h, minute=m, second=0)      # noqa: E731
        cfg.set_many({"feat_daily_summary": "1", "feat_summary_dayend": "1", "summary_time": "21:00", "last_summary_date": ""})
        self.assertFalse(A.summary_due(cfg, at(20, 59)))
        self.assertTrue(A.summary_due(cfg, at(21, 0)))
        self.assertTrue(A.summary_due(cfg, at(23, 30)))
        cfg.set_many({"last_summary_date": TODAY})
        self.assertFalse(A.summary_due(cfg, at(23, 30)))
        cfg.set_many({"last_summary_date": YESTERDAY})
        self.assertTrue(A.summary_due(cfg, at(21, 5)))
        cfg.set_many({"feat_summary_dayend": "0"})
        self.assertFalse(A.summary_due(cfg, at(23, 30)))
        cfg.set_many({"feat_summary_dayend": "1", "feat_daily_summary": "0"})
        self.assertFalse(A.summary_due(cfg, at(23, 30)))
        cfg.set_many({"feat_daily_summary": "1", "summary_time": "garbage"})
        self.assertTrue(A.summary_due(cfg, at(21, 0)))                              # bad time -> falls back to 21:00

    def test_whatsapp_delivery(self):
        dbm.settings.set_many({"owner_whatsapp": "0771234567"})
        s = A.build_daily_summary(ctx(), "en")
        kind, url = A.deliver_summary(s, "WhatsApp")
        self.assertEqual(kind, "whatsapp")
        self.assertTrue(url.startswith("https://wa.me/94771234567?text="))
        self.assertIn("Daily%20summary", url)
        dbm.settings.set_many({"owner_whatsapp": ""})
        with self.assertRaises(ValueError):
            A.deliver_summary(s, "WhatsApp")

    def test_email_delivery_through_a_fake_smtp_server(self):
        srv = socketserver.ThreadingTCPServer(("127.0.0.1", 0), _FakeSmtp)
        srv.messages = []
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            dbm.settings.set_many({"smtp_host": "127.0.0.1", "smtp_port": str(srv.server_address[1]), "smtp_user": "shop@gmail.com",
                                   "owner_email": "owner@example.com"})
            otpmod.set_smtp_password("goodpass")
            s = A.build_daily_summary(ctx(), "en")
            self.assertEqual(A.deliver_summary(s, "Email"), ("email", "owner@example.com"))
            self.assertEqual(len(srv.messages), 1)
            m = srv.messages[0]
            self.assertIn("Daily summary - Test Shop", m)
            self.assertIn("text/html", m)                                           # multipart: plain + HTML
            self.assertIn("500.00", m)
            otpmod.set_smtp_password("")
            with self.assertRaises(ValueError):
                A.deliver_summary(s, "Email")
        finally:
            srv.shutdown()
            srv.server_close()


# ============================================================================ voice
class VoiceTests(unittest.TestCase):
    def test_text_never_enters_the_command_line(self):
        evil = '"; Remove-Item C:\\* -Recurse; "$(calc.exe) `whoami`'
        cmd, env = voice.build_speak_job(evil, "en")
        self.assertNotIn("Remove-Item", " ".join(cmd))
        self.assertNotIn("calc", " ".join(cmd))
        self.assertIn("Remove-Item", env["VP_TEXT"])                                # travels as data
        self.assertEqual(env["VP_LANG"], "en")
        self.assertEqual(cmd[-1], voice.SPEAK_SCRIPT)                                # constant script
        self.assertIn("$env:VP_TEXT", voice.SPEAK_SCRIPT)

    def test_clean_for_speech(self):
        t = voice.clean_for_speech("Low stock (at or below 5): 2 item(s)\n- Sugar: 3\n- Rice: 0\n" + "x" * 2000)
        self.assertLessEqual(len(t), voice.MAX_CHARS)
        self.assertNotIn("\n", t)
        self.assertNotIn("- Sugar", t)

    def test_speak_reports_novoice_and_ok(self):
        calls = []
        real_run, real_win = voice.subprocess.run, voice.IS_WINDOWS
        voice.IS_WINDOWS = True
        try:
            for code, want in ((0, "ok"), (3, "novoice"), (1, "error")):
                voice.subprocess.run = lambda cmd, env=None, **k: (calls.append((cmd, env)), types.SimpleNamespace(returncode=code))[1]
                got = []
                voice.speak("hello", "si", True, got.append, sync=True)
                self.assertEqual(got, [want])
            self.assertEqual(calls[0][1]["VP_LANG"], "si")
            voice.subprocess.run = lambda *a, **k: (_ for _ in ()).throw(OSError("no powershell"))
            got = []
            voice.speak("hello", "en", True, got.append, sync=True)
            self.assertEqual(got, ["error"])
        finally:
            voice.subprocess.run, voice.IS_WINDOWS = real_run, real_win

    def test_speak_is_silent_when_disabled_or_not_windows(self):
        ran = []
        real_run, real_win = voice.subprocess.run, voice.IS_WINDOWS
        voice.subprocess.run = lambda *a, **k: ran.append(1)
        try:
            voice.IS_WINDOWS = True
            voice.speak("hi", "en", False, sync=True)
            voice.speak("", "en", True, sync=True)
            voice.IS_WINDOWS = False
            voice.speak("hi", "en", True, sync=True)
            self.assertEqual(ran, [])
        finally:
            voice.subprocess.run, voice.IS_WINDOWS = real_run, real_win

    def test_parse_voices(self):
        raw = "Microsoft David Desktop|en-US\nMicrosoft Zira Desktop|en-US\nMicrosoft Valluvar|ta-IN\r\nbroken line\n"
        got = voice.parse_voices(raw)
        self.assertEqual(got["en"], ["Microsoft David Desktop", "Microsoft Zira Desktop"])
        self.assertEqual(got["ta"], ["Microsoft Valluvar"])
        self.assertNotIn("si", got)

    def test_voice_input_uses_the_right_language_and_maps_errors(self):
        class Boom(Exception):
            pass

        def fake_module(outcome):
            m = types.ModuleType("speech_recognition")
            m.WaitTimeoutError, m.UnknownValueError, m.RequestError = type("W", (Exception,), {}), type("U", (Exception,), {}), type("R", (Exception,), {})
            seen = {}

            class Mic:
                def __enter__(s): return s
                def __exit__(s, *a): return False
                @staticmethod
                def list_microphone_names(): return ["Mic"]

            class Rec:
                def adjust_for_ambient_noise(s, src, duration=0): pass
                def listen(s, src, timeout=None, phrase_time_limit=None):
                    if outcome == "timeout": raise m.WaitTimeoutError()
                    return "AUDIO"
                def recognize_google(s, audio, language=None):
                    seen["language"] = language
                    if outcome == "unknown": raise m.UnknownValueError()
                    if outcome == "offline": raise m.RequestError()
                    return "sales today"
            m.Microphone, m.Recognizer, m.seen = Mic, Rec, seen
            return m
        old = sys.modules.get("speech_recognition", "missing")
        try:
            m = fake_module("ok")
            sys.modules["speech_recognition"] = m
            self.assertEqual(voice.stt_available(), (True, "OK"))
            self.assertEqual(voice.listen_once("si"), "sales today")
            self.assertEqual(m.seen["language"], "si-LK")
            voice.listen_once("ar")
            self.assertEqual(m.seen["language"], "ar-SA")
            for outcome, text in (("timeout", "did not hear"), ("unknown", "could not understand"), ("offline", "not reachable")):
                sys.modules["speech_recognition"] = fake_module(outcome)
                with self.assertRaises(RuntimeError) as cm:
                    voice.listen_once("en")
                self.assertIn(text, str(cm.exception))
            sys.modules["speech_recognition"] = None                                # package not installed
            ok, msg = voice.stt_available()
            self.assertFalse(ok)
            self.assertIn("pip install SpeechRecognition pyaudio", msg)
            with self.assertRaises(RuntimeError):
                voice.listen_once("en")
        finally:
            if old == "missing":
                sys.modules.pop("speech_recognition", None)
            else:
                sys.modules["speech_recognition"] = old

    def test_all_languages_have_a_recognition_code(self):
        self.assertEqual(set(voice.STT_CODE), set(I.LANGS))


class DefaultsTests(unittest.TestCase):
    def test_new_features_have_toggles_and_safe_defaults(self):
        keys = {k for k, _ in dbm.FEATURES}
        for k in ("feat_assistant", "feat_assistant_fab", "feat_assistant_voice", "feat_voice_input", "feat_daily_summary",
                  "feat_summary_on_close", "feat_summary_dayend"):
            self.assertIn(k, keys)
            self.assertIn(k, dbm.DEFAULTS)
        self.assertEqual(dbm.DEFAULTS["feat_voice_input"], "0")                     # online feature is OFF by default
        self.assertEqual(dbm.DEFAULTS["feat_daily_summary"], "0")
        self.assertEqual(dbm.DEFAULTS["feat_assistant_voice"], "0")

    def test_low_stock_level_helper(self):
        fresh()
        self.assertEqual(svc.low_stock_level(), 5)
        dbm.settings.set_many({"low_stock_level": "abc"})
        self.assertEqual(svc.low_stock_level(), 5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
