import { createHash } from "node:crypto";
import { createReadStream } from "node:fs";
import { readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

function argument(name) {
  const index = process.argv.indexOf(`--${name}`);
  if (index === -1 || !process.argv[index + 1]) {
    throw new Error(`Missing --${name}`);
  }
  return process.argv[index + 1];
}

async function sha256(filename) {
  const hash = createHash("sha256");
  for await (const chunk of createReadStream(filename)) hash.update(chunk);
  return hash.digest("hex");
}

const root = path.dirname(fileURLToPath(import.meta.url));
const template = await readFile(
  path.join(root, "Casks", "godfin.rb.template"),
  "utf8",
);
const rendered = template
  .replaceAll("__VERSION__", argument("version"))
  .replaceAll("__SHA256_ARM64__", await sha256(argument("arm")))
  .replaceAll("__SHA256_X64__", await sha256(argument("intel")));

await writeFile(argument("output"), rendered, "utf8");
