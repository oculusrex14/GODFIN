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

mkdirSync(dirname(destination), { recursive: true });
if (existsSync(source)) {
  copyFileSync(source, destination);
} else if (!existsSync(destination)) {
  throw new Error(
    "Entitlement manifest is unavailable: build from the repository root or include the generated snapshot.",
  );
}
