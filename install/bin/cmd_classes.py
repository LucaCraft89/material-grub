"""Annotate grub.cfg for the Material theme and refresh BLS mirrors. stdlib only. Idempotent.
 - titles -> catalog class (case-insensitive), Windows 10/11 detection
 - unique per-entry classes (mg_xxxx) so each kernel/recovery/advanced entry gets its own scene
 - menu.json: the entries in real GRUB menu order, per menu level (the list/clean styles draw the siblings of the selected entry)
 - Fedora BLS: top level = default kernel, 'Advanced options' submenu = the rest (via mirror dirs; system files untouched)
usage: material-grub-classes GRUB_CFG [--pkg DIR] [--bls DIR] [--loader DIR] [--blsbase /loader] [--mirrors DIR --mirrorbase GRUBPATH] [--fallback-all] [--state FILE] [--default ID]
 --mirrors/--mirrorbase: where the structured BLS mirrors live (default: inside --loader). Immutable (ostree) systems keep them outside /boot/loader,
   because ostree swaps that directory on every deployment.  --fallback-all adds a raw 'All boot entries' submenu that reads the live entries,
   so a stale mirror can never hide the newest deployment."""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import grubscript
import mgoverrides
import mgrub
import mgsafe


def arg(n, d=None):
    return sys.argv[sys.argv.index(n) + 1] if n in sys.argv else d


FALLBACK = "--fallback-all" in sys.argv
MARK = "# material-grub: classes applied"


def os_name():
    try:
        for l in Path(os.environ.get("OS_RELEASE", "/etc/os-release")).read_text().splitlines():
            if l.startswith("NAME="):
                return l.split("=", 1)[1].strip('"')
    except Exception:
        pass
    return "Linux"


def windows_key(device):
    try:
        with tempfile.TemporaryDirectory() as mp:
            subprocess.run(["mount", "-o", "ro", device, mp], check=True, capture_output=True)
            try:
                for p in Path(mp).rglob("*"):
                    if p.name.lower() == "bootmgfw.efi":
                        s = p.read_bytes()
                        u = s.decode("utf-16le", "ignore") + s[1:].decode("utf-16le", "ignore")
                        m = re.search(r"10\.0\.(\d{5})\.", u)
                        if m:
                            return "windows11" if int(m.group(1)) >= 22000 else "windows10"
            finally:
                subprocess.run(["umount", mp], capture_output=True)
    except Exception:
        pass
    return "windows11"


def key_of(title, cls=()):
    k = mgrub.key_for(title, rules)
    if k:
        return k
    if re.search(r"windows|microsoft", title, re.I):
        d = re.search(r"\(on (/dev/[^)\s]+)\)", title)
        return windows_key(d.group(1)) if d else "windows11"
    for c in cls:
        if c in alias2key:
            return alias2key[c]
    return "tux"


def mkentry(title, key, kind, level, cls, **kw):
    info = mgrub.parse_title(title)
    e = {"class": cls, "key": key, "kind": kind, "level": level, "title": title, **info}
    e.update(kw)
    return e


bls_entries = []
BLS_MARK = "# material-grub: structured BLS entries"


def group_of(key):
    base = key.split("~", 1)[0]
    return "windows" if base in ("windows10", "windows11") else "system" if base in ("firmware", "reboot", "shutdown") else "linux"


