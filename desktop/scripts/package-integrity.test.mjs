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
const requiredLegal = new Map([
  ["LICENSE", "LICENSE"],
  ["THIRD_PARTY_NOTICES.md", "THIRD_PARTY_NOTICES.md"],
  ["godfin.cdx.json", "sbom/godfin.cdx.json"],
  ["legal-clearance.json", "supply-chain/legal-clearance.json"],
]);

async function fixture() {
  const root = await mkdtemp(path.join(tmpdir(), "godfin-integrity-"));
  const shared = path.join(root, "godfin-backend", "_internal", "shared");
  await mkdir(shared, { recursive: true });
  for (const name of required) {
    await copyFile(path.join(projectRoot, "shared", name), path.join(shared, name));
  }
  const legal = path.join(root, "GODFIN.app", "Contents", "Resources", "legal");
  await mkdir(legal, { recursive: true });
  for (const [name, sourcePath] of requiredLegal) {
    await copyFile(path.join(projectRoot, sourcePath), path.join(legal, name));
  }
  const files = [
    ...(await readdir(shared)).map((name) => path.join(shared, name)),
    ...(await readdir(legal)).map((name) => path.join(legal, name)),
  ];
  return { root, shared, files };
}

test("accepts byte-identical signed registry assets", async () => {
  const current = await fixture();
  try {
    const result = await assertPackageIntegrity(current.files, { projectRoot });
    assert.equal(result.registryVersion, "2026-08-02.1");
    assert.equal(result.pinnedModels, 5);
    assert.equal(result.legalAssets, 4);
  } finally {
    await rm(current.root, { recursive: true, force: true });
  }
});

test("rejects a missing legal or SBOM asset", async () => {
  const current = await fixture();
  try {
    const withoutSbom = current.files.filter(
      (file) => !file.endsWith("godfin.cdx.json"),
    );
    await assert.rejects(
      assertPackageIntegrity(withoutSbom, { projectRoot }),
      /exactly one reviewed legal asset: godfin.cdx.json/,
    );
  } finally {
    await rm(current.root, { recursive: true, force: true });
  }
});

test("rejects an altered legal notice", async () => {
  const current = await fixture();
  try {
    const notice = current.files.find((file) => file.endsWith("THIRD_PARTY_NOTICES.md"));
    await writeFile(notice, "altered notice\n");
    await assert.rejects(
      assertPackageIntegrity(current.files, { projectRoot }),
      /does not match the reviewed source asset/,
    );
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
