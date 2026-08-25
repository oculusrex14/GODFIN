import { copyFileSync, existsSync, mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const websiteRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const source = resolve(websiteRoot, "..", "shared", "entitlements.json");
const destination = resolve(
  websiteRoot,
  "src",
  "generated",
  "entitlements.json",
);
const publicClaimsSource = resolve(
  websiteRoot,
  "..",
  "docs",
  "production-remediation",
  "PUBLIC_CLAIMS_POLICY.json",
);
const publicClaimsDestination = resolve(
  websiteRoot,
  "src",
  "generated",
  "public-claims-policy.json",
);
const publicKeysSource = resolve(
  websiteRoot,
  "..",
  "shared",
  "license-entitlement-public-keys.json",
);
const publicKeysDestination = resolve(
  websiteRoot,
  "src",
  "generated",
  "license-entitlement-public-keys.json",
);

mkdirSync(dirname(destination), { recursive: true });
if (existsSync(source)) {
  copyFileSync(source, destination);
} else if (!existsSync(destination)) {
  throw new Error(
    "Entitlement manifest is unavailable: build from the repository root or include the generated snapshot.",
  );
}

mkdirSync(dirname(publicClaimsDestination), { recursive: true });
if (existsSync(publicClaimsSource)) {
  copyFileSync(publicClaimsSource, publicClaimsDestination);
} else if (!existsSync(publicClaimsDestination)) {
  throw new Error(
    "Public claims policy is unavailable: build from the repository root or include the generated snapshot.",
  );
}

mkdirSync(dirname(publicKeysDestination), { recursive: true });
if (existsSync(publicKeysSource)) {
  copyFileSync(publicKeysSource, publicKeysDestination);
} else if (!existsSync(publicKeysDestination)) {
  throw new Error(
    "License public-key manifest is unavailable: build from the repository root or include the generated snapshot.",
  );
}
