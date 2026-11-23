import { api } from "/api.js";
import { h, icon, toast, hint, flip, WavyProgress } from "/ui.js";

// ---------------------------------------------------------------- state
const clone = (x) => JSON.parse(JSON.stringify(x));
const S = {
  srv: null, // what the server last said
  draft: null, // {conf, overrides}: what the user is editing
  base: "", // JSON of the draft as last applied/loaded
  view: "overview",
  sel: null, // class of the selected entry
  dark: matchMedia("(prefers-color-scheme: dark)").matches,
  status: null,
  update: null,
  log: [], // events of the last job
  palette: {},
  pv: { n: 0 },
  plymouthCmdline: false, // the person's permission to edit the kernel command line / mkinitcpio hooks; asked every session, never saved
};
const VIEWS = [
  ["overview", "Overview", "overview"],
  ["style", "Style", "style"],
  ["entries", "Entries", "entries"],
  ["colours", "Colours", "colours"],
  ["ventoy", "Ventoy", "ventoy"],
  ["presets", "Presets", "presets"],
  ["update", "Update", "update"],
  ["logs", "Logs", "logs"],
];
// The Boot splash page exists only when the optional Plymouth part is installed (the server says so in /api/state).
const views = () => (S.srv?.plymouth?.installed ? [...VIEWS.slice(0, 4), ["plymouth", "Boot splash", "plymouth"], ...VIEWS.slice(4)] : VIEWS);
const dirty = () => JSON.stringify(S.draft) !== S.base;
const GROUPS = { linux: "Linux", windows: "Windows", system: "Firmware & power" };