def customise(text, cfg_entries, bls_at, ov, log=print):
    """Apply the user's `hidden`, `order` and `groups` overrides to the annotated grub.cfg. Only whole menuentry/submenu blocks that stand at the
    top level of the script (not inside if/while/function) are touched: hidden ones are replaced by a comment, the others swap places with each
    other, so everything between the blocks stays where it is. The blscfg block counts as one movable item that belongs to the Linux group.
    Returns (text, cfg_entries, bls_at). Anything unusual (a numeric `set default`) leaves everything as it was."""
    wants = bool(ov["order"] or ov["groups"] or any(r.get("hidden") for r in ov["entries"]))
    if not wants:
        return text, cfg_entries, bls_at
    if re.search(r'^\s*set\s+default\s*=\s*"?\d', text, re.M):
        log("material-grub: overrides: grub.cfg selects its default entry by number, so entries are not hidden or reordered")
        return text, cfg_entries, bls_at
    by_class = {e["class"]: e for e in cfg_entries}

    def info(ge):
        return by_class.get(next((c for c in ge.classes if c.startswith("mg_")), None))

    def descendants_of(root_class):
        out, todo = set(), [root_class]
        while todo:
            c = todo.pop()
            for e in cfg_entries:
                if e.get("parent") == c and e["class"] not in out:
                    out.add(e["class"])
                    todo.append(e["class"])
        return out

    # 1. hidden: cut the blocks out
    sc = grubscript.scan(text)
    cuts = []
    for ge in sc.entries:
        d = info(ge)
        if d is not None and not ge.guarded and ge.end is not None and mgoverrides.rule_for(ov, d).get("hidden"):
            cuts.append((ge, d))
    gone = set()
    for ge, d in cuts:
        gone.add(d["class"])
        gone |= descendants_of(d["class"])
    cuts = [(ge, d) for ge, d in cuts if not any(a in gone and a != d["class"] and d["class"] in descendants_of(a) for a in gone)]
    if cuts:
        out, last = [], 0
        for ge, d in sorted(cuts, key=lambda t: t[0].start):
            out += [text[last : ge.start], "# material-grub: hidden by overrides.json: " + re.sub(r"\s+", " ", d["title"])]
            last = ge.end
        out.append(text[last:])
        text = "".join(out)
        cfg_entries = [e for e in cfg_entries if e["class"] not in gone]
        by_class = {e["class"]: e for e in cfg_entries}
    # 2. order: swap the movable blocks between the slots they occupy
    if not (ov["order"] or ov["groups"]):
        return text, cfg_entries, bls_at
    sc = grubscript.scan(text)
    items = []  # (start, end, class or None for the BLS block)
    for ge in sc.entries:
        d = info(ge)
        if d is not None and ge.parent is None and not ge.guarded and ge.end is not None:
            items.append((ge.start, ge.end, d["class"]))
    i = text.find(BLS_MARK)
    if i >= 0:
        i = text.rfind("\n", 0, i) + 1
        j = text.find("\nunset blsdir", i) + 1 if "\nunset blsdir" in text[i:] else -1
        j = text.find("\n", j) + 1 if j >= 0 else -1
        fb = next((ge for ge in sc.entries if ge.title.startswith("All boot entries") and ge.start >= i), None)
        if fb is not None and fb.end is not None and fb.start - j < 4:
            j = text.find("\n", fb.end) + 1 if text.find("\n", fb.end) >= 0 else len(text)
        if j > i:
            items.append((i, j, None))
    items.sort()
    if len(items) < 2:
        return text, cfg_entries, bls_at
    names = list(ov["groups"]) + [n for n in ("linux", "windows", "system") if n not in ov["groups"]]

    def rank(item):
        cls = item[2]
        e = by_class.get(cls) if cls else None
        g = names.index(group_of(e["key"] if e else "linux")) if ov["groups"] else 0
        o = next((n for n, m in enumerate(ov["order"]) if e and mgoverrides.matches(m, e)), len(ov["order"]))
        return g, o

    ranked = sorted(range(len(items)), key=lambda n: (*rank(items[n]), n))
    if ranked == list(range(len(items))):
        return text, cfg_entries, bls_at
    out, last = [], 0
    for slot, n in zip(items, ranked):
        out += [text[last : slot[0]], text[items[n][0] : items[n][1]]]
        last = slot[1]
    out.append(text[last:])
    # the same permutation for the entry state (a root moves together with its submenu children)
    chunks, cur, tops_seen = [], None, 0
    movable = {c for _, _, c in items if c}
    has_bls = any(c is None for _, _, c in items)
    for e in cfg_entries:
        if e.get("level", "top") == "top" and e.get("parent") is None:
            if has_bls and tops_seen == bls_at and not any(c[0] == "BLS" for c in chunks):
                chunks.append(("BLS", []))
            tops_seen += 1
            cur = [e]
            chunks.append((e["class"] if e["class"] in movable else None, cur))
        elif cur is not None:
            cur.append(e)
        else:
            chunks.append((None, [e]))
    if has_bls and not any(c[0] == "BLS" for c in chunks):
        chunks.append(("BLS", []))
    slots = [n for n, c in enumerate(chunks) if c[0] is not None]
    order_of = {c: n for n, (_, _, c) in enumerate(items)}
    order_of["BLS"] = next((n for n, it in enumerate(items) if it[2] is None), None)
    movers = [chunks[n] for n in slots if order_of.get(chunks[n][0]) is not None]
    if movers and len(movers) == len(slots):
        newc = sorted(movers, key=lambda c: ranked.index(order_of[c[0]]))
        for n, c in zip(slots, newc):
            chunks[n] = c
    flat, tops = [], 0
    bls_new = bls_at
    for tag, es in chunks:
        if tag == "BLS":
            bls_new = tops
        for e in es:
            flat.append(e)
            tops += e.get("level", "top") == "top" and e.get("parent") is None
    return "".join(out), flat, bls_new


