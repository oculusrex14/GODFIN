import {
  createPrivateKey,
  randomUUID,
  sign,
} from "node:crypto";

import {
  ENTITLEMENTS,
  releasedFeatures,
  type PaidLicenseTier,
} from "@/lib/entitlements";
import { serverEnv } from "@/lib/env";

const ENVELOPE_SCHEMA_VERSION = 1;
const MAX_TTL_HOURS = 31 * 24;

type SigningKeyMap = Record<string, string>;

function privateSigningKeys(): SigningKeyMap {
  let value: unknown;
  try {
    value = JSON.parse(serverEnv.licenseEntitlementPrivateKeysJson());
  } catch {
    throw new Error("License entitlement signing keys are invalid.");
  }
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("License entitlement signing keys are invalid.");
  }
  return value as SigningKeyMap;
}

function entitlementTtlHours(): number {
  const raw = Number(process.env.LICENSE_ENTITLEMENT_TTL_HOURS || "168");
  if (!Number.isInteger(raw) || raw < 1 || raw > MAX_TTL_HOURS) {
    throw new Error("LICENSE_ENTITLEMENT_TTL_HOURS is invalid.");
  }
  return raw;
}

export function signEntitlement({
  licenseId,
  tier,
  installationHash,
  licenseStateVersion,
  now = new Date(),
}: {
  licenseId: string;
  tier: PaidLicenseTier;
  installationHash: string;
  licenseStateVersion: number;
  now?: Date;
}) {
  const keyVersion = serverEnv.licenseEntitlementActiveKeyVersion();
  const encodedKey = privateSigningKeys()[keyVersion];
  if (typeof encodedKey !== "string" || !encodedKey) {
    throw new Error("The active license entitlement signing key is unavailable.");
  }
  if (!/^[0-9a-f-]{36}$/i.test(licenseId) || !/^[0-9a-f]{64}$/i.test(installationHash)) {
    throw new Error("License entitlement identifiers are invalid.");
  }
  if (!Number.isSafeInteger(licenseStateVersion) || licenseStateVersion < 1) {
    throw new Error("License entitlement state version is invalid.");
  }

  const expiresAt = new Date(now.getTime() + entitlementTtlHours() * 60 * 60 * 1000);
  const claims = {
    schema_version: ENVELOPE_SCHEMA_VERSION,
    issuer: "godfin-license-service",
    audience: "godfin-desktop",
    key_version: keyVersion,
    license_id: licenseId,
    tier,
    features: releasedFeatures(tier),
    entitlement_version: ENTITLEMENTS.schema_version,
    installation_hash: installationHash,
    issued_at: now.toISOString(),
    expires_at: expiresAt.toISOString(),
    token_id: randomUUID(),
    license_state_version: licenseStateVersion,
  };
  const payloadBytes = Buffer.from(JSON.stringify(claims), "utf8");
  const privateKey = createPrivateKey({
    key: Buffer.from(encodedKey, "base64"),
    format: "der",
    type: "pkcs8",
  });
  const signature = sign(null, payloadBytes, privateKey);
  return {
    schema_version: ENVELOPE_SCHEMA_VERSION,
    algorithm: "Ed25519",
    key_version: keyVersion,
    payload: payloadBytes.toString("base64url"),
    signature: signature.toString("base64url"),
  };
}
