import { access, copyFile, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import process from "node:process";

function option(name) {
  const index = process.argv.indexOf(name);
  if (index === -1 || !process.argv[index + 1]) {
    throw new Error(`Missing required option: ${name}`);
  }
  return process.argv[index + 1];
}

const input = path.resolve(option("--input"));
const output = path.resolve(option("--output"));
const version = option("--version");
if (!/^v?\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$/.test(version)) {
  throw new Error(`Invalid immutable release version: ${version}`);
}
const rolloutPercentage = Number(option("--rollout-percentage"));
if (!Number.isInteger(rolloutPercentage) || rolloutPercentage < 1 || rolloutPercentage > 100) {
  throw new Error("Rollout percentage must be an integer from 1 through 100.");
}
const normalizedVersion = version.replace(/^v/, "");
const compatibilitySource = path.join(input, "release-compatibility.json");
const compatibility = JSON.parse(await readFile(compatibilitySource, "utf8"));
if (
  compatibility.schema_version !== 1
  || compatibility.app_version !== normalizedVersion
  || compatibility.rollback_policy !== "immediate_predecessor_verified_snapshot"
  || compatibility.requires_verified_local_snapshot !== true
) {
  throw new Error("Release compatibility metadata does not match this update version.");
}

const channels = {
  "macos-arm64-latest-mac.yml": ["darwin-arm64", "latest-mac.yml"],
  "macos-x64-latest-mac.yml": ["darwin-x64", "latest-mac.yml"],
  "windows-x64-latest.yml": ["win32-x64", "latest.yml"],
  "linux-x64-latest-linux.yml": ["linux-x64", "latest-linux.yml"],
};

await rm(output, { recursive: true, force: true });
for (const [sourceName, [channel, destinationName]] of Object.entries(channels)) {
  const source = path.join(input, sourceName);
  let metadata = await readFile(source, "utf8");
  const metadataVersion = metadata.match(/^version:\s*['"]?([^'"\s]+)['"]?\s*$/m)?.[1];
  if (metadataVersion !== normalizedVersion) {
    throw new Error(`${sourceName} declares version ${metadataVersion || "(missing)"}, expected ${normalizedVersion}.`);
  }
  const referenced = new Set();
  metadata = metadata
    .split(/\r?\n/)
    .map((line) => {
      const match = line.match(/^(\s*(?:-\s+url|path):\s+)(.+?)\s*$/);
      if (!match) return line;
      const rawValue = match[2].replace(/^['"]|['"]$/g, "");
      if (/^https?:\/\//i.test(rawValue)) return line;
      const filename = path.basename(rawValue);
      referenced.add(filename);
      return `${match[1]}../${version}/${filename}`;
    })
    .filter((line) => !/^stagingPercentage:\s*/.test(line))
    .concat(`stagingPercentage: ${rolloutPercentage}`)
    .join("\n");

  for (const filename of referenced) {
    await access(path.join(input, filename));
  }
  if (referenced.size === 0) {
    throw new Error(`${sourceName} does not reference an update artifact.`);
  }

  const channelDirectory = path.join(output, channel);
  await mkdir(channelDirectory, { recursive: true });
  await writeFile(path.join(channelDirectory, destinationName), metadata, "utf8");
  await copyFile(
    compatibilitySource,
    path.join(channelDirectory, "release-compatibility.json"),
  );
}

console.log(
  `Prepared ${Object.keys(channels).length} architecture-specific update channels at ${rolloutPercentage}%.`,
);
