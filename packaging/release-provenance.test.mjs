import assert from "node:assert/strict";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";

import { createReleaseProvenance } from "./create-release-provenance.mjs";
import { verifyReleaseProvenance } from "./verify-release-provenance.mjs";

const options = {
  version: "0.1.0",
  repository: "oculusrex14/GODFIN",
  commit: "a".repeat(40),
  ref: "refs/tags/v0.1.0",
  workflow: ".github/workflows/release.yml",
  "run-id": "123",
  "run-attempt": "1",
  "generated-at": "2026-08-15T00:00:00Z",
};

test("binds every exact staged asset to workflow and commit provenance", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "godfin-provenance-"));
  try {
    await writeFile(path.join(root, "installer.dmg"), "signed fixture");
    await writeFile(path.join(root, "godfin.cdx.json"), "{}");
    const provenance = path.join(root, "release-provenance.intoto.json");
    await createReleaseProvenance({ ...options, input: root, output: provenance });
    const result = await verifyReleaseProvenance({ input: root, provenance });
    assert.equal(result.subjects, 2);
    assert.equal(result.commit, options.commit);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("rejects an asset changed after provenance generation", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "godfin-provenance-"));
  try {
    const asset = path.join(root, "installer.exe");
    await writeFile(asset, "signed fixture");
    const provenance = path.join(root, "release-provenance.intoto.json");
    await createReleaseProvenance({ ...options, input: root, output: provenance });
    await writeFile(asset, "tampered fixture");
    await assert.rejects(
      verifyReleaseProvenance({ input: root, provenance }),
      /digest mismatch/,
    );
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("rejects an asset added after provenance generation", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "godfin-provenance-"));
  try {
    await writeFile(path.join(root, "installer.AppImage"), "fixture");
    const provenance = path.join(root, "release-provenance.intoto.json");
    await createReleaseProvenance({ ...options, input: root, output: provenance });
    await writeFile(path.join(root, "unreviewed.txt"), "late addition");
    await assert.rejects(
      verifyReleaseProvenance({ input: root, provenance }),
      /inventory mismatch/,
    );
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});