def annotate(text, bls_confs, mbase, fallback):
    """Add the unique per-entry classes to every menuentry/submenu and restructure `blscfg`.
    The GRUB script is scanned with grubscript (quotes, escapes, nesting, multi-line headers), never matched line by line.
    Returns (new text, entries found, number of entries that come before the blscfg call)."""
    sc = grubscript.scan(text)
    cfg_entries, inserts, ids = [], [], {}
    for e in sc.entries:  # file order, parents before their children
        key = key_of(e.title, e.classes)
        kind = mgrub.kind_of(e.title, key, e.word == "submenu")
        c = mgrub.uid(
            e.level, e.title
        )  # unique per entry, also for plain ones (Windows, Firmware...): their key stays the 2nd class, so the shared class scene is the fallback
        if c not in e.classes:
            inserts.append((e.title_end, f" --class {c}" + (f" --class {key}" if c != key else "")))
        ids[id(e)] = c
        cfg_entries.append(mkentry(e.title, key, kind, e.level, c, parent=ids.get(id(e.parent))))
    lines = grubscript.split_lines(text)
    offsets, pos = [], 0
    for ln in lines:
        offsets.append(pos)
        pos += len(ln)
    replaced, bls_at = [], 0
    for i, ln in enumerate(lines):
        tok = sc.command_at_line(i)
        if tok is None or tok.value != "blscfg":
            continue
        call = mgrub.bls_call(ln.rstrip("\n"))
        if not call:
            continue
        inside = any(
            e.open_brace < offsets[i] and (e.close_brace is None or offsets[i] < e.close_brace) for e in sc.entries
        )
        if inside or not mgrub.bls_restructurable(call):
            if not inside:
                print(
                    f"material-grub: leaving `{ln.strip()}` untouched (its options are not compatible with the Advanced-options structure); entries are themed by class only"
                )
        elif bls_confs:
            bls_at = sum(1 for e in sc.entries if e.title_end < offsets[i])
            replaced.append((offsets[i], offsets[i] + len(ln.rstrip("\n")), bls_block(call, mbase, fallback)))
    edits = [(at, at, ins) for at, ins in inserts] + replaced
    out, last = [], 0
    for start, end, repl in sorted(edits, key=lambda t: t[0]):
        out.append(text[last:start])
        out.append(repl)
        last = end
    out.append(text[last:])
    result = "".join(out)
    return (result if result.endswith("\n") else result + "\n"), cfg_entries, bls_at


def bls_block(call, mbase, fallback):
    osn = os_name()
    k = key_of(osn)
    ac = mgrub.uid("adv-menu", osn)
    ind, bargs = call
    bcmd = ("blscfg " + bargs).strip()
    blk = [
        "# material-grub: structured BLS entries (default kernel here, the rest under Advanced options)",
        f"set blsdir={mbase}/material-top",
        f"if {bcmd}; then true; else unset blsdir; {bcmd}; fi",
        f"submenu 'Advanced options for {osn}' --class {ac} --class {k} --id material-advanced {{",
        f"\tset blsdir={mbase}/material-adv",
        f"\t{bcmd}",
        "}",
        "unset blsdir",
    ]
    if fallback:
        blk += [
            f"submenu 'All boot entries (raw, always current)' --class {k} --id material-fallback {{",
            f"\t{bcmd}",
            "}",
        ]
    return "\n".join(ind + l for l in blk)


