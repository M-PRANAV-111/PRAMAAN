// Development server: rebuilds on change, serves dist/, proxies /api to the backend (default :8000).
import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";
import { buildAll } from "./build.mjs";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const backendDir = path.resolve(root, "../backend");
const dist = path.join(root, "dist");
const api = new URL(process.env.API_URL || "http://127.0.0.1:8000");
const port = Number(process.env.PORT || 5173);
const types = { ".js": "text/javascript", ".css": "text/css", ".html": "text/html", ".png": "image/png",
  ".svg": "image/svg+xml", ".woff": "font/woff", ".map": "application/json" };

function ensureBackend() {
  const req = http.get({ host: api.hostname, port: api.port, path: "/api/v1/health", timeout: 1000 }, (res) => res.resume());
  req.on("error", () => {
    console.log(`Starting backend on ${api.origin} ...`);
    const py = process.platform === "win32" ? "python" : "python3";
    spawn(py, ["-m", "uvicorn", "app.main:app", "--host", api.hostname, "--port", String(api.port || 8000)], {
      cwd: backendDir,
      env: { ...process.env, FRONT_DIST: dist },
      stdio: "inherit",
    });
  });
}

let building = buildAll({ minify: false }).then((info) => { ensureBackend(); return info; });
let timer;
fs.watch(path.join(root, "src"), { recursive: true }, () => {
  clearTimeout(timer);
  timer = setTimeout(() => { building = buildAll({ minify: false }).then((i) => (console.log("rebuilt", i.jsName), i)); }, 120);
});

http.createServer(async (req, res) => {
  if (req.url.startsWith("/api/")) {
    const p = http.request({ host: api.hostname, port: api.port, path: req.url, method: req.method, headers: req.headers },
      (r) => { res.writeHead(r.statusCode, r.headers); r.pipe(res); });
    p.on("error", () => { res.writeHead(502); res.end("backend unavailable"); });
    return req.pipe(p);
  }
  await building;
  const file = path.join(dist, decodeURIComponent(new URL(req.url, "http://x").pathname));
  const target = file.startsWith(dist) && fs.existsSync(file) && fs.statSync(file).isFile() ? file : path.join(dist, "index.html");
  res.writeHead(200, { "content-type": types[path.extname(target)] || "application/octet-stream" });
  fs.createReadStream(target).pipe(res);
}).listen(port, () => console.log(`PRAMAAN dev server http://localhost:${port} → API ${api.origin}`));
