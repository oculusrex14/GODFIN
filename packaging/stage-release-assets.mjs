import { copyFile, mkdir, readdir, rm } from "node:fs/promises";
import path from "node:path";
import process from "node:process";

function option(name) {
  const index = process.argv.indexOf(name);
  if (index === -1 || !process.argv[index + 1]) {
    throw new Error(`Missing required option: ${name}`);
  }
  return path.resolve(process.argv[index + 1]);
}

async function filesBelow(directory) {
  const results = [];
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const candidate = path.join(directory, entry.name);
    if (entry.isDirectory()) results.push(...await filesBelow(candidate));
    else results.push(candidate);
  }
  return results;
}

const input = option("--input");
const output = option("--output");
await rm(output, { recursive: true, force: true });
await mkdir(output, { recursive: true });

const usedNames = new Set();
for (const source of await filesBelow(input)) {
  const relative = path.relative(input, source);
  const artifactGroup = relative.split(path.sep)[0];
  const basename = path.basename(source);
  const releaseName = /^latest.*\.ya?ml$/i.test(basename)
    ? `${artifactGroup}-${basename}`
    : basename;

  if (usedNames.has(releaseName)) {
    throw new Error(`Duplicate release asset name: ${releaseName}`);
  }
  usedNames.add(releaseName);
  await copyFile(source, path.join(output, releaseName));
}

console.log(`Staged ${usedNames.size} uniquely named release assets in ${output}.`);
