import assert from "node:assert/strict";
import { mkdir, mkdtemp, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import test from "node:test";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const prepareScript = path.join(root, "packaging", "prepare-update-feed.mjs");
const createScript = path.join(root, "packaging", "create-release-compatibility.mjs");
const verifyScript = path.join(root, "packaging", "verify-rollback-transition.mjs");
const metadataNames = [
  "macos-arm64-latest-mac.yml",
  "macos-x64-latest-mac.yml",
  "windows-x64-latest.yml",
  "linux-x64-latest-linux.yml",
];

function run(script, args, expectedStatus = 0) {
  const result = spawnSync(process.execPath, [script, ...args], {
    cwd: root,
    encoding: "utf8",
    shell: false,
  });
  assert.equal(result.status, expectedStatus, result.stderr || result.stdout);
  return result;
}

async function compatibilityFixture(directory, version, previousVersion, revision) {
  await mkdir(path.join(directory, "desktop"), { recursive: true });
  await mkdir(path.join(directory, "backend", "app", "core"), { recursive: true });
  await writeFile(
    path.join(directory, "desktop", "package.json"),
    JSON.stringify({ version }),
  );
  await writeFile(
    path.join(directory, "backend", "app", "core", "startup_migrations.py"),
    `CURRENT_SCHEMA_REVISION = ${revision}\n`,
  );
  const output = path.join(directory, "release-compatibility.json");
  const args = [
    "--project-root", directory,
    "--version", version,
    "--output", output,
  ];
  if (previousVersion) args.push("--previous-version", previousVersion);
  run(createScript, args);
  return output;
}

test("prepares architecture feeds with an explicit staged rollout", async () => {
  const directory = await mkdtemp(path.join(tmpdir(), "godfin-update-feed-"));
  const input = path.join(directory, "input");
  const output = path.join(directory, "output");
  await mkdir(input);
  const artifact = "GODFIN-1.1.0-update.bin";
  await writeFile(path.join(input, artifact), "signed fixture");
  for (const name of metadataNames) {
    await writeFile(
      path.join(input, name),
      `version: 1.1.0\npath: ${artifact}\nstagingPercentage: 100\n`,
    );
  }
  await writeFile(
    path.join(input, "release-compatibility.json"),
    JSON.stringify({
      schema_version: 1,
      app_version: "1.1.0",
      database_schema_revision: 16,
      previous_release_version: "1.0.0",
      rollback_policy: "immediate_predecessor_verified_snapshot",
      requires_verified_local_snapshot: true,
    }),
  );

  run(prepareScript, [
    "--input", input,
    "--output", output,
    "--version", "v1.1.0",
    "--rollout-percentage", "25",
  ]);
  for (const channel of ["darwin-arm64", "darwin-x64", "win32-x64", "linux-x64"]) {
    const files = await Promise.all([
      readFile(path.join(output, channel, "release-compatibility.json"), "utf8"),
      readFile(
        path.join(output, channel, channel.startsWith("darwin")
          ? "latest-mac.yml"
          : channel.startsWith("win32") ? "latest.yml" : "latest-linux.yml"),
        "utf8",
      ),
    ]);
    assert.equal(JSON.parse(files[0]).app_version, "1.1.0");
    assert.match(files[1], /stagingPercentage: 25/);
    assert.match(files[1], /\.\.\/v1\.1\.0\/GODFIN-1\.1\.0-update\.bin/);
    assert.equal((files[1].match(/stagingPercentage:/g) || []).length, 1);
  }
});

test("rejects unsafe rollout percentages and mismatched release metadata", async () => {
  const directory = await mkdtemp(path.join(tmpdir(), "godfin-update-invalid-"));
  await mkdir(path.join(directory, "input"));
  const result = spawnSync(process.execPath, [
    prepareScript,
    "--input", path.join(directory, "input"),
    "--output", path.join(directory, "output"),
    "--version", "v1.1.0",
    "--rollout-percentage", "0",
  ], { encoding: "utf8", shell: false });
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /Rollout percentage/);
});

test("release manifests bind app, schema, and immediate predecessor", async () => {
  const directory = await mkdtemp(path.join(tmpdir(), "godfin-compatibility-"));
  const currentRoot = path.join(directory, "current-project");
  const targetRoot = path.join(directory, "target-project");
  const olderRoot = path.join(directory, "older-project");
  const current = await compatibilityFixture(currentRoot, "1.2.0", "1.1.0", 16);
  const target = await compatibilityFixture(targetRoot, "1.1.0", "1.0.0", 15);
  const older = await compatibilityFixture(olderRoot, "1.0.0", null, 14);

  run(verifyScript, ["--current", current, "--target", target]);
  const invalid = spawnSync(process.execPath, [
    verifyScript,
    "--current", current,
    "--target", older,
  ], { cwd: root, encoding: "utf8", shell: false });
  assert.notEqual(invalid.status, 0);
  assert.match(invalid.stderr, /not the declared immediate predecessor/);
});

test("promotion and rollback workflows retain their manual safety gates", async () => {
  const promotion = await readFile(
    path.join(root, ".github", "workflows", "promote-updates.yml"),
    "utf8",
  );
  const rollback = await readFile(
    path.join(root, ".github", "workflows", "rollback-updates.yml"),
    "utf8",
  );
  assert.match(promotion, /PUBLISH_STAGED_RELEASE/);
  assert.match(promotion, /ADVANCE_AFTER_HEALTH_REVIEW/);
  assert.match(promotion, /--rollout-percentage/);
  assert.match(promotion, /release-compatibility\.json/);
  assert.match(rollback, /current_tag:/);
  assert.match(rollback, /verify-rollback-transition\.mjs/);
  assert.match(rollback, /--rollout-percentage 100/);
  assert.match(rollback, /ROLLBACK_SIGNED_RELEASE/);
});
