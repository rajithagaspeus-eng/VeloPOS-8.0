"""Safe adapter for a narrow set of existing VeloPOS settings.

The importing process MUST set VELOPOS_HOME to an isolated directory before
importing velopos.database. This package is a preview, not a license bypass.
"""
from dataclasses import dataclass

SHOP_FIELDS = ("shop_name", "phone", "address", "currency", "bank_name", "bank_branch", "bank_acc", "bank_holder")
APPEARANCE_FIELDS = ("theme", "accent", "font_family", "font_size")
# Preview-only configuration fields. Printer enumeration and device I/O stay disabled.
PRINT_FIELDS = ("printer_brand", "print_mode", "paper_size", "receipt_footer", "print_copies")
ALLOWED_FIELDS = frozenset(SHOP_FIELDS + APPEARANCE_FIELDS + PRINT_FIELDS)
PRINTER_BRANDS = ("Xprinter", "Epson", "Other ESC/POS")
PRINT_MODES = ("Windows RAW (ESC/POS)", "Windows driver (any printer)",
               "LAN / Network (IP)", "COM / Bluetooth serial", "Browser only")
PAPER_SIZES = ("80mm", "58mm", "A5", "A4")



@dataclass
class SettingsAdapter:
    store: object

    def read(self):
        return {key: str(self.store.get(key)) for key in ALLOWED_FIELDS}

    def save(self, updates):
        if not isinstance(updates, dict):
            raise TypeError("updates must be a dictionary")
        invalid = set(updates) - ALLOWED_FIELDS
        if invalid:
            raise ValueError("Unsupported settings: " + ", ".join(sorted(invalid)))
        clean = {key: str(value).strip() for key, value in updates.items()}
        if "shop_name" in clean and not clean["shop_name"]:
            raise ValueError("Shop name cannot be empty")
        if "font_size" in clean:
            try:
                size = int(clean["font_size"])
            except ValueError as exc:
                raise ValueError("Font size must be a number") from exc
            if not 11 <= size <= 28:
                raise ValueError("Font size must be between 11 and 28")
        if "theme" in clean and clean["theme"] not in ("light", "dark", "system"):
            raise ValueError("Invalid theme")
        choices = {
            "printer_brand": PRINTER_BRANDS,
            "print_mode": PRINT_MODES,
            "paper_size": PAPER_SIZES,
        }
        for key, accepted in choices.items():
            if key in clean and clean[key] not in accepted:
                raise ValueError("Invalid " + key)
        if "print_copies" in clean:
            try:
                copies = int(clean["print_copies"])
            except ValueError as exc:
                raise ValueError("Print copies must be a whole number") from exc
            if not 1 <= copies <= 5:
                raise ValueError("Print copies must be between 1 and 5")
        if "receipt_footer" in clean and len(clean["receipt_footer"]) > 250:
            raise ValueError("Receipt footer is too long")
        # Existing API commits in one database transaction.
        self.store.set_many(clean)
        return clean
