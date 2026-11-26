// Small UI toolkit: hyperscript, icons, toasts, hints, ripple, the wavy progress bar, FLIP reordering. No dependencies.

export function h(tag, props, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(props || {})) {
    if (v === false || v == null) continue;
    if (k === "class") el.className = v;
    else if (k === "style" && typeof v === "object") for (const [sk, sv] of Object.entries(v)) sk.startsWith("--") ? el.style.setProperty(sk, sv) : (el.style[sk] = sv);
    else if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2).toLowerCase(), v);
    else if (k === "html") el.innerHTML = v;
    else if (v === true) el.setAttribute(k, "");
    else el.setAttribute(k, v);
  }
  for (const kid of kids.flat(Infinity)) {
    if (kid == null || kid === false) continue;
    el.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  }
  return el;
}

const ICONS = {
  overview: "M4 11l8-7 8 7v9h-5v-6H9v6H4z",
  style: "M3 3h8v8H3zm10 0h8v8h-8zM3 13h8v8H3zm10 0h8v8h-8z",
  entries: "M4 6h16v2H4zm0 5h16v2H4zm0 5h16v2H4z",
  colours: "M12 3a9 9 0 100 18c1.1 0 1.6-.8 1.3-1.7-.4-1 .3-2.3 1.7-2.3H17a4 4 0 004-4c0-5-4-10-9-10zM7.5 12a1.3 1.3 0 110-2.6 1.3 1.3 0 010 2.6zm3-3.5a1.3 1.3 0 110-2.6 1.3 1.3 0 010 2.6zm4 0a1.3 1.3 0 110-2.6 1.3 1.3 0 010 2.6z",
  plymouth: "M3 4h18v12H3zm2 2v8h14V6zm4 12h6v2H9z",
  ventoy: "M7 3h10v7H7zm-2 9h14v9H5zm4 2v2h2v-2zm4 0v2h2v-2z",
  presets: "M6 3h12v18l-6-4-6 4z",
  update: "M12 5V1L7 6l5 5V7a5 5 0 11-5 5H5a7 7 0 107-7z",
  logs: "M3 4h18v16H3zm2 2v12h14V6zm2 2.5l4 3.5-4 3.5V14l1.8-2L7 10zM12 15h5v1.5h-5z",
  check: "M9 16.2l-3.5-3.5L4 14.2l5 5 11-11-1.5-1.5z",
  close: "M18.3 5.7L12 12l6.3 6.3-1.4 1.4L10.6 13.4 4.3 19.7 2.9 18.3 9.2 12 2.9 5.7 4.3 4.3l6.3 6.3 6.3-6.3z",
  grip: "M9 5a1.5 1.5 0 110 3 1.5 1.5 0 010-3zm6 0a1.5 1.5 0 110 3 1.5 1.5 0 010-3zM9 10.5a1.5 1.5 0 110 3 1.5 1.5 0 010-3zm6 0a1.5 1.5 0 110 3 1.5 1.5 0 010-3zM9 16a1.5 1.5 0 110 3 1.5 1.5 0 010-3zm6 0a1.5 1.5 0 110 3 1.5 1.5 0 010-3z",
  up: "M7.4 14.6L12 10l4.6 4.6L18 13.2l-6-6-6 6z",
  down: "M7.4 9.4L12 14l4.6-4.6L18 10.8l-6 6-6-6z",
  eyeoff: "M3 5.3l1.3-1.3 16.4 16.4-1.3 1.3-3-3A10 10 0 0112 20C6.5 20 2.7 16 1 12c.8-1.8 2.2-3.7 4-5.2zM12 6c5.5 0 9.3 4 11 8-.5 1.1-1.2 2.2-2.2 3.2l-3.1-3.1a4.5 4.5 0 00-5.8-5.8L8.3 6.4C9.5 6.1 10.7 6 12 6z",
  upload: "M5 18h14v2H5zM11 4.8L7.4 8.4 6 7l6-6 6 6-1.4 1.4L13 4.8V16h-2z",
  trash: "M6 7h12l-1 14H7zM9 3h6l1 2h4v2H4V5h4z",
  save: "M5 3h11l4 4v14H5zm3 0v5h7V3zm4 8a3 3 0 100 6 3 3 0 000-6z",
  download: "M5 18h14v2H5zM13 12.2l3.6-3.6L18 10l-6 6-6-6 1.4-1.4 3.6 3.6V2h2z",
  reset: "M12 5a7 7 0 11-6.7 9H3.2a9 9 0 104.2-9.2L5 3v6h6L8.6 6.6A7 7 0 0112 5z",
  sun: "M12 7a5 5 0 100 10 5 5 0 000-10zM11 1h2v3h-2zm0 19h2v3h-2zM1 11h3v2H1zm19 0h3v2h-3zM4.2 5.6l1.4-1.4 2.1 2.1-1.4 1.4zm12.1 12.1l1.4-1.4 2.1 2.1-1.4 1.4zM5.6 19.8l-1.4-1.4 2.1-2.1 1.4 1.4zM17.7 7.7l-1.4-1.4 2.1-2.1 1.4 1.4z",
  moon: "M12 3a9 9 0 109 9 7 7 0 01-9-9z",
  apply: "M5 13l4 4L19 7l-1.4-1.4L9 14.2 6.4 11.6z",
  cookie: "M12 1.5l2.6 2 3.3-.3 1.2 3.1 3 1.4-.7 3.2 1.7 2.8-2.3 2.4.1 3.3-3.2.9-1.8 2.8L12 21l-2.9 1.1-1.8-2.8-3.2-.9.1-3.3L1.9 12.7l1.7-2.8-.7-3.2 3-1.4 1.2-3.1 3.3.3z",
};

