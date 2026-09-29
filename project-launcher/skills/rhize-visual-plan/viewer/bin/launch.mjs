#!/usr/bin/env node
/**
 * launch.mjs — run the rhize-plan viewer from any install without writing
 * node_modules into the skill directory.
 *
 *   node launch.mjs serve <path-to-plan.mdx|dir> [--port N] [--no-open]
 *   node launch.mjs build <path-to-plan.mdx|dir> [-o out.html]
 *   node launch.mjs --print-root      # print the cache directory, install nothing
 *   node launch.mjs --prepare-only    # install into the cache, run nothing
 *
 * The skill directory may be a version-pinned plugin cache that is replaced on
 * every plugin update, so nothing is ever installed there. Instead the viewer's
 * shipped files (an explicit list, below) are copied to
 *   $RHIZE_PLAN_VIEWER_HOME  (default: ${XDG_CACHE_HOME:-~/.cache}/rhize-plan-viewer)
 *   /<content-hash>/
 * dependencies are installed there once with `npm ci` against the committed
 * lockfile, and bin/rhize-plan.mjs runs from the copy — so its VIEWER_ROOT, and
 * vite.config.ts's node_modules aliases, resolve to the cache copy unchanged.
 *
 * Node builtins only: this file must run before any dependency exists.
 * RHIZE_PLAN_NPM overrides the npm executable (tests use a stub).
 */

