// The page's only network peer is the local Material GRUB GUI server. Every call carries the token from the page's meta tag.
const TOKEN = document.querySelector('meta[name="mg-token"]').content;

async function call(method, path, body, raw) {
  const opt = { method, headers: { "X-MG-Token": TOKEN } };
  if (body !== undefined) {
    if (body instanceof Blob || body instanceof ArrayBuffer) { opt.body = body; opt.headers["Content-Type"] = "application/octet-stream"; }
    else { opt.body = JSON.stringify(body); opt.headers["Content-Type"] = "application/json"; }
  }
  const r = await fetch(path, opt);
  if (!r.ok) {
    let msg = r.statusText;
    try { msg = (await r.json()).error || msg; } catch {}
    throw new Error(msg);
  }
  return raw ? r : r.json();
}

export const api = {
  state: () => call("GET", "/api/state"),
  status: () => call("GET", "/api/status"),
  ping: () => call("GET", "/api/ping"),
  palette: (seed) => call("GET", "/api/palette?seed=" + encodeURIComponent(seed)),
  preview: async (body) => URL.createObjectURL(await (await call("POST", "/api/preview", body, true)).blob()),
  uploadIcon: (name, blob) => call("POST", "/api/icon?name=" + encodeURIComponent(name), blob),
  ventoySticks: () => call("GET", "/api/ventoy/sticks"),
  ventoyState: (path) => call("GET", "/api/ventoy/state?path=" + encodeURIComponent(path)),
  ventoyIcon: (path, name, blob) => call("POST", "/api/ventoy/icon?path=" + encodeURIComponent(path) + "&name=" + encodeURIComponent(name), blob),
  ventoyApply: (path, draft, res) => call("POST", "/api/ventoy/apply", { path, draft, res }),
  apply: (draft, plymouth_cmdline) => call("POST", "/api/apply", { draft, plymouth_cmdline: plymouth_cmdline === true }),
  plymouthPreview: async (body) => URL.createObjectURL(await (await call("POST", "/api/plymouth/preview", body, true)).blob()),
  plymouthRun: (action, cmdline) => call("POST", "/api/plymouth/run", { action, cmdline: cmdline === true }),
  checkUpdate: () => call("POST", "/api/update/check", {}),
  runUpdate: () => call("POST", "/api/update/run", {}),
  savePreset: (name, draft) => call("POST", "/api/presets/save", { name, draft }),
  loadPreset: (name) => call("POST", "/api/presets/load/" + encodeURIComponent(name), {}),
  deletePreset: (name) => call("DELETE", "/api/presets/" + encodeURIComponent(name)),
  exportPreset: (name) => call("GET", "/api/presets/export/" + encodeURIComponent(name)),
  importPreset: (data) => call("POST", "/api/presets/import", data),
  events: (job, onEvent) => {
    return new Promise((resolve) => {
      // EventSource cannot send our token header, so stream with fetch
      fetch(`/api/jobs/${job}/events`, { headers: { "X-MG-Token": TOKEN } }).then(async (r) => {
        const rd = r.body.getReader(), dec = new TextDecoder();
        let buf = "";
        for (;;) {
          const { value, done } = await rd.read();
          if (done) break;
          buf += dec.decode(value, { stream: true });
          let i;
          while ((i = buf.indexOf("\n\n")) >= 0) {
            const chunk = buf.slice(0, i); buf = buf.slice(i + 2);
            if (chunk.startsWith("data: ")) onEvent(JSON.parse(chunk.slice(6)));
          }
        }
        resolve();
      }).catch(() => resolve());
    });
  },
};
