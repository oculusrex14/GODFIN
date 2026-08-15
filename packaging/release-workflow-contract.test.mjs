import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const root = new URL("../", import.meta.url);

async function source(path) {
  return readFile(new URL(path, root), "utf8");
}

test("draft release binds native assets to an immutable tag and exact evidence", async () => {
  const workflow = await source(".github/workflows/release.yml");

  assert.match(workflow, /ref: \$\{\{ github\.event_name == 'workflow_dispatch' && inputs\.tag \|\| github\.ref \}\}/);
  assert.match(workflow, /test "\$\{RELEASE_TAG#v\}" = "\$\(node -p/);
  assert.match(workflow, /create-release-provenance\.mjs/);
  assert.match(workflow, /verify-release-provenance\.mjs/);
  assert.match(workflow, /godfin\.cdx\.json/);
  assert.match(workflow, /THIRD_PARTY_NOTICES\.md/);
  assert.match(workflow, /legal-clearance\.json/);
  assert.match(workflow, /actions\/attest@1e69f48acb82d1966a394da916b4c1698aa569d6 # v4\.2\.2/);
  assert.match(workflow, /already exists; immutable candidates are never rebuilt in place/);
});

test("promotion verifies every staged byte before publishing", async () => {
  const workflow = await source(".github/workflows/promote-updates.yml");

  assert.match(workflow, /ref: \$\{\{ inputs\.tag \}\}/);
  assert.match(workflow, /sha256sum --check SHA256SUMS\.txt/);
  assert.match(workflow, /verify-release-provenance\.mjs/);
  assert.match(workflow, /verify_supply_chain_artifacts\.py[\s\S]*--promotion/);
  assert.match(workflow, /while read -r _ asset/);
  assert.match(workflow, /gh attestation verify "artifacts\/\$\{asset\}"/);
  assert.match(workflow, /test -n "\$\(find artifacts -name '\*\.dmg'/);
  assert.match(workflow, /test -n "\$\(find artifacts -name '\*\.exe'/);
  assert.match(workflow, /test -n "\$\(find artifacts -name '\*\.AppImage'/);
});

test("dependency refresh always opens a human review path without weakening CI", async () => {
  const workflow = await source(".github/workflows/refresh-python-locks.yml");

  assert.match(workflow, /python scripts\/verify_dependency_boundaries\.py/);
  assert.match(workflow, /id: review-gates[\s\S]*continue-on-error: true/);
  assert.match(workflow, /if: always\(\)/);
  assert.match(workflow, /git push --force-with-lease origin "\$branch"/);
  assert.match(workflow, /A human must review dependency, license, SBOM, audit, and frozen-package changes before merge/);
});

test("release and dependency trust controls require owner review", async () => {
  const codeowners = await source(".github/CODEOWNERS");
  const entries = new Set(codeowners.split("\n"));

  for (const protectedPath of [
    "/.github/workflows/",
    "/backend/requirements*.txt",
    "/packaging/",
    "/supply-chain/",
    "/sbom/",
    "/THIRD_PARTY_NOTICES.md",
  ]) {
    assert.ok(entries.has(`${protectedPath} @oculusrex14`));
  }
});

test("all GitHub Actions dependencies are pinned to immutable commits", async () => {
  for (const path of [
    ".github/workflows/ci.yml",
    ".github/workflows/promote-updates.yml",
    ".github/workflows/refresh-python-locks.yml",
    ".github/workflows/release.yml",
    ".github/workflows/rollback-updates.yml",
  ]) {
    const workflow = await source(path);
    assert.doesNotMatch(workflow, /uses:\s+[^\s@]+@v[0-9]/);
    for (const line of workflow.split("\n").filter((entry) => entry.includes("uses:"))) {
      assert.match(line, /uses:\s+[^\s@]+@[a-f0-9]{40}(?:\s+#\s+v[^\s]+)?$/);
    }
  }
});