import { createHash } from "node:crypto";
import {
  chmodSync,
  copyFileSync,
  existsSync,
  lstatSync,
  mkdirSync,
  readdirSync,
  readFileSync,
  renameSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import os from "node:os";
import { dirname, join, resolve } from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const SRC = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const READY = ".ready";
// What the viewer needs at runtime. Everything else in the directory (README,
// this launcher, a dev checkout's node_modules/dist/exports) is never copied.
const SHIPPED_FILES = ["package.json", "package-lock.json", "index.html", "vite.config.ts", "bin/rhize-plan.mjs"];
const SHIPPED_DIRS = ["src"];

class LaunchError extends Error {}

function regularFile(abs) {
  const st = lstatSync(abs, { throwIfNoEntry: false });
  if (!st) return false;
  if (st.isSymbolicLink()) throw new LaunchError(`refusing symlink in viewer sources: ${abs}`);
  return st.isFile();
}

function walk(relDir, out) {
  for (const entry of readdirSync(join(SRC, relDir), { withFileTypes: true })) {
    const rel = `${relDir}/${entry.name}`;
    if (entry.isSymbolicLink()) throw new LaunchError(`refusing symlink in viewer sources: ${rel}`);
    if (entry.isDirectory()) walk(rel, out);
    else if (entry.isFile()) out.push(rel);
  }
}

function shippedFiles() {
  const files = [];
  for (const rel of SHIPPED_FILES) {
    if (!regularFile(join(SRC, rel))) {
      if (rel === "package-lock.json") {
        throw new LaunchError("viewer/package-lock.json is missing; refusing an unpinned install");
      }
      throw new LaunchError(`viewer file missing: ${rel}`);
    }
    files.push(rel);
  }
  for (const dir of SHIPPED_DIRS) walk(dir, files);
  return files.sort();
}

function contentHash(root, files) {
  const h = createHash("sha256");
  for (const rel of files) {
    const digest = createHash("sha256").update(readFileSync(join(root, rel))).digest("hex");
    h.update(`${rel}\0${digest}\n`);
  }
  return h.digest("hex");
}

function cacheRoot() {
  if (process.env.RHIZE_PLAN_VIEWER_HOME) return resolve(process.env.RHIZE_PLAN_VIEWER_HOME);
  const base = process.env.XDG_CACHE_HOME || join(os.homedir(), ".cache");
  return join(base, "rhize-plan-viewer");
}

function ensurePrivateDir(dir) {
  mkdirSync(dir, { recursive: true, mode: 0o700 });
  const st = lstatSync(dir);
  if (st.isSymbolicLink() || !st.isDirectory()) throw new LaunchError(`cache path is not a real directory: ${dir}`);
  if (process.platform !== "win32") chmodSync(dir, 0o700);
}

// A cache entry is trusted only if it is a real directory whose marker names
// this exact content hash, whose copied sources still hash to it, and whose
// install produced node_modules.
function validInstall(dest, files, hash) {
  const st = lstatSync(dest, { throwIfNoEntry: false });
  if (!st) return false;
  if (st.isSymbolicLink() || !st.isDirectory()) throw new LaunchError(`cache entry is not a real directory: ${dest}`);
  try {
    if (readFileSync(join(dest, READY), "utf8").trim() !== hash) return false;
    if (!lstatSync(join(dest, "node_modules")).isDirectory()) return false;
    for (const rel of files) if (!regularFile(join(dest, rel))) return false;
    return contentHash(dest, files) === hash;
  } catch {
    return false;
  }
}

function runNpm(cwd) {
  const npm = process.env.RHIZE_PLAN_NPM || (process.platform === "win32" ? "npm.cmd" : "npm");
  const args = ["ci", "--no-audit", "--no-fund"];
  // Windows runs npm through npm.cmd, which needs a shell; the arguments are
  // fixed constants, so nothing user-controlled reaches it.
  const result = spawnSync(npm, args, {
    cwd,
    stdio: ["ignore", "inherit", "inherit"],
    shell: process.platform === "win32" && !process.env.RHIZE_PLAN_NPM,
  });
  if (result.error || result.status !== 0) {
    const why = result.error ? result.error.message : result.signal ? `signal ${result.signal}` : `exit ${result.status}`;
    throw new LaunchError(`\`${npm} ${args.join(" ")}\` failed (${why})`);
  }
}

function prepare(files, hash, dest) {
  if (validInstall(dest, files, hash)) return;
  const root = dirname(dest);
  ensurePrivateDir(root);
  const tmp = join(root, `.tmp-${hash.slice(0, 16)}-${process.pid}-${Date.now()}`);
  try {
    mkdirSync(tmp, { mode: 0o700 });
    for (const rel of files) {
      mkdirSync(join(tmp, dirname(rel)), { recursive: true });
      copyFileSync(join(SRC, rel), join(tmp, rel));
    }
    console.error(`rhize-plan: installing viewer dependencies into ${dest} (first run only)…`);
    runNpm(tmp);
    writeFileSync(join(tmp, READY), `${hash}\n`);
    try {
      renameSync(tmp, dest);
    } catch {
      // Either a concurrent first run published a complete copy first, or an
      // incomplete/corrupt entry is in the way. Only a verified copy is kept.
      if (!validInstall(dest, files, hash)) {
        rmSync(dest, { recursive: true, force: true });
        renameSync(tmp, dest);
      }
    }
    if (!validInstall(dest, files, hash)) throw new LaunchError(`cache entry failed verification: ${dest}`);
  } finally {
    rmSync(tmp, { recursive: true, force: true });
  }
}

function main(argv) {
  const files = shippedFiles();
  const hash = contentHash(SRC, files);
  const dest = join(cacheRoot(), hash.slice(0, 16));
  if (argv[0] === "--print-root") {
    console.log(dest);
    return 0;
  }
  prepare(files, hash, dest);
  if (argv[0] === "--prepare-only") {
    console.log(dest);
    return 0;
  }
  const child = spawnSync(process.execPath, [join(dest, "bin", "rhize-plan.mjs"), ...argv], { stdio: "inherit" });
  if (child.error) throw new LaunchError(child.error.message);
  if (child.signal) {
    process.kill(process.pid, child.signal); // re-raise so callers see the same signal
    return 1;
  }
  return child.status ?? 1;
}

try {
  process.exitCode = main(process.argv.slice(2));
} catch (err) {
  console.error(`rhize-plan: ${err instanceof LaunchError ? err.message : err.stack}`);
  process.exitCode = 1;
}
