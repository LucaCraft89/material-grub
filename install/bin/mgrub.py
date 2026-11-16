"""Shared helpers for material-grub tools (stdlib only)."""
import json, re
from pathlib import Path

def load_rules(pkg): return json.loads((Path(pkg) / "rules.json").read_text())

def key_for(title, rules):
    """Match an entry title (case-insensitive, token based) to a catalog key; None if unknown/Windows."""
    toks = re.findall(r"[a-z0-9]+", title.lower())
    if "windows" in toks or "microsoft" in toks: return None
    for r in rules:
        t = r["tokens"]; n = len(t)
        if any(toks[i:i + n] == t for i in range(len(toks) - n + 1)): return r["key"]
        if "".join(t) in toks: return r["key"]
    return None
