import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readdir, readFile } from "node:fs/promises";
import path from "node:path";
import process from "node:process";

const websiteRoot = path.resolve(process.cwd());
const migrationRoot = path.join(websiteRoot, "supabase", "migrations");
const manifest = JSON.parse(
  await readFile(
    path.join(websiteRoot, "supabase", "migration-manifest.json"),
    "utf8",
  ),
);

assert.equal(manifest.schema_version, 1, "Unsupported migration manifest.");
assert.ok(
  manifest.migrations && typeof manifest.migrations === "object",
  "Migration manifest is empty.",
);

const actualFiles = (await readdir(migrationRoot))
  .filter((name) => /^\d{4}_[a-z0-9_]+\.sql$/.test(name))
  .sort();
const expectedFiles = Object.keys(manifest.migrations).sort();
assert.deepEqual(
  actualFiles,
  expectedFiles,
  "Every ordered SQL migration must be registered before build.",
);

for (const filename of actualFiles) {
  const bytes = await readFile(path.join(migrationRoot, filename));
  const digest = createHash("sha256").update(bytes).digest("hex");
  assert.equal(
    digest,
    manifest.migrations[filename],
    `Migration ${filename} changed after registration. Add a new migration or explicitly review and update the manifest.`,
  );
}

console.log(`Verified ${actualFiles.length} ordered Supabase migration hashes.`);
