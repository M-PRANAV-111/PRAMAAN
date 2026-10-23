// Builds the frontend into dist/ and starts the unified backend + frontend server on port 8000.
import http from "node:http";
import path from "node:path";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";
import { buildAll } from "./build.mjs";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const backendDir = path.resolve(root, "../backend");
const distDir = path.join(root, "dist");
const port = Number(process.env.PORT || 8000);

function checkServer(p) {
  return new Promise((resolve) => {
    const req = http.get({ host: "127.0.0.1", port: p, path: "/api/v1/health", timeout: 1000 }, (res) => {
      res.resume();
      resolve(res.statusCode === 200);
    });
    req.on("error", () => resolve(false));
    req.on("timeout", () => { req.destroy(); resolve(false); });
  });
}

await buildAll({ minify: true });

if (await checkServer(port)) {
  console.log(`PRAMAAN server is already running at http://127.0.0.1:${port}/`);
} else {
  console.log(`Starting PRAMAAN server at http://127.0.0.1:${port}/ ...`);
  const py = process.platform === "win32" ? "python" : "python3";
  const child = spawn(py, ["-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", String(port)], {
    cwd: backendDir,
    env: { ...process.env, FRONT_DIST: distDir },
    stdio: "inherit",
  });
  child.on("exit", (code) => process.exit(code ?? 0));
}
