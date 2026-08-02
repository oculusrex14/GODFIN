import {
  createPublicKey,
  timingSafeEqual,
  verify,
} from "node:crypto";
import { readFile } from "node:fs/promises";
import path from "node:path";

const REQUIRED_SHARED_ASSETS = [
  "entitlements.json",
  "model-registry.json",
  "model-registry.json.sig",
  "model-registry-public-key.txt",
];
const ED25519_SPKI_PREFIX = Buffer.from("302a300506032b6570032100", "hex");
const DIGEST_PATTERN = /^sha256:[0-9a-f]{64}$/;

function normalizedPath(value) {
  return value.split(path.sep).join("/");
}

function packagedCandidates(files, name) {
  const suffix = `/_internal/shared/${name}`;
  return files.filter((file) => normalizedPath(file).endsWith(suffix));
}

async function assertByteIdentical(source, packaged, name) {
  const [expected, actual] = await Promise.all([
    readFile(source),
    readFile(packaged),
  ]);
  if (expected.length !== actual.length || !timingSafeEqual(expected, actual)) {
    throw new Error(`Packaged ${name} does not match the reviewed source asset.`);
  }
  return actual;
}

export async function assertPackageIntegrity(
  files,
  { projectRoot, now = new Date() } = {},
) {
  if (!projectRoot) throw new Error("projectRoot is required for package verification.");

  const packaged = new Map();
  for (const name of REQUIRED_SHARED_ASSETS) {
    const candidates = packagedCandidates(files, name);
    if (!candidates.length) {
      throw new Error(`Package is missing required backend asset: ${name}`);
    }
    for (const candidate of candidates) {
      await assertByteIdentical(
        path.join(projectRoot, "shared", name),
        candidate,
        name,
      );
    }
    packaged.set(name, candidates[0]);
  }

  const payload = await readFile(packaged.get("model-registry.json"));
  const signature = Buffer.from(
    (await readFile(packaged.get("model-registry.json.sig"), "utf8")).trim(),
    "base64",
  );
  const rawPublicKey = Buffer.from(
    (await readFile(packaged.get("model-registry-public-key.txt"), "utf8")).trim(),
    "base64",
  );
  if (rawPublicKey.length !== 32 || signature.length !== 64) {
    throw new Error("Packaged model-registry signature material is malformed.");
  }
  const publicKey = createPublicKey({
    key: Buffer.concat([ED25519_SPKI_PREFIX, rawPublicKey]),
    format: "der",
    type: "spki",
  });
  if (!verify(null, payload, publicKey, signature)) {
    throw new Error("Packaged model-registry signature is invalid.");
  }

  const registry = JSON.parse(payload.toString("utf8"));
  const issuedAt = Date.parse(registry.issued_at);
  const expiresAt = Date.parse(registry.expires_at);
  if (
    registry.schema_version !== 1
    || !Number.isFinite(issuedAt)
    || !Number.isFinite(expiresAt)
    || issuedAt > now.getTime()
    || expiresAt <= now.getTime()
  ) {
    throw new Error("Packaged model registry is inactive, expired, or unsupported.");
  }
  const models = Object.values(registry.models || {});
  if (
    !models.length
    || models.some((model) => !DIGEST_PATTERN.test(model.expected_digest || ""))
  ) {
    throw new Error("Packaged model registry contains an unpinned model.");
  }

  return {
    registryVersion: registry.registry_version,
    pinnedModels: models.length,
    packageCopies: packagedCandidates(files, "model-registry.json").length,
  };
}
