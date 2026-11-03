"""ONE registry of keyboard shortcuts. It both INSTALLS the global keys (App.install_shortcuts) and GENERATES the cheat sheet (F1),
so the sheet can never disagree with the program. Widget-local keys (Enter in the search box, Esc in a dialog ...) are listed here too;
tests/test_phase6_4.py scans the source and fails if a special key is bound anywhere without being registered here.

Plain `<Return>` in an ordinary input box means "confirm" everywhere and is covered by one generic entry."""
import html
from dataclasses import dataclass


@dataclass(frozen=True)
class Shortcut:
    seq: str                 # Tk key sequence, e.g. "<F5>"
    label: str               # what the user presses
    scope: str               # where it works
    desc: str                # what it does
    action: str = ""         # global keys: method called on the CURRENT screen (or the special action 'help')
    where: str = ""          # local keys: the source file that binds it (checked by the tests)

    @property
    def is_global(self):
        return bool(self.action)


REGISTRY = [
    # ---- global keys (installed by the registry)
    Shortcut("<F1>", "F1", "Everywhere", "Show this keyboard-shortcut sheet", action="help"),
    Shortcut("<F2>", "F2", "Billing", "Edit the selected line of the bill (quantity, price, serial no)", action="edit_row"),
    Shortcut("<F4>", "F4", "Billing", "Hold the current bill (park it) and start a new one", action="hold"),
    Shortcut("<F5>", "F5", "Billing", "Pay & print: open the payment window", action="hotkey_pay"),
    # ---- widget-local keys
    Shortcut("<Return>", "Enter", "Billing - search box", "Add the typed barcode, or the first matching item", where="screens/billing.py"),
    Shortcut("<Down>", "Down arrow", "Billing - search box", "Move into the list of matching items", where="screens/billing.py"),
    Shortcut("<Escape>", "Esc", "Billing - search box", "Close the list of matching items", where="screens/billing.py"),
    Shortcut("<Return>", "Enter", "Billing - item list", "Add the selected item to the bill", where="screens/billing.py"),
    Shortcut("<Return>", "Enter", "Billing - quantity window", "Quantity -> price -> add to bill", where="screens/billing.py"),
    Shortcut("<Escape>", "Esc", "Billing - quantity window", "Close the window without adding", where="screens/billing.py"),
    Shortcut("<Return>", "Enter", "Billing - payment window", "Complete & save the bill", where="screens/billing.py"),
    Shortcut("<Return>", "Enter", "Login", "Log in", where="main.py"),
    Shortcut("<Return>", "Enter", "Any input box", "Confirm / go to the next step (Inventory '+ Add stock', stock-take, search ...)", where="*"),
]


def global_shortcuts():
    return [s for s in REGISTRY if s.is_global]


def local_shortcuts():
    return [s for s in REGISTRY if not s.is_global]


def sheet_rows(include_help=True):
    """[(scope, key label, description)] in a sensible order (global first)."""
    rows = [s for s in REGISTRY if include_help or s.action != "help"]
    rows.sort(key=lambda s: (0 if s.scope == "Everywhere" else 1, s.scope, s.label))
    return [(s.scope, s.label, s.desc) for s in rows]


def sheet_text(include_help=True):
    out, last = ["VeloPOS keyboard shortcuts", "=" * 28], None
    for scope, key, desc in sheet_rows(include_help):
        if scope != last:
            out += ["", scope]
            last = scope
        out.append(f"  {key:<12} {desc}")
    return "\n".join(out)


def sheet_html(shop="VeloPOS", include_help=True):
    rows, last, body = sheet_rows(include_help), None, []
    for scope, key, desc in rows:
        if scope != last:
            body.append(f"<tr><th colspan='2' style='text-align:left;background:#eee;padding:6px 8px'>{html.escape(scope)}</th></tr>")
            last = scope
        body.append(f"<tr><td style='padding:4px 8px;white-space:nowrap'><b>{html.escape(key)}</b></td><td style='padding:4px 8px'>{html.escape(desc)}</td></tr>")
    return (f"<html><head><meta charset='utf-8'><title>Keyboard shortcuts</title></head><body style='font-family:Segoe UI,Arial,sans-serif;margin:24px'>"
            f"<h2>{html.escape(shop)} - keyboard shortcuts</h2><table style='border-collapse:collapse;min-width:520px'>{''.join(body)}</table></body></html>")
