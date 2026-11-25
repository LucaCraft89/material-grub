"""What moved out of material-grub into material_boot, and how to build a copy of material-grub's `install/bin` that uses the core instead.

This is the one table both gates read (tests/snapshot/snapshot.py renders pictures with it, tests/gate/grub_suites.py runs material-grub's own unit suites with
it). Grow it with every module that moves: the gates then cover the move. `apply_moves` also checks itself, so a gate that silently runs material-grub's own
code cannot pass.
"""

import ast
from pathlib import Path

# material-grub module -> the material_boot module that replaces it entirely (the old module name becomes a one-line shim).
MOVED = {
    "mgoverrides": "overrides",
    "mgseeds": "seeds",
    "mgpalette": "palette",
    "mgscenes": "scenes",
    "mgcustom": "custom",
    "mgmigrate": "migrate",
    "mgpresets": "presets",
}
# Modules that were only partly moved: material-grub module -> [(material_boot module, [names that moved])]. The original file is rebuilt without those
# definitions and imports them from the core, which is what material-grub's own switch-over does.
PARTIAL = {
    "mgrub": [
        ("conf", ["CONF_DEFAULTS", "CONF_CHOICES", "load_conf", "_conf_ok", "write_conf"]),
        ("titles", ["load_rules", "key_for", "uid", "parse_title", "kind_of"]),
        ("catalog", ["GENERIC"]),
    ],
    "installer": [("events", ["LineEvents", "Tee", "open_log"])],
    "mgdetect": [
        (
            "state",
            ["STATE_VERSION", "version_tuple", "_state_dir", "state_path", "read", "write", "record", "owner_of"],
        ),
    ],
}


# Modules that do not live in install/bin: name -> the directory, relative to install/bin. They are covered when the whole checkout is there (the suites gate)
# and skipped when only bin/ was copied (the picture snapshot).
ELSEWHERE = {"installer": ".."}


def describe():
    return f"the core's {', '.join(MOVED.values())} and, from {', '.join(PARTIAL)}, {', '.join(m for ms in PARTIAL.values() for m, _ in ms)}"


def rebuilt(source, moves):
    """`source` (a module's text) without the top-level definitions named in `moves`, plus an import of them from the core after the docstring."""
    tree = ast.parse(source)
    gone = {n for _mod, names in moves for n in names}

    def defined(node):
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            return {node.name}
        if isinstance(node, ast.Assign):
            return {t.id for t in node.targets if isinstance(t, ast.Name)}
        return set()

    kept = [n for n in tree.body if not (defined(n) and defined(n) <= gone)]
    removed = {x for n in tree.body for x in defined(n)} & gone
    if removed != gone:
        raise SystemExit(
            f"the original no longer defines {sorted(gone - removed)}: update PARTIAL in tests/gate/moves.py"
        )
    imports = [ast.parse(f"from material_boot.{mod} import {', '.join(names)}").body[0] for mod, names in moves]
    at = (
        1 if kept and isinstance(kept[0], ast.Expr) and isinstance(getattr(kept[0], "value", None), ast.Constant) else 0
    )
    tree.body = kept[:at] + imports + kept[at:]
    return ast.unparse(ast.fix_missing_locations(tree)) + "\n"


def location(bindir, name):
    """The file of material-grub module `name`, or None when it is an ELSEWHERE module that is not part of this copy."""
    f = Path(bindir) / ELSEWHERE.get(name, ".") / f"{name}.py"
    if name in ELSEWHERE and not f.is_file():
        return None
    return f


def check_gate(new):
    """Every moved module is a shim, and every moved definition of a partial module is imported, not defined (a gate that silently runs the old code
    would pass everything)."""
    for old, mod in MOVED.items():
        if f"material_boot import {mod}" not in (new / f"{old}.py").read_text():
            raise SystemExit(f"gate error: {old}.py is not a shim for material_boot.{mod}")
    for old, moves in PARTIAL.items():
        f = location(new, old)
        if f is None:
            continue
        tree = ast.parse(f.read_text())
        imported = {a.name for n in tree.body if isinstance(n, ast.ImportFrom) for a in n.names}
        defined = {n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
        for _mod, names in moves:
            for n in names:
                if n not in imported or n in defined:
                    raise SystemExit(f"gate error: {old}.{n} is not taken from the core")


def apply_moves(bindir):
    """Rewrite the moved modules in `bindir` (a COPY of material-grub's install/bin) to use the core, then check that it worked."""
    bindir = Path(bindir)
    for old, mod in MOVED.items():
        (bindir / f"{old}.py").write_text(
            f"import sys\nfrom material_boot import {mod}\n\nsys.modules[__name__] = {mod}\n"
        )
    for old, moves in PARTIAL.items():
        f = location(bindir, old)
        if f is not None:
            f.write_text(rebuilt(f.read_text(), moves))
    check_gate(bindir)
