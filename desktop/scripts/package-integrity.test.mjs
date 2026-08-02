import assert from "node:assert/strict";
import {
  copyFile,
  mkdir,
  mkdtemp,
  readdir,
  rm,
  writeFile,
} from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { assertPackageIntegrity } from "./package-integrity.mjs";

const desktopRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const projectRoot = path.resolve(desktopRoot, "..");
const required = [
  "entitlements.json",
  "model-registry.json",
  "model-registry.json.sig",
  "model-registry-public-key.txt",
];

async function fixture() {
  const root = await mkdtemp(path.join(tmpdir(), "godfin-integrity-"));
  const shared = path.join(root, "godfin-backend", "_internal", "shared");
  await mkdir(shared, { recursive: true });
  for (const name of required) {
    await copyFile(path.join(projectRoot, "shared", name), path.join(shared, name));
  }
  const files = (await readdir(shared)).map((name) => path.join(shared, name));
  return { root, shared, files };
}

test("accepts byte-identical signed registry assets", async () => {
  const current = await fixture();
  try {
    const result = await assertPackageIntegrity(current.files, { projectRoot });
    assert.equal(result.registryVersion, "2026-08-02.1");
    assert.equal(result.pinnedModels, 5);
  } finally {
    await rm(current.root, { recursive: true, force: true });
  }
});

test("rejects a missing signed-registry asset", async () => {
  const current = await fixture();
  try {
    const withoutSignature = current.files.filter(
      (file) => !file.endsWith("model-registry.json.sig"),
    );
    await assert.rejects(
      assertPackageIntegrity(withoutSignature, { projectRoot }),
      /missing required backend asset/,
    );
  } finally {
    await rm(current.root, { recursive: true, force: true });
  }
});

test("rejects an altered packaged registry", async () => {
  const current = await fixture();
  try {
    await writeFile(
      path.join(current.shared, "model-registry.json"),
      '{"schema_version":1,"models":{}}\n',
    );
    await assert.rejects(
      assertPackageIntegrity(current.files, { projectRoot }),
      /does not match the reviewed source asset/,
    );
  } finally {
    await rm(current.root, { recursive: true, force: true });
  }
});