def main():
    global alias2key, rules
    cfg = Path(sys.argv[1])
    pkg = Path(arg("--pkg", "/usr/share/material-grub"))
    bls = Path(arg("--bls", "/boot/loader/entries"))
    loader = Path(arg("--loader", "/boot/loader"))
    blsbase = arg("--blsbase", "/loader" if os.path.ismount("/boot") else "/boot/loader")
    mirrors = Path(arg("--mirrors", str(loader)))
    mbase = arg("--mirrorbase", blsbase)
    state = Path(arg("--state", str(mgsafe.state_dir() / "entries.json")))
    cfgstate = state.with_name("cfg-entries.json")
    cfgmeta = state.with_name("cfg-meta.json")
    rules = mgrub.load_rules(pkg)
    ovr = mgoverrides.load()[0]
    classes = json.loads((pkg / "classes.json").read_text())
    alias2key = {a: k for k, al in classes.items() for a in al}
    text = cfg.read_text()
    first = MARK not in text
    bls_confs = sorted(bls.glob("*.conf")) if bls.is_dir() else []
    if first:
        new_text, cfg_entries, bls_at = annotate(text, bls_confs, mbase, FALLBACK)
        ov, problems = mgoverrides.load()
        for pr in problems:
            print(f"material-grub: overrides: {pr}")
        new_text, cfg_entries, bls_at = customise(new_text, cfg_entries, bls_at, ov)
        tmp = cfg.with_name(cfg.name + ".material")
        tmp.write_text(MARK + "\n" + new_text)
        os.chmod(tmp, cfg.stat().st_mode)
        os.replace(tmp, cfg)
        state.parent.mkdir(parents=True, exist_ok=True)
        cfgstate.write_text(json.dumps(cfg_entries))
        cfgmeta.write_text(json.dumps({"bls_at": bls_at}))
        print(f"material-grub: annotated {len(cfg_entries)} grub.cfg entries")
    cfg_entries = json.loads(cfgstate.read_text()) if cfgstate.exists() else []
    try:
        bls_at = json.loads(cfgmeta.read_text())["bls_at"]
    except Exception:
        bls_at = 0  # state from an older version: the BLS block is normally the first thing in the menu
    if bls_confs:

        def parse(f):
            d = {}
            for l in f.read_text(errors="ignore").splitlines():
                if " " in l:
                    k, v = l.split(None, 1)
                    d.setdefault(k, v.strip())
            return f, d

        items = [parse(f) for f in bls_confs]

        def vk(it):
            return [int(x) if x.isdigit() else x for x in re.split(r"(\d+)", it[1].get("version", ""))]

        normal = sorted(
            [i for i in items if "rescue" not in i[0].name.lower() and "rescue" not in i[1].get("title", "").lower()],
            key=lambda i: [(0, x) if isinstance(x, int) else (1, x) for x in vk(i)],
            reverse=True,
        )
        rescue = [i for i in items if i not in normal]
        saved = arg("--default")
        if saved is None:
            for ed in ("grub2-editenv", "grub-editenv"):
                try:
                    o = subprocess.run([ed, "list"], capture_output=True, text=True).stdout
                    m = re.search(r"^saved_entry=(.+)$", o, re.M)
                    if m:
                        saved = m.group(1).strip()
                        break
                except Exception:
                    pass
        default = next((i for i in normal if i[0].stem == saved), normal[0] if normal else None)
        for d in ("material-top", "material-adv"):
            shutil.rmtree(mirrors / d, ignore_errors=True)
            (mirrors / d).mkdir(parents=True, exist_ok=True)

        def mirror(item, where, level, is_default):
            f, d = item
            title = d.get("title", f.stem)
            key = key_of(title, [d["grub_class"]] if "grub_class" in d else [])
            kind = mgrub.kind_of(title, key)
            cls = mgrub.uid(level, title)
            if mgoverrides.rule_for(ovr, {"key": key, "class": cls, "title": title}).get("hidden"):
                return
            lines = [
                l for l in f.read_text(errors="ignore").splitlines() if l.strip() and not l.startswith("grub_class")
            ] + [
                f"grub_class {cls}"
            ]  # GRUB stops parsing a BLS entry at the first blank line, so the class must not follow one
            (mirrors / where / f.name).write_text("\n".join(lines) + "\n")
            bls_entries.append(mkentry(title, key, kind, level, cls, default=is_default))

        if default:
            mirror(default, "material-top", "top", True)
        for it in normal + rescue:
            if it is not default:
                mirror(it, "material-adv", "adv", False)
        osn = os_name()
        k = key_of(osn)
        adv = {
            "class": mgrub.uid("adv-menu", osn),
            "key": k,
            "kind": "advanced",
            "level": "top",
            "title": f"Advanced options for {osn}",
            "count": sum(1 for e in bls_entries if e["level"] == "adv"),
            "os": osn,
        }
        bls_entries.insert(1 if default else 0, adv)
    allents = bls_entries + [
        e
        for e in cfg_entries
        if not (e["kind"] == "advanced" and bls_entries and e["title"].startswith("Advanced options for") and False)
    ]
    state.write_text(json.dumps(allents, indent=0))
    top_bls = [e for e in bls_entries if e["level"] == "top"]
    adv_bls = [e for e in bls_entries if e["level"] == "adv"]
    top_cfg = [e for e in cfg_entries if e.get("level", "top") == "top"]
    at = min(bls_at, len(top_cfg))
    levels = {None: [e["class"] for e in top_cfg[:at] + top_bls + top_cfg[at:]]}
    for e in cfg_entries:
        if e.get("level") == "adv":
            levels.setdefault(e.get("parent") or "cfg-adv", []).append(e["class"])
    if adv_bls:
        levels[top_bls[-1]["class"]] = [e["class"] for e in adv_bls]
    menu = [{"level": "top", "items": levels.pop(None)}] + [
        {"level": "adv", "parent": par, "items": items} for par, items in levels.items()
    ]
    state.with_name("menu.json").write_text(json.dumps(menu, indent=0))
    print(f"material-grub: state has {len(allents)} entries ({len(bls_entries)} from BLS)")
