#!/usr/bin/env node
/**
 * rhize-plan — local viewer + static exporter for the Rhize plan.mdx format.
 *
 *   rhize-plan serve <path-to-plan.mdx|dir>
 *       Start a Vite dev server with HMR, print the URL, open the browser, and
 *       live-reload when the plan file is edited.
 *
 *   rhize-plan build <path-to-plan.mdx|dir> [-o out.html]
 *       Produce ONE self-contained .html (all CSS+JS inlined, openable offline).
 *       If -o is omitted, write <plan-slug>.html next to the source file (slug
 *       from the frontmatter title, falling back to the filename). Prints the
 *       absolute output path.
 *
 * A <dir> argument resolves to <dir>/plan.mdx.
 *
 * Implementation: Vite's JS API. The target plan path is passed to Vite via the
 * RHIZE_PLAN_PATH env var; vite.config.ts resolves the virtual MDX entry from it.
 */

import { createServer, build, preview } from "vite";
import {
  existsSync,
  statSync,
  readFileSync,
  writeFileSync,
  readdirSync,
  rmSync,
  copyFileSync,
} from "node:fs";
import { resolve, dirname, join, basename, isAbsolute, extname } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { spawn } from "node:child_process";
import os from "node:os";
import matter from "gray-matter";

const __dirname = dirname(fileURLToPath(import.meta.url));
const VIEWER_ROOT = resolve(__dirname, "..");

// --------------------------------------------------------------------------
// arg parsing
// --------------------------------------------------------------------------
function parseArgs(argv) {
  const [command, ...rest] = argv;
  const opts = { _: [], out: undefined, open: true, port: undefined };
  for (let i = 0; i < rest.length; i++) {
    const a = rest[i];
    if (a === "-o" || a === "--out" || a === "--output") {
      opts.out = rest[++i];
    } else if (a === "--no-open") {
      opts.open = false;
    } else if (a === "--port") {
      opts.port = Number(rest[++i]);
    } else if (a === "-h" || a === "--help") {
      opts.help = true;
    } else if (a.startsWith("-")) {
      console.warn(`rhize-plan: ignoring unknown flag ${a}`);
    } else {
      opts._.push(a);
    }
  }
  return { command, opts };
}

function usage() {
  console.log(`rhize-plan — local viewer + static exporter for plan.mdx

Usage:
  rhize-plan serve <path-to-plan.mdx|dir> [--port N] [--no-open]
  rhize-plan build <path-to-plan.mdx|dir> [-o out.html]

A <dir> argument resolves to <dir>/plan.mdx.`);
}

// Resolve a user-supplied path (file or dir) to an absolute plan.mdx path.
function resolvePlanPath(input) {
  if (!input) {
    throw new Error(
      "No plan path given. Usage: rhize-plan <serve|build> <path-to-plan.mdx|dir>"
    );
  }
  let p = isAbsolute(input) ? input : resolve(process.cwd(), input);

  if (existsSync(p) && statSync(p).isDirectory()) {
    p = join(p, "plan.mdx");
  } else if (!existsSync(p) && extname(p) === "") {
    // Treat a non-existent extension-less path as a dir reference.
    p = join(p, "plan.mdx");
  }

  if (!existsSync(p)) {
    throw new Error(`Plan file not found: ${p}`);
  }
  if (!/\.mdx?$/.test(p)) {
    throw new Error(`Expected a .mdx (or .md) plan file, got: ${p}`);
  }
  return p;
}

// Derive a filesystem-safe slug from the frontmatter title or the source filename.
function deriveSlug(planPath) {
  let title;
  try {
    title = matter(readFileSync(planPath, "utf8")).data?.title;
  } catch {
    /* ignore */
  }
  const base =
    (typeof title === "string" && title.trim()) ||
    basename(planPath).replace(/\.mdx?$/, "");
  const slug = String(base)
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 80);
  return slug || "plan";
}

function openBrowser(url) {
  const platform = process.platform;
  const cmd =
    platform === "darwin" ? "open" : platform === "win32" ? "start" : "xdg-open";
  try {
    const child = spawn(cmd, [url], {
      stdio: "ignore",
      detached: true,
      shell: platform === "win32",
    });
    child.on("error", () => {});
    child.unref();
  } catch {
    /* opening the browser is best-effort */
  }
}