// ---------------------------------------------------------------- overrides helpers (the same rules as install/bin/mgoverrides.py)
const groupOf = (key) => (["windows10", "windows11"].includes(key.split("~")[0]) ? "windows" : ["firmware", "reboot", "shutdown"].includes(key.split("~")[0]) ? "system" : "linux");
const mkey = (m) => Object.keys(m)[0];
const same = (a, b) => mkey(a) === mkey(b) && a[mkey(a)] === b[mkey(b)];
function matches(m, e) {
  const k = mkey(m);
  return k === "title" ? (e.title || "").toLowerCase().includes(m.title.toLowerCase()) : e[k] === m[k];
}
const rules = () => S.draft.overrides.entries;
const effective = (e) => rules().find((r) => matches(r.match, e)) || null;
function topRows() {
  const ents = S.srv.entries.filter((e) => (e.level || "top") === "top" && !e.parent);
  const ov = S.draft.overrides;
  const names = [...ov.groups, ...Object.keys(GROUPS).filter((n) => !ov.groups.includes(n))];
  const rank = (e) => [ov.groups.length ? names.indexOf(groupOf(e.key)) : 0, (() => { const i = ov.order.findIndex((m) => matches(m, e)); return i < 0 ? ov.order.length : i; })()];
  return ents
    .map((e, i) => ({ e, i, r: rank(e) }))
    .sort((a, b) => a.r[0] - b.r[0] || a.r[1] - b.r[1] || a.i - b.i)
    .map((x) => x.e);
}
function setRule(match, patch) {
  const list = rules();
  let r = list.find((x) => same(x.match, match));
  if (!r) { r = { match }; list.push(r); }
  for (const [k, v] of Object.entries(patch)) { if (v === undefined || v === "") delete r[k]; else r[k] = v; }
  if (Object.keys(r).length === 1) list.splice(list.indexOf(r), 1);
}
function matchFor(e, scope = "key") {
  if (scope === "class") return { class: e.class };
  if (scope === "title") return { title: (e.title || "").split(/[(\[]/)[0].trim() || e.title };
  return { key: e.key };
}
const titleOf = (e) => S.srv.catalog[e.key]?.title || e.key;
function entryLabel(e) {
  const r = effective(e);
  const named = r?.name && !(["advanced", "rescue"].includes(e.kind) && r.match.key); // a distro-wide name is for the main entry
  return (named && r.name) || (e.kind === "kernel" ? titleOf(e) : e.kind === "advanced" ? "Advanced options" : e.kind === "rescue" ? "Rescue" : titleOf(e));
}

// ---------------------------------------------------------------- boot
async function load(keepDraft = false) {
  S.srv = await api.state();
  if (!keepDraft || !S.draft) {
    S.draft = { conf: clone(S.srv.conf), overrides: clone(S.srv.overrides) };
    S.base = JSON.stringify(S.draft);
  }
  if (!S.srv.entries.some((e) => e.class === S.sel)) S.sel = topRows()[0]?.class || null;
}
function go(v) {
  const [name, arg] = String(v).split(":");
  S.view = views().some((x) => x[0] === name) ? name : "overview";
  history.replaceState(null, "", "#" + S.view);
  if (S.view === "ventoy" && arg && VT.path !== decodeURIComponent(arg)) vtLoad(decodeURIComponent(arg));
  render(true);
  scrollTo({ top: 0 });
}
addEventListener("hashchange", () => go(location.hash.slice(1)));

// ---------------------------------------------------------------- rendering
function render(enter = false) {
  if (!S.srv) return;
  renderRail();
  renderTop();
  const layout = document.getElementById("layout");
  const wide = ["overview", "presets", "update", "logs", "ventoy", "plymouth"].includes(S.view);
  layout.className = "layout" + (wide ? " wide" : "") + (enter ? " enter" : "");
  const view = h("div", { class: "col view" });
  ({ overview: vOverview, style: vStyle, entries: vEntries, colours: vColours, plymouth: vPlymouth, ventoy: vVentoy, presets: vPresets, update: vUpdate, logs: vLogs })[S.view](view);
  layout.replaceChildren(view);
  if (!wide) layout.append(previewPane());
  renderFab();
  if (!wide) schedulePreview();
  if (S.view === "plymouth") schedulePly();
}
function renderRail() {
  const rail = document.getElementById("rail");
  rail.replaceChildren(
    h("div", { class: "brand" }, icon("cookie"), h("div", {}, h("b", {}, "Material GRUB"), h("small", {}, S.srv.version ? "v" + S.srv.version : "not installed"))),
    ...views().map(([id, label, ic]) =>
      h("button", { class: "nav", "aria-current": S.view === id ? "page" : false, onClick: () => go(id) }, icon(ic), h("span", {}, label), id === "entries" && S.draft.overrides.entries.length ? h("span", { class: "badge" }, S.draft.overrides.entries.length) : null),
    ),
    h("div", { class: "spacer" }),
    h("button", { class: "nav", onClick: toggleTheme, "aria-label": "Switch between light and dark interface" }, icon(S.dark ? "sun" : "moon"), h("span", {}, S.dark ? "Light" : "Dark")),
  );
}
function toggleTheme() {
  const dark = !(document.documentElement.dataset.theme ? document.documentElement.dataset.theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.dataset.theme = dark ? "dark" : "light";
  render();
}
function renderTop() {
  const t = document.getElementById("topbar");
  const title = views().find((v) => v[0] === S.view)[1];
  t.replaceChildren(
    ...[
      h("h1", {}, title),
      dirty() ? h("span", { class: "chip dirty" }, "Unsaved changes") : null,
      dirty() ? h("button", { class: "btn text small", onClick: () => { S.draft = JSON.parse(S.base); render(); toast("Changes discarded"); } }, icon("reset"), "Discard") : null,
    ].filter(Boolean),
  );
  document.title = (dirty() ? "• " : "") + title + " · Material GRUB";
}
function renderFab() {
  const f = document.getElementById("fabbar");
  if (S.view === "ventoy") return f.replaceChildren(); // the stick has its own button
  f.replaceChildren(
    h("button", { class: "btn fab" + (dirty() ? " attention" : ""), disabled: !dirty() || !S.srv.installed, onClick: applyDraft, title: dirty() ? "Write your changes to GRUB (asks for your password or fingerprint)" : "Nothing to apply yet" }, icon("apply"), "Apply to GRUB"),
  );
}
const touch = () => { renderTop(); renderFab(); renderRail(); schedulePreview(); if (S.view === "plymouth") schedulePly(); };

// ---------------------------------------------------------------- helpers for forms
function card(title, ...kids) {
  return h("section", { class: "card" }, title ? h("div", { class: "card-head" }, h("h2", {}, title)) : null, ...kids);
}
function field(label, help, input) {
  return h("div", { class: "field" }, h("label", {}, label, help ? hint(help) : null), input);
}
function toggle(label, checked, onChange, help, disabled) {
  const i = h("input", { type: "checkbox", disabled: !!disabled, ...(checked ? { checked: "" } : {}), onChange: (e) => onChange(e.target.checked) });
  i.checked = !!checked;
  return h("label", { class: "switch" }, i, h("span", { class: "track" }), h("span", {}, label), help ? hint(help) : null);
}
function seg(options, value, onPick) {
  return h("div", { class: "seg", role: "group" }, ...options.map(([v, label]) => h("button", { type: "button", "aria-pressed": String(value === v), onClick: () => onPick(v) }, label)));
}
function swatchGrid(value, onPick, extra) {
  return h("div", { class: "swatches" }, ...(extra || []), ...S.srv.seeds.map((s) => h("button", { class: "swatch", type: "button", style: { background: s.color }, title: `${s.name} ${s.color}`, "aria-label": s.name, "aria-pressed": String((value || "").toUpperCase() === s.color), onClick: () => onPick(s.color) })));
}
function hexField(value, onInput, placeholder = "#2E7D32") {
  const i = h("input", { type: "text", value: value || "", placeholder, maxlength: 7, spellcheck: "false", "aria-label": "Colour as #RRGGBB" });
  const picker = h("input", { type: "color", value: /^#[0-9a-f]{6}$/i.test(value || "") ? value : "#2e7d32", style: { width: "52px", height: "52px", border: 0, background: "none", padding: 0 }, "aria-label": "Pick a colour" });
  i.addEventListener("input", () => {
    const ok = /^#[0-9a-f]{6}$/i.test(i.value);
    i.setAttribute("aria-invalid", String(i.value !== "" && !ok));
    if (ok) { picker.value = i.value; onInput(i.value.toUpperCase()); }
  });
  picker.addEventListener("input", () => { i.value = picker.value.toUpperCase(); i.setAttribute("aria-invalid", "false"); onInput(picker.value.toUpperCase()); });
  return h("div", { class: "row" }, i, picker);
}

// ---------------------------------------------------------------- Overview
async function refreshStatus() {
  try { S.status = await api.status(); } catch (e) { toast("Could not run the checks: " + e.message); }
  render();
}
function vOverview(v) {
  const st = S.status;
  v.append(
    h("div", { class: "hero-card" },
      h("div", { class: "row between" },
        h("div", {},
          h("h2", {}, S.srv.installed ? "Your boot menu, your way" : "Material GRUB is not installed yet"),
          h("p", { class: "muted" }, S.srv.installed ? "Pick a style, recolour entries, rename, reorder and hide them, all with a live preview. Nothing changes on your system until you press Apply." : "Install the theme first (sudo ./install.sh), then come back here."),
          h("div", { class: "row" }, h("span", { class: "chip ok" }, "version " + (S.srv.version || "?")), h("span", { class: "chip" }, "style " + S.srv.conf.STYLE), h("span", { class: "chip" }, S.srv.scheme + " scheme"), S.srv.demo ? h("span", { class: "chip warn" }, "no boot entries read yet: showing samples") : h("span", { class: "chip" }, S.srv.entries.length + " menu entries")),
        ),
        h("button", { class: "btn tonal", onClick: () => go("entries") }, icon("entries"), "Edit entries"),
      ),
    ),
    h("div", { class: "grid cols2" },
      ...[["style", "Style", "Four layouts: rail, clean, list and split."], ["colours", "Colours", "One seed colour for everything, or a colour per entry."], ["presets", "Presets", "Save a look and bring it back later."], ["update", "Update", "See what is new and update in one click."]].map(([id, t, d]) =>
        h("button", { class: "style-card", onClick: () => go(id) }, h("b", {}, t), h("span", { class: "muted small" }, d)),
      ),
    ),
    card("Health checks",
      h("div", { class: "row" },
        h("button", { class: "btn tonal small", onClick: refreshStatus }, icon("check"), st ? "Run again" : "Run checks"),
        st ? h("span", { class: "chip " + (st.failed ? "fail" : st.warnings ? "warn" : "ok") }, st.failed ? `${st.failed} failed` : st.warnings ? `${st.warnings} warning(s)` : "everything is fine") : h("span", { class: "muted small" }, "Checks the theme files, grub.cfg, your configuration and overrides."),
        hint("Runs the same checks as `material-grub doctor`: nothing is changed. Some checks need root to read grub.cfg and say so."),
      ),
      st ? h("div", { style: { marginTop: "14px" } }, ...st.checks.map((c) => h("div", { class: "status-row" }, h("span", { class: "chip " + ({ ok: "ok", warn: "warn", FAIL: "fail", info: "" }[c.status] || "") }, c.status === "FAIL" ? "fail" : c.status), h("span", { class: "what" }, c.check), h("span", { class: "detail" }, c.detail)))) : null,
    ),
  );
  if (S.srv.problems.length) v.append(card("Your overrides file has a problem", ...S.srv.problems.map((p) => h("p", { class: "muted small mono" }, p))));
}

// ---------------------------------------------------------------- Style
const WIRE = {
  rail: `<rect x="8" y="10" width="14" height="60" rx="7" fill="currentColor" opacity=".25"/><rect x="40" y="16" width="64" height="30" rx="15" fill="currentColor" opacity=".35"/><rect x="48" y="52" width="48" height="8" rx="4" fill="currentColor" opacity=".6"/>`,
  clean: `<rect x="14" y="2" width="116" height="14" rx="7" fill="currentColor" opacity=".18"/><rect x="14" y="20" width="116" height="40" rx="14" fill="currentColor" opacity=".35"/><rect x="14" y="64" width="116" height="14" rx="7" fill="currentColor" opacity=".18"/>`,
  list: `<g fill="currentColor"><rect x="36" y="10" width="72" height="12" rx="6" opacity=".25"/><rect x="36" y="28" width="72" height="12" rx="6" opacity=".6"/><rect x="36" y="46" width="72" height="12" rx="6" opacity=".25"/><rect x="36" y="64" width="72" height="12" rx="6" opacity=".25"/></g>`,
  split: `<rect x="12" y="14" width="44" height="44" rx="22" fill="currentColor" opacity=".35"/><g fill="currentColor"><rect x="72" y="12" width="60" height="12" rx="6" opacity=".25"/><rect x="72" y="30" width="60" height="12" rx="6" opacity=".6"/><rect x="72" y="48" width="60" height="12" rx="6" opacity=".25"/></g>`,
};
const STYLES = [
  ["rail", "Rail", "A big hero panel with a rail of icons on the left, grouped Linux, Windows, System."],
  ["clean", "Clean", "A big panel per entry; the previous and next entries peek in above and below."],
  ["list", "List", "The whole menu as a centred list of icon and name pills."],
  ["split", "Split", "The logo and name on the left, the list on the right."],
];
function vStyle(v) {
  const c = S.draft.conf;
  const set = (k, val) => { c[k] = val; touch(); };
  v.append(
    card("Layout", h("div", { class: "grid cols2" }, ...STYLES.map(([id, name, desc]) => {
      const b = h("button", { class: "style-card", "aria-pressed": String(c.STYLE === id), onClick: () => { c.STYLE = id; render(); } }, h("svg", { viewBox: "0 0 144 80", html: WIRE[id] }), h("b", {}, name), h("span", { class: "small" }, desc));
      return b;
    }))),
    card("Details",
      h("div", { class: "grid cols2" },
        toggle("Cookie shape", c.COOKIE === "on", (x) => { set("COOKIE", x ? "on" : "off"); render(); }, "The scalloped shape at the top right. Turning it off also hides the firmware logo."),
        toggle("Firmware logo", c.LOGO === "on" && c.COOKIE === "on", (x) => set("LOGO", x ? "on" : "off"), "Your machine's own boot logo (from the firmware) inside the cookie.", c.COOKIE !== "on"),
        toggle("Key hints", c.HINTS === "on", (x) => set("HINTS", x ? "on" : "off"), "The small pills at the bottom: Arrows select, Enter boot, E edit, C console. The keys keep working when hidden."),
        toggle("Raw entry name", c.RAW_NAME === "on", (x) => set("RAW_NAME", x ? "on" : "off"), "A muted line at the very bottom with the entry title exactly as GRUB sees it. Handy when something looks wrong."),
        toggle("Countdown bar", c.COUNTDOWN === "on", (x) => set("COUNTDOWN", x ? "on" : "off"), "The 'Booting in N seconds' bar and label."),
        field("Timeout (seconds)", "Seconds before the default entry boots. Empty keeps GRUB_TIMEOUT (or 5).", h("input", { type: "number", min: 0, max: 9999, value: c.TIMEOUT, placeholder: "default", onInput: (e) => set("TIMEOUT", e.target.value.replace(/\D/g, "").slice(0, 4)) })),
      ),
    ),
    card("Colour scheme", h("p", { class: "muted" }, `This theme was built with the ${S.srv.scheme} scheme. The scheme is baked into the images at build time, so changing it means installing again (sudo ./install.sh --scheme light). The preview can show both.`), seg([["dark", "Preview dark"], ["light", "Preview light"]], S.dark ? "dark" : "light", (x) => { S.dark = x === "dark"; render(); })),
  );
}

// ---------------------------------------------------------------- Entries
function vEntries(v) {
  const ov = S.draft.overrides;
  const rows = topRows();
  const ordered = ov.groups.length > 0;
  v.append(
    card("Menu order",
      h("p", { class: "muted small" }, "Drag entries (or use the arrows) to reorder the menu. Sections decide which kind comes first."),
      h("div", { class: "row" },
        seg([["", "Free order"], ["linux", "Linux first"], ["windows", "Windows first"]], ov.groups[0] || "", (x) => {
          ov.groups = x === "" ? [] : x === "linux" ? ["linux", "windows", "system"] : ["windows", "linux", "system"];
          render();
        }),
        hint("With a section order, entries only move inside their section. 'Free order' lets you mix Linux, Windows and firmware entries any way you like. The real GRUB menu is reordered when you apply."),
      ),
    ),
    card("Entries",
      rows.length ? entryList(rows, ordered) : h("div", { class: "empty" }, "No boot entries known yet."),
      S.srv.demo ? h("p", { class: "muted small" }, "These are sample entries: run sudo material-grub apply once to let the theme read your real menu.") : null,
    ),
  );
  const e = S.srv.entries.find((x) => x.class === S.sel);
  if (e) v.append(entryEditor(e));
}
function entryList(rows, ordered) {
  const box = h("div", { class: "entries", role: "listbox", "aria-label": "Boot menu entries" });
  let last = null;
  const draw = () => {
    box.replaceChildren();
    last = null;
    const cur = topRows();
    for (const e of cur) {
      const g = groupOf(e.key);
      if (ordered && g !== last) box.append(h("div", { class: "group-head", "data-k": "g-" + g }, GROUPS[g]));
      last = g;
      box.append(entryRow(e, cur, ordered, box, draw));
    }
  };
  draw();
  return box;
}
function entryRow(e, cur, ordered, box, redraw) {
  const r = effective(e);
  const col = r?.color || S.srv.catalog[e.key]?.seed;
  const sel = S.sel === e.class;
  const move = (dir) => {
    const i = cur.findIndex((x) => x.class === e.class), j = i + dir;
    if (j < 0 || j >= cur.length) return;
    if (ordered && groupOf(cur[j].key) !== groupOf(e.key)) { toast("Entries stay inside their section. Choose 'Free order' to mix them."); return; }
    reorder(cur, i, j, box, redraw);
  };
  const row = h("div", { class: "entry" + (r?.hidden ? " hidden-entry" : ""), role: "option", tabindex: 0, "aria-selected": String(sel), "data-k": e.class, draggable: "true",
    onClick: () => { S.sel = e.class; render(); },
    onKeydown: (ev) => { if (ev.altKey && ev.key === "ArrowUp") { ev.preventDefault(); move(-1); } else if (ev.altKey && ev.key === "ArrowDown") { ev.preventDefault(); move(1); } else if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); S.sel = e.class; render(); } },
    onDragstart: (ev) => { S.drag = e.class; row.classList.add("dragging"); ev.dataTransfer.effectAllowed = "move"; ev.dataTransfer.setData("text/plain", e.class); },
    onDragend: () => { S.drag = null; row.classList.remove("dragging"); box.querySelectorAll(".over").forEach((x) => x.classList.remove("over")); },
    onDragover: (ev) => { if (S.drag && S.drag !== e.class) { ev.preventDefault(); row.classList.add("over"); } },
    onDragleave: () => row.classList.remove("over"),
    onDrop: (ev) => {
      ev.preventDefault();
      row.classList.remove("over");
      const i = cur.findIndex((x) => x.class === S.drag), j = cur.findIndex((x) => x.class === e.class);
      if (i < 0 || j < 0) return;
      if (ordered && groupOf(cur[i].key) !== groupOf(cur[j].key)) { toast("Entries stay inside their section. Choose 'Free order' to mix them."); return; }
      reorder(cur, i, j, box, redraw);
    },
  },
    h("span", { class: "grip", title: "Drag to reorder (or Alt + arrow keys)" }, icon("grip")),
    h("span", { class: "badge-ico", style: { background: col || "var(--c-primary-container)", color: "#fff" } }, glyphEl(e, r)),
    h("div", { class: "names" }, h("b", {}, entryLabel(e)), h("small", {}, (r?.hidden ? "hidden · " : "") + (e.title || ""))),
    h("button", { class: "btn icon small text", "aria-label": "Move up", onClick: (ev) => { ev.stopPropagation(); move(-1); } }, icon("up")),
    h("button", { class: "btn icon small text", "aria-label": "Move down", onClick: (ev) => { ev.stopPropagation(); move(1); } }, icon("down")),
  );
  return row;
}
function glyphEl(e, r) {
  const ic = r?.icon || "";
  if (ic.startsWith("file:")) return h("img", { src: "/api/icon/" + encodeURIComponent(ic.slice(5)), alt: "", style: { width: "26px", height: "26px", objectFit: "contain", background: "#fff", borderRadius: "6px" } });
  const g = ic || e.key;
  return h("span", { class: "glyph", style: { "--g": `url(/api/glyph/${encodeURIComponent(g)})`, width: "24px", height: "24px" } });
}
function reorder(cur, i, j, box, redraw) {
  const seq = cur.slice();
  const [m] = seq.splice(i, 1);
  seq.splice(j, 0, m);
  const keyCount = {};
  seq.forEach((e) => (keyCount[e.key] = (keyCount[e.key] || 0) + 1));
  const seen = new Set();
  const order = [];
  for (const e of seq) {
    const mt = keyCount[e.key] > 1 || e.kind === "advanced" ? { class: e.class } : { key: e.key };
    const id = JSON.stringify(mt);
    if (!seen.has(id)) { seen.add(id); order.push(mt); }
  }
  S.draft.overrides.order = order;
  flip(box, redraw);
  touch();
}

function entryEditor(e) {
  const r = effective(e) || {};
  const scopeOf = (m) => (!m ? "key" : mkey(m));
  let scope = scopeOf(r.match);
  let titleText = r.match && mkey(r.match) === "title" ? r.match.title : (e.title || "").split(/[(\[]/)[0].trim();
  const cur = () => (scope === "title" ? { title: titleText || e.title } : matchFor(e, scope));
  const patch = (p) => { setRule(r.match || cur(), p); touch(); redrawEditor(); };
  const wrap = h("section", { class: "card high", id: "editor" });
  const redrawEditor = () => { wrap.replaceWith((window.__ed = entryEditor(e))); renderListOnly(); };
  const eff = effective(e) || {};
  wrap.append(
    h("div", { class: "card-head" }, h("h2", {}, "Customise: " + entryLabel(e)), eff.name || eff.color || eff.icon || eff.hidden ? h("button", { class: "btn text small", onClick: () => { setRule(eff.match, { name: undefined, color: undefined, icon: undefined, hidden: undefined }); touch(); redrawEditor(); } }, icon("reset"), "Reset this entry") : null),
    h("div", { class: "grid cols2" },
      field("Name", "Shown in big letters on the entry's screen and in list rows. Leave empty for the default.", h("input", { type: "text", value: eff.name || "", placeholder: entryLabel({ ...e }) === eff.name ? titleOf(e) : entryLabel(e), maxlength: 60, onChange: (ev) => patch({ name: ev.target.value.trim() }) })),
      field("Applies to", "Which entries this customisation covers. 'All of this distro' keeps working after kernel updates; 'Only this entry' stops when its title changes.", h("div", { class: "col" },
        h("select", { onChange: (ev) => { scope = ev.target.value; if (eff.match) { const old = eff.match; const nm = cur(); const rr = rules().find((x) => same(x.match, old)); if (rr) rr.match = nm; } touch(); redrawEditor(); } },
          ...[["key", `All ${titleOf(e)} entries`], ["class", "Only this entry"], ["title", "Entries whose title contains..."]].map(([v, l]) => h("option", { value: v, ...(scope === v ? { selected: "" } : {}) }, l))),
        scope === "title" ? h("input", { type: "text", value: titleText, onChange: (ev) => { titleText = ev.target.value; if (eff.match) { const rr = rules().find((x) => same(x.match, eff.match)); if (rr) rr.match = cur(); } touch(); redrawEditor(); } }) : null,
      )),
    ),
    h("hr"),
    h("div", { class: "field" }, h("label", {}, "Colour", hint("Every entry normally has its brand colour. Pick another one: the whole screen of this entry is re-made in that colour (Material 3 turns it into a full palette).")),
      swatchGrid(eff.color, (c) => patch({ color: c }), [h("button", { class: "swatch", type: "button", style: { background: "repeating-conic-gradient(var(--c-surface-container-highest) 0 25%, var(--c-surface) 0 50%) 0 0/14px 14px" }, title: "Automatic", "aria-label": "Automatic colour", "aria-pressed": String(!eff.color), onClick: () => patch({ color: undefined }) })]),
      hexField(eff.color || "", (c) => patch({ color: c })),
    ),
    h("hr"),
    iconPicker(e, eff, patch),
    h("hr"),
    h("div", { class: "row" }, toggle("Hide this entry from the menu", !!eff.hidden, (x) => patch({ hidden: x || undefined }), "Removes the entry from the GRUB menu (nothing is deleted from disk). Entries GRUB creates inside an if-block, like 'UEFI Firmware Settings', cannot be hidden. Takes effect when you apply.")),
  );
  return wrap;
}
function renderListOnly() { const el = document.querySelector(".entries"); if (el) { const p = el.parentNode; const n = entryList(topRows(), S.draft.overrides.groups.length > 0); p.replaceChild(n, el); } }
function iconPicker(e, eff, patch, src) {
  src = src || { icons: () => S.srv.icons, url: (n) => "/api/icon/" + encodeURIComponent(n), upload: async (name, f) => { const r = await api.uploadIcon(name, f); S.srv.icons = [...new Set([...S.srv.icons, r.name])].sort(); return r; } };
  let q = "";
  const grid = h("div", { class: "icon-grid" });
  const cats = Object.entries(S.srv.catalog).filter(([, c]) => c.glyph).map(([k, c]) => [k, c.title]);
  const draw = () => {
    grid.replaceChildren(
      h("button", { class: "icon-cell", type: "button", title: "Automatic", "aria-pressed": String(!eff.icon), onClick: () => patch({ icon: undefined }) }, "Auto"),
      ...src.icons().map((n) => h("button", { class: "icon-cell", type: "button", title: n, "aria-pressed": String(eff.icon === "file:" + n), onClick: () => patch({ icon: "file:" + n }) }, h("img", { src: src.url(n), alt: n }))),
      ...cats.filter(([k, t]) => !q || (k + t).toLowerCase().includes(q)).map(([k, t]) => h("button", { class: "icon-cell", type: "button", title: t, "aria-label": t, "aria-pressed": String(eff.icon === k), onClick: () => patch({ icon: k }) }, h("span", { class: "glyph", style: { "--g": `url(/api/glyph/${encodeURIComponent(k)})` } }))),
    );
  };
  draw();
  const file = h("input", { type: "file", accept: "image/png,image/jpeg,image/svg+xml,image/webp,image/gif,image/bmp", class: "sr" });
  file.addEventListener("change", async () => {
    const f = file.files[0];
    if (!f) return;
    const name = f.name.replace(/[^A-Za-z0-9._-]/g, "_").replace(/^\.+/, "") || "icon.png";
    try {
      const r = await src.upload(name, f);
      patch({ icon: "file:" + r.name });
      toast("Picture added: " + r.name);
    } catch (err) { toast("Could not add the picture: " + err.message); }
  });
  return h("div", { class: "field" },
    h("label", {}, "Icon", hint("Pick one of the built-in distro icons or add your own picture (PNG, JPEG, SVG, WEBP, GIF, BMP). Your picture is drawn in full colour on a white badge on the entry's screen, and as a one-colour shape in the rail and lists.")),
    h("div", { class: "row" }, h("input", { type: "text", placeholder: "Search icons...", "aria-label": "Search icons", onInput: (ev) => { q = ev.target.value.toLowerCase(); draw(); } }), h("button", { class: "btn tonal", type: "button", onClick: () => file.click() }, icon("upload"), "Add picture..."), file),
    grid,
  );
}

// ---------------------------------------------------------------- Colours
async function loadPalette(seed) {
  if (S.palette[seed]) return S.palette[seed];
  try { S.palette[seed] = await api.palette(seed); } catch { S.palette[seed] = null; }
  return S.palette[seed];
}
function vColours(v) {
  const ov = S.draft.overrides;
  const single = ov.seed.mode === "single";
  const strip = h("div", { class: "palette-strip" });
  const paint = async () => {
    const p = await loadPalette(ov.seed.color);
    if (!p) return;
    const r = p[S.dark ? "dark" : "light"];
    strip.replaceChildren(...["primary", "primaryContainer", "secondary", "secondaryContainer", "tertiary", "tertiaryContainer", "surfaceContainerHigh", "surface"].map((k) => h("div", { style: { background: r[k] }, title: k })));
  };
  v.append(
    card("Colour mode",
      seg([["multi", "A colour per entry"], ["single", "One colour for everything"]], ov.seed.mode, (x) => { ov.seed.mode = x; render(); }),
      h("p", { class: "muted", style: { marginTop: "12px" } }, single ? "Every entry uses the palette made from your seed colour: a calm, uniform theme. Entries you colour by hand keep their own colour." : "Every distro keeps its brand colour (Fedora blue, Ubuntu orange, ...). Pick the single mode for one uniform theme."),
    ),
    card("Seed colour",
      h("p", { class: "muted small" }, single ? "Material 3 makes surfaces, containers and accents from this one colour." : "Used when you switch to 'One colour for everything'."),
      swatchGrid(ov.seed.color, (c) => { ov.seed.color = c; ov.seed.mode = "single"; render(); }),
      h("div", { style: { marginTop: "14px" } }, field("Any other colour", "Type #RRGGBB or use the picker. A grey makes a monochrome theme.", hexField(ov.seed.color, (c) => { ov.seed.color = c; ov.seed.mode = "single"; touch(); paint(); }))),
      h("div", { style: { marginTop: "16px" } }, h("div", { class: "label" }, "Resulting palette (" + (S.dark ? "dark" : "light") + ")"), strip),
    ),
  );
  paint();
}

// ---------------------------------------------------------------- Ventoy
const VT = { sticks: null, path: "", data: null, draft: null, base: "", sel: null, busy: false };
const vtDirty = () => VT.draft && JSON.stringify(VT.draft) !== VT.base;
async function vtLoad(path) {
  try {
    VT.data = await api.ventoyState(path);
    VT.path = path;
    VT.draft = { conf: clone(VT.data.conf), overrides: clone(VT.data.overrides) };
    VT.base = JSON.stringify(VT.draft);
    VT.sel = VT.data.files[0]?.path || null;
  } catch (e) { VT.data = null; toast(e.message); }
  render();
}
async function vtDetect() {
  VT.busy = true; render();
  try { VT.sticks = (await api.ventoySticks()).sticks; } catch (e) { toast(e.message); VT.sticks = []; }
  VT.busy = false; render();
}
function vVentoy(v) {
  const sticks = VT.sticks;
  v.append(
    card("Your Ventoy stick",
      h("p", { class: "muted" }, "Plug in a Ventoy stick and mount it (your file manager does this when you open it). The theme is written to the stick itself; no root is needed."),
      h("div", { class: "row" },
        h("button", { class: "btn tonal", onClick: vtDetect, disabled: VT.busy }, icon("ventoy"), VT.busy ? "Looking..." : sticks ? "Look again" : "Find sticks"),
        hint("Looks for disks with a Ventoy partition, and for a /ventoy folder on removable drives."),
      ),
      sticks && !sticks.length ? h("p", { class: "muted", style: { marginTop: "12px" } }, "No Ventoy stick found. You can also type the mount point below.") : null,
      sticks?.length ? h("div", { class: "grid cols2", style: { marginTop: "14px" } }, ...sticks.map((s) => h("div", { class: "card high" }, h("h3", {}, s.label || "Ventoy"), h("p", { class: "muted small" }, [s.model, s.fstype, s.size ? (s.size / 1e9).toFixed(1) + " GB" : ""].filter(Boolean).join(" · ")), s.mounted ? h("button", { class: "btn small", onClick: () => vtLoad(s.path) }, "Edit this stick") : h("span", { class: "chip warn" }, "not mounted")))) : null,
      h("div", { class: "row", style: { marginTop: "14px" } }, (() => { const i = h("input", { type: "text", placeholder: "/run/media/you/Ventoy", "aria-label": "Mount point of the stick", style: { flex: "1" } }); return h("div", { class: "row", style: { flex: "1" } }, i, h("button", { class: "btn small outline", onClick: () => vtLoad(i.value.trim()) }, "Open")); })()),
    ),
  );
  if (!VT.data) return;
  const d = VT.draft, c = d.conf;
  const set = (k, val) => { c[k] = val; vtTouch(); };
  v.append(
    card("Look on the stick",
      h("p", { class: "muted small mono" }, VT.data.path + (VT.data.installed.length ? " · themed for " + VT.data.installed.join(", ") : " · not themed yet")),
      h("div", { class: "grid cols2" },
        h("div", { class: "field" }, h("label", {}, "Style", hint("Ventoy has two layouts: 'list' (the distro's logo and name on the left, the ISO list on the right) and 'full' (a full-screen picker, one ISO at a time).")), seg([["list", "List"], ["full", "Full screen"]], c.STYLE === "full" ? "full" : "list", (x) => set("STYLE", x))),
        h("div", { class: "field" }, h("label", {}, "Mode", hint("Dynamic works for any ISO you add later (rules match the file name). Snapshot draws one scene per file that is on the stick right now.")), seg([["dynamic", "Dynamic"], ["snapshot", "Snapshot"]], c.MODE, (x) => set("MODE", x))),
        toggle("Cookie shape", c.COOKIE === "on", (x) => { set("COOKIE", x ? "on" : "off"); render(); }, "The scalloped shape at the top right, with the Ventoy logo inside."),
        toggle("Ventoy logo", c.LOGO === "on" && c.COOKIE === "on", (x) => set("LOGO", x ? "on" : "off"), "The Ventoy logo inside the cookie.", c.COOKIE !== "on"),
        toggle("Key hints", c.HINTS === "on", (x) => set("HINTS", x ? "on" : "off"), "The pills at the bottom with Ventoy's keys (F1 Help, F2 Browse, ...)."),
        toggle("Raw file name", c.RAW_NAME === "on", (x) => set("RAW_NAME", x ? "on" : "off"), "In the full-screen picker: the real file name in a pill under the title."),
      ),
      h("hr"),
      h("div", { class: "field" }, h("label", {}, "Colours", hint("One colour for the whole stick, or every distro in its own brand colour.")),
        seg([["multi", "A colour per distro"], ["single", "One colour"]], d.overrides.seed.mode, (x) => { d.overrides.seed.mode = x; vtTouch(); render(); }),
        d.overrides.seed.mode === "single" ? swatchGrid(d.overrides.seed.color, (col) => { d.overrides.seed.color = col; vtTouch(); render(); }) : null),
    ),
    card("Your images (" + VT.data.files.length + ")",
      VT.data.files.length ? h("div", { class: "entries" }, ...VT.data.files.map((f) => {
        const r = vtRule(f);
        return h("div", { class: "entry", role: "option", tabindex: 0, "aria-selected": String(VT.sel === f.path), onClick: () => { VT.sel = f.path; render(); }, onKeydown: (ev) => { if (ev.key === "Enter") { VT.sel = f.path; render(); } } },
          h("span", { class: "badge-ico", style: { background: r?.color || S.srv.catalog[f.key]?.seed || "var(--c-primary-container)", color: "#fff" } }, h("span", { class: "glyph", style: { "--g": `url(/api/glyph/${encodeURIComponent(S.srv.catalog[f.key]?.glyph ? f.key : "tux")})` } })),
          h("div", { class: "names" }, h("b", {}, r?.name || f.name), h("small", {}, f.path + " · " + (S.srv.catalog[f.key]?.title || f.key))),
          r ? h("span", { class: "chip ok" }, "customised") : null);
      })) : h("div", { class: "empty" }, "No ISO, WIM, IMG or VHD files on the stick yet. Dynamic mode still works for files you add later."),
    ),
  );
  const f = VT.data.files.find((x) => x.path === VT.sel);
  if (f) v.append(vtEditor(f));
  v.append(h("div", { class: "row" },
    h("button", { class: "btn", disabled: !vtDirty() && !!VT.data.installed.length, onClick: vtApply }, icon("apply"), "Write to the stick"),
    h("select", { id: "vt-res", style: { width: "auto" }, "aria-label": "Screen resolution of the theme" }, ...VT.data.resolutions.map((r) => h("option", { value: r, ...(r === (VT.data.installed[0] || "1920x1080") ? { selected: "" } : {}) }, r))),
    hint("The resolution Ventoy starts in. Pick your screen's, or the nearest."),
    vtDirty() ? h("span", { class: "chip dirty" }, "unsaved changes") : null));
}
const vtTouch = () => {};
const vtRule = (f) => VT.draft.overrides.entries.find((r) => r.match.title === f.name) || VT.draft.overrides.entries.find((r) => r.match.key === f.key) || null;
function vtEditor(f) {
  const r = vtRule(f) || {};
  const patch = (p) => { const list = VT.draft.overrides.entries; let x = list.find((y) => y.match.title === f.name); if (!x) { x = { match: { title: f.name } }; list.push(x); } for (const [k, val] of Object.entries(p)) { if (val === undefined || val === "") delete x[k]; else x[k] = val; } if (Object.keys(x).length === 1) list.splice(list.indexOf(x), 1); render(); };
  const src = { icons: () => VT.data.icons, url: (n) => "/api/ventoy/icon?path=" + encodeURIComponent(VT.path) + "&name=" + encodeURIComponent(n), upload: async (name, file) => { const res = await api.ventoyIcon(VT.path, name, file); VT.data.icons = [...new Set([...VT.data.icons, res.name])].sort(); return res; } };
  return h("section", { class: "card high" },
    h("div", { class: "card-head" }, h("h2", {}, "Customise: " + f.name), r.match ? h("button", { class: "btn text small", onClick: () => patch({ name: undefined, color: undefined, icon: undefined }) }, icon("reset"), "Reset") : null),
    h("div", { class: "field" }, h("label", {}, "Name", hint("Drawn in big letters on this image's screen. It is also written as a Ventoy alias for the list, but Ventoy 1.1.18 did not show it there when tested, so the list keeps the file name. Leave empty to keep the default.")), h("input", { type: "text", value: r.name || "", placeholder: f.name, maxlength: 60, onChange: (ev) => patch({ name: ev.target.value.trim() }) })),
    h("hr"),
    h("div", { class: "field" }, h("label", {}, "Colour", hint("The screen shown for this image is made in this colour.")), swatchGrid(r.color, (c) => patch({ color: c }), [h("button", { class: "swatch", type: "button", style: { background: "repeating-conic-gradient(var(--c-surface-container-highest) 0 25%, var(--c-surface) 0 50%) 0 0/14px 14px" }, title: "Automatic", "aria-pressed": String(!r.color), onClick: () => patch({ color: undefined }) })]), hexField(r.color || "", (c) => patch({ color: c }))),
    h("hr"),
    iconPicker(f, r, patch, src),
    h("p", { class: "muted small" }, "The rule applies to files whose name contains \"" + f.name + "\". Ventoy matches by a piece of the name, so the theme picks the shortest piece that no other file has."),
  );
}
function vtApply() {
  const res = document.getElementById("vt-res")?.value || "1920x1080";
  runJob("Writing the theme to the stick", () => api.ventoyApply(VT.path, VT.draft, res), async () => { await vtLoad(VT.path); });
}

// ---------------------------------------------------------------- Presets
function vPresets(v) {
  const name = h("input", { type: "text", placeholder: "My look", maxlength: 40, "aria-label": "Preset name" });
  const file = h("input", { type: "file", accept: "application/json,.json", class: "sr" });
  file.addEventListener("change", async () => {
    try {
      const data = JSON.parse(await file.files[0].text());
      const r = await api.importPreset(data);
      S.draft = clone(r.draft);
      toast(`Loaded "${r.name}" into the editor. Press Apply to use it.`);
      render();
    } catch (e) { toast("Could not import: " + e.message); }
  });
  v.append(
    card("Save the current look", h("div", { class: "row" }, h("div", { style: { flex: "1", minWidth: "200px" } }, name), h("button", { class: "btn", onClick: async () => { try { await api.savePreset(name.value, S.draft); await load(true); toast("Preset saved"); render(); } catch (e) { toast(e.message); } } }, icon("save"), "Save preset"), h("button", { class: "btn tonal", onClick: () => file.click() }, icon("upload"), "Import file..."), file),
      h("p", { class: "muted small", style: { marginTop: "10px" } }, "A preset holds the style, the options, every colour, name, icon and the order. It does not include the dark or light scheme or the resolution: those are chosen when the theme is built.")),
    card("Your presets", S.srv.presets.length ? h("div", { class: "grid cols2" }, ...S.srv.presets.map((p) => h("div", { class: "card high" }, h("h3", {}, p.name), h("p", { class: "muted small" }, `style ${p.style || "?"} · ${p.entries} customised`), h("div", { class: "row" },
      h("button", { class: "btn small", onClick: async () => { try { const r = await api.loadPreset(p.name); S.draft = clone(r.draft); await load(true); toast(`Loaded "${p.name}". Press Apply to use it.`); go("style"); } catch (e) { toast(e.message); } } }, "Load"),
      h("button", { class: "btn small tonal", "aria-label": "Export " + p.name, onClick: async () => { const d = await api.exportPreset(p.name); const a = h("a", { href: URL.createObjectURL(new Blob([JSON.stringify(d, null, 1)], { type: "application/json" })), download: p.name + ".json" }); a.click(); } }, icon("download")),
      h("button", { class: "btn small danger", "aria-label": "Delete " + p.name, onClick: async () => { await api.deletePreset(p.name); await load(true); render(); } }, icon("trash")),
    )))) : h("div", { class: "empty" }, "No presets yet.")),
  );
}

// ---------------------------------------------------------------- Update
function vUpdate(v) {
  const u = S.update;
  v.append(
    card("Material GRUB " + (S.srv.version ? "v" + S.srv.version : ""),
      h("p", { class: "muted" }, `Installed ${S.srv.install_kind === "package" ? "from a package (updates come through your package manager)" : "from source (updates re-run the installer)"}.`),
      h("div", { class: "row" },
        h("button", { class: "btn tonal", onClick: async () => { S.update = null; render(); try { S.update = await api.checkUpdate(); } catch (e) { S.update = { error: e.message }; } render(); } }, icon("update"), "Check for updates"),
        hint("Contacts GitHub once, only when you click. Nothing is sent about you or your machine."),
      ),
      u ? (u.error ? h("p", { class: "muted", style: { marginTop: "12px" } }, u.error) : h("div", { style: { marginTop: "14px" } },
        h("div", { class: "row" }, h("span", { class: "chip " + (u.newer ? "warn" : "ok") }, u.newer ? `v${u.latest} is available` : "you are up to date"), u.url ? h("a", { href: u.url, target: "_blank", rel: "noopener noreferrer" }, "release notes") : null),
        u.newer ? h("div", { style: { marginTop: "12px" } }, S.srv.install_kind === "package" ? h("button", { class: "btn", onClick: runUpdate }, icon("update"), "Update now") : h("p", { class: "muted" }, "In your clone of the repository run ", h("span", { class: "kbd mono" }, "git pull && sudo ./install.sh"))) : null,
      )) : null,
    ),
  );
}
function runUpdate() { runJob("Updating Material GRUB", () => api.runUpdate(), async () => { await load(); render(); }); }

// ---------------------------------------------------------------- Logs
function vLogs(v) {
  v.append(card("Last change", S.log.length ? h("div", { class: "logbox" }, ...S.log.map(logLine)) : h("div", { class: "empty" }, "Nothing has been applied in this session yet. The installer's own log is /var/log/material-grub/install.log.")));
}
function logLine(ev) {
  const t = ev.text || ev.msg || "";
  const cls = { warn: "l-warn", error: "l-error", ok: "l-ok", step: "l-step" }[ev.event] || (ev.level === "warn" ? "l-warn" : "");
  return h("div", { class: cls }, ev.event === "step" ? `[${ev.n}/${ev.total}] ${t}` : ev.event === "ok" ? "ok  " + t : ev.event === "error" ? "ERROR " + t : t);
}

// ---------------------------------------------------------------- Apply and the progress dialog
async function applyDraft() {
  if (!dirty()) return;
  runJob("Applying your changes", () => api.apply(S.draft, S.plymouthCmdline), async () => { S.base = JSON.stringify(S.draft); await load(true); render(); });
}
function runJob(title, start, after) {
  const dlg = document.getElementById("job");
  S.log = [];
  const wp = new WavyProgress(560);
  wp.set(null);
  const stepEl = h("div", { class: "steps" }, "Starting...");
  const logEl = h("div", { class: "logbox", hidden: true, "aria-live": "off" });
  const closeBtn = h("button", { class: "btn", disabled: true, onClick: () => dlg.close() }, "Close");
  const verbose = h("input", { type: "checkbox", onChange: (e) => { logEl.hidden = !e.target.checked; } });
  const sheet = h("div", { class: "sheet" },
    h("h2", { id: "job-title" }, title),
    h("p", { class: "muted small" }, "Your password or fingerprint may be asked by the system. Do not close this window."),
    wp.svg, stepEl,
    h("div", { class: "row between", style: { marginTop: "14px" } }, h("label", { class: "switch" }, verbose, h("span", { class: "track" }), h("span", {}, "Verbose log")), closeBtn),
    logEl,
  );
  dlg.replaceChildren(sheet);
  dlg.addEventListener("cancel", (e) => { if (closeBtn.disabled) e.preventDefault(); }, { once: false });
  dlg.showModal();
  let lastOk = "";
  const onEvent = (ev) => {
    S.log.push(ev);
    logEl.append(logLine(ev));
    logEl.scrollTop = logEl.scrollHeight;
    if (ev.event === "step") { stepEl.textContent = `Step ${ev.n} of ${ev.total}: ${ev.msg}`; wp.set(Math.max(0.04, (ev.n - 1) / ev.total)); }
    else if (ev.event === "progress" && ev.percent != null) wp.set(ev.percent / 100);
    else if (ev.event === "ok") { stepEl.textContent = ev.msg; lastOk = ev.msg; }
    else if (ev.event === "error") { stepEl.textContent = ev.msg; stepEl.style.color = "var(--c-error)"; }
    else if (ev.event === "done") {
      wp.set(ev.ok ? 1 : null);
      if (!ev.ok) { wp.stop(); wp.svg.style.opacity = ".35"; verbose.checked = true; logEl.hidden = false; }
      else stepEl.textContent = lastOk || "All done.";
      closeBtn.disabled = false;
      closeBtn.focus();
      if (ev.ok) after?.();
    }
  };
  start().then((r) => api.events(r.job, onEvent)).catch((e) => { onEvent({ event: "error", msg: e.message }); onEvent({ event: "done", ok: false, rc: 1 }); });
  dlg.addEventListener("close", () => wp.stop(), { once: true });
}

// ---------------------------------------------------------------- Live preview
function previewPane() {
  const e = S.srv.entries.find((x) => x.class === S.sel) || S.srv.entries[0];
  const frame = h("div", { class: "frame loading", id: "frame" }, h("img", { id: "pv-a", alt: "Preview of the boot menu", style: { opacity: 0 } }), h("img", { id: "pv-b", alt: "", style: { opacity: 0 } }));
  const tops = topRows();
  return h("aside", { class: "preview card" },
    h("div", { class: "card-head" }, h("h2", {}, "Live preview"), hint("Drawn by the same code that writes your real menu, so what you see here is what you will get. Nothing is saved until you press Apply.")),
    frame,
    h("div", { class: "tools" },
      seg([["rail", "Rail"], ["clean", "Clean"], ["list", "List"], ["split", "Split"]], S.draft.conf.STYLE, (x) => { S.draft.conf.STYLE = x; render(); }),
      seg([["dark", "Dark"], ["light", "Light"]], S.dark ? "dark" : "light", (x) => { S.dark = x === "dark"; render(); }),
    ),
    h("div", { class: "tools" }, ...tops.slice(0, 12).map((t) => h("button", { class: "chip", style: S.sel === t.class ? { background: "var(--c-primary)", color: "var(--c-on-primary)" } : {}, onClick: () => { S.sel = t.class; render(); } }, entryLabel(t)))),
  );
}
let pvTimer = null;
function schedulePreview() {
  clearTimeout(pvTimer);
  pvTimer = setTimeout(drawPreview, 160);
}
let pvFront = "pv-a";
async function drawPreview() {
  const frame = document.getElementById("frame");
  if (!frame || !S.sel) return;
  const n = ++S.pv.n;
  frame.classList.add("loading");
  try {
    const url = await api.preview({ draft: S.draft, class: S.sel, dark: S.dark, scale: 0.6, aspect: "16x9" });
    if (n !== S.pv.n) { URL.revokeObjectURL(url); return; }
    const back = document.getElementById(pvFront === "pv-a" ? "pv-b" : "pv-a"), front = document.getElementById(pvFront);
    if (!back) return;
    back.onload = () => { back.style.opacity = 1; if (front) front.style.opacity = 0; pvFront = back.id; frame.classList.remove("loading"); };
    back.src = url;
  } catch (e) {
    if (n === S.pv.n) { frame.classList.remove("loading"); toast("Preview failed: " + e.message); }
  }
}


// ---------------------------------------------------------------- Boot splash (the optional Plymouth part)
const PLY_SCREENS = [["boot", "While it boots"], ["password", "Disk password"], ["shutdown", "Shutting down"]];
function vPlymouth(v) {
  const c = S.draft.conf, ply = S.srv.plymouth;
  const set = (k, val) => { c[k] = val; touch(); };
  const on = c.PLYMOUTH === "on";
  v.append(
    card("Boot splash",
      h("p", { class: "muted" }, `Plymouth ${ply.version} draws this same look while the system starts, when it asks for the disk password and while it shuts down. The style, the colours and the entries are the ones of the other pages.`),
      toggle("Show the Material boot splash", on, (x) => { set("PLYMOUTH", x ? "on" : "off"); render(); }, "Off takes the splash out the next time you press Apply (your distro's own splash comes back)."),
      on ? h("div", { class: "grid cols2", style: { marginTop: "14px" } },
        field("Loading bar", "The wavy bar under the title. Endless: a wave that keeps travelling. Fills as it boots: grows with the real boot progress.",
          seg([["indeterminate", "Endless wave"], ["progress", "Fills as it boots"]], c.PLYMOUTH_BAR, (x) => { set("PLYMOUTH_BAR", x); render(); })),
        field("Motion", "How much moves. Full: the shapes, the cookie and the card. Calm: fewer things, less work for the CPU. Still: nothing but the bar.",
          seg([["full", "Full"], ["calm", "Calm"], ["off", "Still"]], c.PLYMOUTH_MOTION, (x) => { set("PLYMOUTH_MOTION", x); render(); })),
      ) : null,
    ),
    card("Preview", h("p", { class: "muted" }, "Drawn by the boot splash's own code from the settings on screen, so it follows every change before you apply. The real splash is animated."),
      h("div", { class: "grid cols3", style: { marginTop: "12px" } }, ...PLY_SCREENS.map(([id, label]) =>
        h("figure", { class: "ply-shot" }, h("div", { class: "frame loading" }, h("img", { id: "ply-" + id, alt: `Preview: ${label}` })), h("figcaption", { class: "small muted" }, label))))),
    card("Changes to the boot configuration",
      h("p", { class: "muted" }, "For the splash to show, the kernel command line needs the words quiet and splash (and on Arch, mkinitcpio needs the plymouth hook). Each change is backed up first and undone if anything goes wrong."),
      toggle("Let Apply make these changes", S.plymouthCmdline, (x) => { S.plymouthCmdline = x; render(); }, "Not ticked: the theme is installed, but it only shows if splash is already on your command line. This is asked again every time you open the page."),
    ),
    card("Only the boot splash",
      h("p", { class: "muted" }, dirty() ? "You have unsaved changes: Apply (the button at the bottom) writes them for both GRUB and the boot splash. These two buttons act on what is already saved." : "These act on the saved settings only, without touching the GRUB menu."),
      h("div", { class: "row" },
        h("button", { class: "btn", disabled: dirty() || !on, onClick: () => runJob("Applying the boot splash", () => api.plymouthRun("apply", S.plymouthCmdline), async () => { await load(true); render(); }) }, icon("check"), "Apply the boot splash now"),
        h("button", { class: "btn text", onClick: () => { if (confirm("Take the Material boot splash out and rebuild the initramfs?")) runJob("Removing the boot splash", () => api.plymouthRun("remove", false), async () => { await load(true); render(); }); } }, "Remove it"),
      ),
    ),
  );
}
let plyTimer = null;
const plyN = {};
function schedulePly() {
  clearTimeout(plyTimer);
  plyTimer = setTimeout(drawPly, 220);
}
async function drawPly() {
  for (const [id] of PLY_SCREENS) {
    const img = document.getElementById("ply-" + id);
    if (!img) continue;
    const n = (plyN[id] = (plyN[id] || 0) + 1);
    img.parentNode.classList.add("loading");
    try {
      const url = await api.plymouthPreview({ draft: S.draft, screen: id, size: "1280x720" });
      if (n !== plyN[id] || !document.body.contains(img)) { URL.revokeObjectURL(url); continue; }
      img.onload = () => img.parentNode.classList.remove("loading");
      img.src = url;
    } catch (e) {
      if (n === plyN[id]) { img.parentNode.classList.remove("loading"); toast("Preview failed: " + e.message); }
    }
  }
}

// ---------------------------------------------------------------- go
setInterval(() => api.ping().catch(() => {}), 8000);
addEventListener("beforeunload", (e) => { if (dirty()) { e.preventDefault(); e.returnValue = ""; } });
load().then(() => { go(location.hash.slice(1) || "overview"); refreshStatus(); }).catch((e) => { document.body.prepend(h("p", { style: { padding: "2rem" } }, "Could not talk to the Material GRUB GUI program: " + e.message)); });
