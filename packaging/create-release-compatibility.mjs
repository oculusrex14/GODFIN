import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import process from "node:process";

function requiredOption(name) {
  const index = process.argv.indexOf(name);
  if (index === -1 || !process.argv[index + 1]) {
    throw new Error(`Missing required option: ${name}`);
  }
  return process.argv[index + 1];
}

function optionalOption(name, fallback = null) {
  const index = process.argv.indexOf(name);
  return index === -1 ? fallback : process.argv[index + 1];
}

function stableVersion(value, label) {
  const normalized = String(value || "").replace(/^v/, "");
  if (!/^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$/.test(normalized)) {
    throw new Error(`${label} must be a stable semantic version.`);
  }
  return normalized;
}

function compare(left, right) {
  const leftParts = left.split(".").map(Number);
  const rightParts = right.split(".").map(Number);
  for (let index = 0; index < 3; index += 1) {
    if (leftParts[index] !== rightParts[index]) {
      return leftParts[index] > rightParts[index] ? 1 : -1;
    }
  }
  return 0;
}

const projectRoot = path.resolve(optionalOption("--project-root", path.join(import.meta.dirname, "..")));
const output = path.resolve(requiredOption("--output"));
const releaseVersion = stableVersion(requiredOption("--version"), "Release version");
const previousRaw = optionalOption("--previous-version");
const previousVersion = previousRaw && previousRaw !== "none"
  ? stableVersion(previousRaw, "Previous version")
  : null;

const desktopPackage = JSON.parse(
  await readFile(path.join(projectRoot, "desktop", "package.json"), "utf8"),
);
const packagedVersion = stableVersion(desktopPackage.version, "Desktop package version");
if (packagedVersion !== releaseVersion) {
  throw new Error(`Release ${releaseVersion} does not match desktop package ${packagedVersion}.`);
}
if (previousVersion && compare(previousVersion, releaseVersion) >= 0) {
  throw new Error("Previous release version must be older than the release version.");
}

const migrations = await readFile(
  path.join(projectRoot, "backend", "app", "core", "startup_migrations.py"),
  "utf8",
);
const revisionMatch = migrations.match(/^CURRENT_SCHEMA_REVISION\s*=\s*(\d+)\s*$/m);
if (!revisionMatch) throw new Error("CURRENT_SCHEMA_REVISION was not found.");
const databaseSchemaRevision = Number(revisionMatch[1]);

const manifest = {
  schema_version: 1,
  app_version: releaseVersion,
  database_schema_revision: databaseSchemaRevision,
  previous_release_version: previousVersion,
  rollback_policy: "immediate_predecessor_verified_snapshot",
  requires_verified_local_snapshot: true,
};
await mkdir(path.dirname(output), { recursive: true });
await writeFile(output, `${JSON.stringify(manifest, null, 2)}\n`, "utf8");
console.log(JSON.stringify(manifest));
