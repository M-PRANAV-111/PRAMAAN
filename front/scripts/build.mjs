// Production build: esbuild bundles the app, Tailwind v4 compiles only the utilities the source uses.
import { build, transform } from "esbuild";
import { compile } from "tailwindcss";
import fs from "node:fs";
import path from "node:path";
import { createHash } from "node:crypto";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const dist = path.join(root, "dist");
const watch = process.argv.includes("--watch");

function walk(dir) {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((e) =>
    e.isDirectory() ? walk(path.join(dir, e.name)) : [path.join(dir, e.name)]);
}

// Tailwind's own scanner (oxide) is a native add-on; here we pass every class-like token from the source.
// Tailwind ignores tokens that are not utilities, so over-collecting is safe.
function candidates() {
  const set = new Set();
  for (const file of walk(path.join(root, "src")).filter((f) => /\.(tsx?|css)$/.test(f))) {
    // Split on whitespace and string delimiters only: arbitrary values such as
    // grid-cols-[minmax(0,1fr)_2fr] contain parentheses and commas that must stay intact.
    for (const tok of fs.readFileSync(file, "utf8").split(/[\s"'`{}<>;]+/)) {
      if (tok && tok.length < 80 && /^[!-~]+$/.test(tok)) set.add(tok);
    }
  }
  return [...set];
}

async function buildCss() {
  const tailwindDir = path.dirname(fileURLToPath(import.meta.resolve("tailwindcss/package.json")));
  const input = fs.readFileSync(path.join(root, "src/styles.css"), "utf8");
  const compiler = await compile(input, {
    base: path.join(root, "src"),
    loadStylesheet: async (id, base) => {
      const file = id === "tailwindcss" ? path.join(tailwindDir, "index.css")
        : id.startsWith("tailwindcss/") ? path.join(tailwindDir, id.slice("tailwindcss/".length))
        : path.resolve(base, id);
      return { path: file, base: path.dirname(file), content: fs.readFileSync(file, "utf8") };
    },
  });
  return compiler.build(candidates());
}

function hash(text) {
  return createHash("sha256").update(text).digest("hex").slice(0, 10);
}

export async function buildAll({ minify = true } = {}) {
  fs.rmSync(dist, { recursive: true, force: true });
  fs.mkdirSync(path.join(dist, "assets"), { recursive: true });
  fs.cpSync(path.join(root, "public"), path.join(dist, "assets"), { recursive: true });
  const result = await build({
    entryPoints: [path.join(root, "src/main.tsx")],
    bundle: true, minify, sourcemap: !minify, write: false, metafile: true, format: "esm", target: "es2022",
    splitting: true, chunkNames: "chunk-[hash]",
    jsx: "automatic", alias: { "@contract": path.join(root, "../contracts/api.gen.ts") },
    define: { "process.env.NODE_ENV": JSON.stringify(minify ? "production" : "development") },
    outdir: path.join(dist, "assets"), entryNames: "app", logLevel: "warning",
  });
  let jsName = "app.js";
  for (const out of result.outputFiles) {
    const name = path.basename(out.path);
    if (name === "app.js") jsName = `app.${hash(out.text)}.js`;
    fs.writeFileSync(path.join(dist, "assets", name === "app.js" ? jsName : name), out.contents);
  }
  // Find the lazy chunk that contains src/pages/Landing.tsx via esbuild's metafile so index.html modulepreloads it.
  let landingChunk = "";
  let landingBytes = 0;
  let sharedBytes = 0;
  for (const [outPath, meta] of Object.entries(result.metafile?.outputs ?? {})) {
    const base = path.basename(outPath);
    if (base.endsWith(".map") || base === "app.js") continue;
    const inputs = Object.keys(meta.inputs ?? {}).map((p) => p.replace(/\\/g, "/"));
    if (inputs.some((p) => p.endsWith("src/pages/Landing.tsx"))) {
      landingChunk = base;
      landingBytes = meta.bytes;
    } else if (base.endsWith(".js")) {
      sharedBytes += meta.bytes;
    }
  }
  const css = minify ? (await transform(await buildCss(), { loader: "css", minify: true })).code : await buildCss();
  const cssName = `app.${hash(css)}.css`;
  fs.writeFileSync(path.join(dist, "assets", cssName), css);
  const preloadTag = landingChunk ? `\n    <link rel="modulepreload" href="/assets/${landingChunk}" />` : "";
  const html = fs.readFileSync(path.join(root, "index.html"), "utf8")
    .replace("%CSS%", `/assets/${cssName}`)
    .replace("%JS%", `/assets/${jsName}`)
    .replace("</head>", `${preloadTag}\n  </head>`);
  fs.writeFileSync(path.join(dist, "index.html"), html);
  const entryBytes = fs.statSync(path.join(dist, "assets", jsName)).size;
  return { jsName, cssName, landingChunk, jsBytes: entryBytes + sharedBytes, landingBytes, cssBytes: css.length };
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const info = await buildAll({ minify: !watch });
  console.log(
    `built dist/ — signed-in JS ${(info.jsBytes / 1024).toFixed(1)} KB (${info.jsName}), ` +
    `start-page chunk ${(info.landingBytes / 1024).toFixed(1)} KB (${info.landingChunk}), ` +
    `${info.cssName} ${(info.cssBytes / 1024).toFixed(1)} KB`
  );
}
