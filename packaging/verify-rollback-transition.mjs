import { readFile } from "node:fs/promises";
import path from "node:path";
import process from "node:process";

function option(name) {
  const index = process.argv.indexOf(name);
  if (index === -1 || !process.argv[index + 1]) {
    throw new Error(`Missing required option: ${name}`);
  }
  return path.resolve(process.argv[index + 1]);
}

async function manifest(filename) {
  const value = JSON.parse(await readFile(filename, "utf8"));
  if (
    value.schema_version !== 1
    || !/^\d+\.\d+\.\d+$/.test(value.app_version || "")
    || !Number.isInteger(value.database_schema_revision)
    || value.database_schema_revision < 0
    || value.rollback_policy !== "immediate_predecessor_verified_snapshot"
    || value.requires_verified_local_snapshot !== true
  ) {
    throw new Error(`Invalid release compatibility manifest: ${filename}`);
  }
  return value;
}

const current = await manifest(option("--current"));
const target = await manifest(option("--target"));
if (current.previous_release_version !== target.app_version) {
  throw new Error(
    `Rollback ${current.app_version} → ${target.app_version} is not the declared immediate predecessor transition.`,
  );
}
if (target.database_schema_revision > current.database_schema_revision) {
  throw new Error("Rollback target declares a newer database schema than the current release.");
}
console.log(JSON.stringify({
  current_version: current.app_version,
  target_version: target.app_version,
  target_schema_revision: target.database_schema_revision,
  policy: target.rollback_policy,
}));
