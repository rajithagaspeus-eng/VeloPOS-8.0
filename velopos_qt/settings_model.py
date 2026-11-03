"""Safe adapter for a narrow set of existing VeloPOS settings.

The importing process MUST set VELOPOS_HOME to an isolated directory before
importing velopos.database. This package is a preview, not a license bypass.
"""
from dataclasses import dataclass

SHOP_FIELDS = ("shop_name", "phone", "address", "currency", "bank_name", "bank_branch", "bank_acc", "bank_holder")
APPEARANCE_FIELDS = ("theme", "accent", "font_family", "font_size")
ALLOWED_FIELDS = frozenset(SHOP_FIELDS + APPEARANCE_FIELDS)


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
        # Existing API commits in one database transaction.
        self.store.set_many(clean)
        return clean