export function icon(name, cls) {
  const s = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  s.setAttribute("viewBox", "0 0 24 24");
  s.setAttribute("aria-hidden", "true");
  if (cls) s.setAttribute("class", cls);
  const p = document.createElementNS("http://www.w3.org/2000/svg", "path");
  p.setAttribute("d", ICONS[name] || ICONS.cookie);
  p.setAttribute("fill", "currentColor");
  p.setAttribute("fill-rule", "evenodd");
  s.append(p);
  return s;
}

export function toast(msg, ms = 4200) {
  const box = document.getElementById("toasts");
  const t = h("div", { class: "toast", role: "status" }, msg);
  box.append(t);
  setTimeout(() => {
    t.style.transition = "opacity .3s, transform .3s";
    t.style.opacity = "0";
    t.style.transform = "translateY(10px)";
    setTimeout(() => t.remove(), 320);
  }, ms);
}

// a "?" button whose text shows in a popover on hover, focus or tap
export function hint(text) {
  let pop = null;
  const hide = () => { pop?.remove(); pop = null; };
  const show = (b) => {
    hide();
    pop = h("div", { class: "popover", role: "tooltip" }, text);
    document.body.append(pop);
    const r = b.getBoundingClientRect();
    const w = pop.offsetWidth, hh = pop.offsetHeight;
    pop.style.left = Math.max(8, Math.min(innerWidth - w - 8, r.left + r.width / 2 - w / 2)) + "px";
    pop.style.top = (r.bottom + hh + 14 > innerHeight ? r.top - hh - 10 : r.bottom + 10) + "px";
  };
  const b = h("button", { class: "hint-btn", type: "button", "aria-label": "Help: " + text }, "?");
  b.addEventListener("mouseenter", () => show(b));
  b.addEventListener("focus", () => show(b));
  b.addEventListener("mouseleave", hide);
  b.addEventListener("blur", hide);
  b.addEventListener("click", (e) => { e.preventDefault(); pop ? hide() : show(b); });
  return b;
}

// Material ripple on every .btn
document.addEventListener("pointerdown", (e) => {
  const b = e.target.closest?.(".btn, .nav");
  if (!b || b.disabled) return;
  const r = b.getBoundingClientRect();
  const d = Math.max(r.width, r.height) * 2;
  const s = h("span", { class: "ripple", style: { width: d + "px", height: d + "px", left: e.clientX - r.left - d / 2 + "px", top: e.clientY - r.top - d / 2 + "px" } });
  b.style.overflow = "hidden";
  b.append(s);
  setTimeout(() => s.remove(), 650);
});

