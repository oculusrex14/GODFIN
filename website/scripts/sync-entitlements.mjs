import { copyFileSync, mkdirSync } from "node:fs";
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
copyFileSync(source, destination);