// --------------------------------------------------------------------------
// serve
// --------------------------------------------------------------------------
async function runServe(planPath, opts) {
  process.env.RHIZE_PLAN_PATH = planPath;
  process.env.RHIZE_PLAN_MODE = "serve";

  const server = await createServer({
    root: VIEWER_ROOT,
    configFile: resolve(VIEWER_ROOT, "vite.config.ts"),
    server: { port: opts.port, open: false },
  });
  await server.listen();

  const info = server.resolvedUrls;
  const url =
    (info && info.local && info.local[0]) ||
    `http://localhost:${server.config.server.port ?? 5173}/`;

  console.log("");
  console.log(`  Rhize plan viewer (HMR)`);
  console.log(`  plan:  ${planPath}`);
  console.log(`  local: ${url}`);
  console.log("");
  console.log("  Editing the plan file live-reloads the page. Ctrl-C to stop.");
  console.log("");

  if (opts.open) openBrowser(url);

  // Keep the process alive until interrupted.
  const shutdown = async () => {
    await server.close();
    process.exit(0);
  };
  process.on("SIGINT", shutdown);
  process.on("SIGTERM", shutdown);
}

// --------------------------------------------------------------------------
// build
// --------------------------------------------------------------------------
async function runBuild(planPath, opts) {
  process.env.RHIZE_PLAN_PATH = planPath;
  process.env.RHIZE_PLAN_MODE = "build";

  // Build into a fresh temp dir so we don't pollute the viewer folder, then copy
  // the single produced HTML to the destination.
  const outDir = join(
    os.tmpdir(),
    `rhize-plan-build-${Date.now()}-${Math.random().toString(36).slice(2)}`
  );

  await build({
    root: VIEWER_ROOT,
    configFile: resolve(VIEWER_ROOT, "vite.config.ts"),
    logLevel: "warn",
    build: {
      outDir,
      emptyOutDir: true,
    },
  });

  // vite-plugin-singlefile inlines everything into index.html.
  const produced = join(outDir, "index.html");
  if (!existsSync(produced)) {
    // Fallback: find the single .html in the out dir.
    const htmls = readdirSync(outDir).filter((f) => f.endsWith(".html"));
    if (htmls.length === 0) {
      throw new Error(`Build produced no .html in ${outDir}`);
    }
  }
  const sourceHtml = existsSync(produced)
    ? produced
    : join(outDir, readdirSync(outDir).filter((f) => f.endsWith(".html"))[0]);

  // Determine destination.
  let dest;
  if (opts.out) {
    dest = isAbsolute(opts.out) ? opts.out : resolve(process.cwd(), opts.out);
  } else {
    const slug = deriveSlug(planPath);
    dest = join(dirname(planPath), `${slug}.html`);
  }

  copyFileSync(sourceHtml, dest);

  // Clean up the temp build dir.
  try {
    rmSync(outDir, { recursive: true, force: true });
  } catch {
    /* best-effort */
  }

  const bytes = statSync(dest).size;
  console.log("");
  console.log(`  Built self-contained plan HTML`);
  console.log(`  plan:   ${planPath}`);
  console.log(`  output: ${dest}`);
  console.log(`  size:   ${(bytes / 1024).toFixed(0)} KB`);
  console.log("");
  return dest;
}

// --------------------------------------------------------------------------
// main
// --------------------------------------------------------------------------
async function main() {
  const { command, opts } = parseArgs(process.argv.slice(2));

  if (!command || opts.help || command === "help") {
    usage();
    process.exit(command ? 0 : 1);
  }

  if (command !== "serve" && command !== "build") {
    console.error(`rhize-plan: unknown command "${command}"`);
    usage();
    process.exit(1);
  }

  let planPath;
  try {
    planPath = resolvePlanPath(opts._[0]);
  } catch (err) {
    console.error(`rhize-plan: ${err.message}`);
    process.exit(1);
  }

  try {
    if (command === "serve") {
      await runServe(planPath, opts);
    } else {
      await runBuild(planPath, opts);
      process.exit(0);
    }
  } catch (err) {
    console.error(`rhize-plan: ${command} failed`);
    console.error(err && err.stack ? err.stack : String(err));
    process.exit(1);
  }
}

main();