// FLIP: animate list items from their old to their new place after `mutate()` re-rendered the container
export function flip(container, mutate) {
  const before = new Map([...container.children].map((c) => [c.dataset.k, c.getBoundingClientRect()]));
  mutate();
  if (matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  for (const c of container.children) {
    const a = before.get(c.dataset.k);
    if (!a) continue;
    const b = c.getBoundingClientRect();
    const dy = a.top - b.top;
    if (!dy) continue;
    c.animate([{ transform: `translateY(${dy}px)` }, { transform: "none" }], { duration: 520, easing: "cubic-bezier(.2,0,0,1)" });
  }
}

// Material 3 Expressive wavy progress indicator: a travelling sine wave for the finished part, a straight track for the rest.
// value 0..1 (determinate) or null (indeterminate: a wave of fixed length sweeps along).
export class WavyProgress {
  constructor(width = 560) {
    this.W = width;
    this.value = null;
    this.shown = 0;
    this.phase = 0;
    this.ns = "http://www.w3.org/2000/svg";
    this.svg = document.createElementNS(this.ns, "svg");
    this.svg.setAttribute("class", "wavy");
    this.svg.setAttribute("viewBox", `0 -14 ${this.W} 28`);
    this.svg.setAttribute("preserveAspectRatio", "none");
    this.svg.setAttribute("role", "progressbar");
    this.track = this.mk("var(--c-secondary-container)", 6);
    this.wave = this.mk("var(--c-primary)", 6);
    this.dot = document.createElementNS(this.ns, "circle");
    this.dot.setAttribute("r", "3");
    this.dot.setAttribute("fill", "var(--c-primary)");
    this.svg.append(this.track, this.wave, this.dot);
    this.raf = null;
    this.t0 = performance.now();
    this.tick = this.tick.bind(this);
    this.raf = requestAnimationFrame(this.tick);
  }
  mk(color, w) {
    const p = document.createElementNS(this.ns, "path");
    p.setAttribute("fill", "none");
    p.setAttribute("stroke", color);
    p.setAttribute("stroke-width", w);
    p.setAttribute("stroke-linecap", "round");
    p.setAttribute("stroke-linejoin", "round");
    this.svg.append(p);
    return p;
  }
  set(v) {
    this.value = v;
    this.svg.setAttribute("aria-valuenow", v == null ? "" : Math.round(v * 100));
  }
  stop() { cancelAnimationFrame(this.raf); }
  tick(now) {
    const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
    const t = (now - this.t0) / 1000;
    this.phase = reduce ? 0 : t * 5.2;
    let a, b;
    if (this.value == null) { // indeterminate: a 38% long wave segment travelling left to right and back around
      const len = this.W * 0.38, pos = ((t * 0.55) % 1) * (this.W + len) - len;
      a = Math.max(0, pos); b = Math.min(this.W, pos + len);
    } else {
      this.shown += (this.value - this.shown) * 0.12; // ease toward the target
      a = 0; b = this.W * this.shown;
    }
    const amp = this.value != null && (this.shown < 0.02 || this.shown > 0.985) ? 0 : 7; // flat at both ends, as in the M3 spec
    const k = (2 * Math.PI) / 44;
    let d = "";
    for (let x = a; x <= b; x += 3) d += (d ? "L" : "M") + x.toFixed(1) + " " + (Math.sin(x * k - this.phase) * amp).toFixed(2);
    if (b > a) d += "L" + b.toFixed(1) + " " + (Math.sin(b * k - this.phase) * amp).toFixed(2);
    this.wave.setAttribute("d", d || "M0 0");
    this.track.setAttribute("d", `M${Math.min(this.W, b + 14)} 0H${this.W}`);
    this.dot.setAttribute("cx", this.W - 3);
    this.dot.setAttribute("cy", 0);
    this.dot.style.opacity = this.value != null && this.shown > 0.985 ? 0 : 1;
    this.raf = requestAnimationFrame(this.tick);
  }
}
