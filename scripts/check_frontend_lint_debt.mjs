#!/usr/bin/env node
/**
 * Lint changed frontend source files only.
 *
 * The repository currently contains legacy lint debt across unrelated files.
 * This lets a PR enforce ESLint on files it actually changes without hiding
 * typecheck, unit-test, or production-build failures.
 */
import { execFileSync, spawnSync } from "node:child_process";
import path from "node:path";

const base = process.argv[2];
if (!base) {
  console.error("Usage: node scripts/check_frontend_lint_debt.mjs <base-ref>");
  process.exit(2);
}

const root = process.cwd();
const frontendRoot = path.join(root, "frontend", "web");
let changedPaths;
try {
  const output = execFileSync(
    "git",
    [
      "diff",
      "--name-only",
      "--diff-filter=ACMR",
      `${base}...HEAD`,
      "--",
      "frontend/web",
    ],
    { cwd: root, encoding: "utf8" },
  );
  changedPaths = output
    .split(/\r?\n/)
    .map((item) => item.trim())
    .filter(Boolean)
    .filter((item) => /\.(?:[cm]?[jt]sx?)$/i.test(item))
    .map((item) => path.relative("frontend/web", item));
} catch (error) {
  console.error("Could not determine changed frontend files from Git.");
  console.error(error instanceof Error ? error.message : String(error));
  process.exit(2);
}

if (changedPaths.length === 0) {
  console.log("No changed frontend source files; ESLint diff check skipped.");
  process.exit(0);
}

console.log(`ESLint will check ${changedPaths.length} changed frontend source file(s).`);
const command = process.platform === "win32" ? "npx.cmd" : "npx";
const result = spawnSync(
  command,
  ["--no-install", "eslint", "--quiet", ...changedPaths],
  {
    cwd: frontendRoot,
    stdio: "inherit",
    shell: process.platform === "win32",
  },
);

if (result.error) {
  console.error(result.error.message);
  process.exit(2);
}
process.exit(typeof result.status === "number" ? result.status : 2);
