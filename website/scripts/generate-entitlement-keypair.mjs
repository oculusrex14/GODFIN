import { generateKeyPairSync } from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

function argument(name) {
  const index = process.argv.indexOf(name);
  return index >= 0 ? process.argv[index + 1] : null;
}

const keyVersion = argument("--key-version");
const privateOutput = argument("--private-output");
const publicOutput = argument("--public-output");
if (!keyVersion || !/^[a-z0-9][a-z0-9._-]{2,63}$/i.test(keyVersion)) {
  throw new Error("Provide a safe --key-version value.");
}
if (!privateOutput || !publicOutput) {
  throw new Error("Provide explicit --private-output and --public-output paths.");
}

const scriptDirectory = path.dirname(fileURLToPath(import.meta.url));
const repositoryRoot = path.resolve(scriptDirectory, "../..");
const resolvedPrivateOutput = path.resolve(privateOutput);
if (
  resolvedPrivateOutput === repositoryRoot
  || resolvedPrivateOutput.startsWith(`${repositoryRoot}${path.sep}`)
) {
  throw new Error("The private signing key must never be written inside the repository.");
}

const { privateKey, publicKey } = generateKeyPairSync("ed25519");
const privateDer = privateKey.export({ format: "der", type: "pkcs8" });
const publicDer = publicKey.export({ format: "der", type: "spki" });

let privateKeys = {};
try {
  privateKeys = JSON.parse(await fs.readFile(resolvedPrivateOutput, "utf8"));
} catch (error) {
  if (error?.code !== "ENOENT") throw error;
}
if (privateKeys[keyVersion]) {
  throw new Error(`Private signing key version already exists: ${keyVersion}`);
}
privateKeys[keyVersion] = Buffer.from(privateDer).toString("base64");
await fs.mkdir(path.dirname(resolvedPrivateOutput), { recursive: true, mode: 0o700 });
const privateParent = await fs.realpath(path.dirname(resolvedPrivateOutput));
const realRepositoryRoot = await fs.realpath(repositoryRoot);
if (
  privateParent === realRepositoryRoot ||
  privateParent.startsWith(`${realRepositoryRoot}${path.sep}`)
) {
  throw new Error("The private signing key must never be written inside the repository.");
}
const privateTemporary = `${resolvedPrivateOutput}.tmp`;
await fs.writeFile(
  privateTemporary,
  `${JSON.stringify(privateKeys, null, 2)}\n`,
  { encoding: "utf8", mode: 0o600 },
);
await fs.chmod(privateTemporary, 0o600);
await fs.rename(privateTemporary, resolvedPrivateOutput);

const resolvedPublicOutput = path.resolve(publicOutput);
let publicManifest = { schema_version: 1, keys: {} };
try {
  publicManifest = JSON.parse(await fs.readFile(resolvedPublicOutput, "utf8"));
} catch (error) {
  if (error?.code !== "ENOENT") throw error;
}
for (const entry of Object.values(publicManifest.keys || {})) {
  if (entry?.status === "active") entry.status = "overlap";
}
publicManifest.schema_version = 1;
publicManifest.keys ||= {};
publicManifest.keys[keyVersion] = {
  status: "active",
  algorithm: "Ed25519",
  public_key_spki_b64: Buffer.from(publicDer).toString("base64"),
};
await fs.mkdir(path.dirname(resolvedPublicOutput), { recursive: true });
const publicTemporary = `${resolvedPublicOutput}.tmp`;
await fs.writeFile(
  publicTemporary,
  `${JSON.stringify(publicManifest, null, 2)}\n`,
  "utf8",
);
await fs.rename(publicTemporary, resolvedPublicOutput);

console.log(
  JSON.stringify({
    key_version: keyVersion,
    private_output: resolvedPrivateOutput,
    public_output: resolvedPublicOutput,
  }),
);
