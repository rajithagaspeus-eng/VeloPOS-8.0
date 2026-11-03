"""Static checks (no GUI needed):  python tests/check_static.py
 1) every .py compiles;  2) names that are used but never defined/imported anywhere in the module;
 3) every app.xxx / self.app.xxx / a.xxx used by screens & dialogs exists on the App class."""
import ast, builtins, glob, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FILES = sorted(glob.glob(os.path.join(ROOT, "velopos", "**", "*.py"), recursive=True))
bad = 0


def defined_names(tree):
    names = set(dir(builtins)) | {"__file__", "__name__", "__compiled__"}
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(n.name)
        if isinstance(n, ast.arg):
            names.add(n.arg)
        if isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del)):
            names.add(n.id)
        if isinstance(n, (ast.Import, ast.ImportFrom)):
            for a in n.names:
                names.add((a.asname or a.name).split(".")[0])
        if isinstance(n, ast.ExceptHandler) and n.name:
            names.add(n.name)
        if isinstance(n, (ast.Global, ast.Nonlocal)):
            names.update(n.names)
    return names


for f in FILES:
    src = open(f, encoding="utf-8").read()
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        print("SYNTAX", f, e); bad += 1; continue
    have = defined_names(tree)
    for n in ast.walk(tree):
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load) and n.id not in have:
            print(f"UNDEFINED NAME  {os.path.relpath(f, ROOT)}:{n.lineno}  {n.id}"); bad += 1

# ---- App attributes
main = ast.parse(open(os.path.join(ROOT, "velopos", "main.py"), encoding="utf-8").read())
app_cls = next(n for n in main.body if isinstance(n, ast.ClassDef) and n.name == "App")
attrs = set()
for n in ast.walk(app_cls):
    if isinstance(n, (ast.FunctionDef,)):
        attrs.add(n.name)
    if isinstance(n, ast.Attribute) and isinstance(n.ctx, ast.Store) and isinstance(n.value, ast.Name) and n.value.id == "self":
        attrs.add(n.attr)
TK = {"after", "clipboard_clear", "clipboard_append", "destroy", "winfo_toplevel", "winfo_exists", "winfo_children",
      "protocol", "configure", "title", "geometry"}
used = {}
for f in FILES:
    rel = os.path.relpath(f, ROOT)
    if rel.endswith("main.py"):
        continue
    src = open(f, encoding="utf-8").read()
    for m in re.finditer(r"(?<![\w.])(?:self\.app|app|a)\.([A-Za-z_]\w*)", src):
        used.setdefault(m.group(1), set()).add(rel)
missing = {k: v for k, v in used.items() if k not in attrs and k not in TK}
for k, v in sorted(missing.items()):
    print("APP ATTRIBUTE MISSING:", k, sorted(v)); bad += 1
print(f"checked {len(FILES)} files, {len(used)} distinct app.* attributes -> {'OK' if not bad else str(bad) + ' PROBLEM(S)'}")
sys.exit(1 if bad else 0)
