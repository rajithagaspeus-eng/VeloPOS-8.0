"""Translation dictionary checks; these tests do not access shop databases."""
import unittest
from velopos_qt.i18n import LANGUAGES, MESSAGES, translate


class TranslationTests(unittest.TestCase):
    def test_three_initial_languages(self):
        self.assertEqual(set(LANGUAGES), {"en", "si", "ta"})

    def test_every_preview_message_translated(self):
        english = set(MESSAGES["en"])
        for language in ("si", "ta"):
            with self.subTest(language=language):
                self.assertEqual(set(MESSAGES[language]), english)

    def test_non_english_navigation_translated(self):
        for language in ("si", "ta"):
            self.assertNotEqual(translate(language, "shop_profile"), "Shop profile")

    def test_unknown_language_falls_back_to_english(self):
        self.assertEqual(translate("de", "save"), translate("en", "save"))

    def test_unknown_key_is_visible(self):
        self.assertEqual(translate("si", "missing_id"), "missing_id")


if __name__ == "__main__":
    unittest.main()
