#!/usr/bin/env node

import { createHash } from "node:crypto";
import { readdir, readFile } from "node:fs/promises";
import path from "node:path";
import process from "node:process";

function parseArguments(argv) {
  const result = {};
  for (let index = 0; index < argv.length; index += 2) {
    const key = argv[index];
    const value = argv[index + 1];
    if (!key?.startsWith("--") || value === undefined) {
      throw new Error(`Invalid argument near ${key || "end of command"}.`);
    }
    result[key.slice(2)] = value;
  }
  if (!result.input || !result.provenance) {
    throw new Error("--input and --provenance are required.");
  }
  return result;
}

async function walk(directory) {
  const entries = await readdir(directory, { withFileTypes: true });
  const files = [];
  for (const entry of entries) {
    const candidate = path.join(directory, entry.name);
    if (entry.isDirectory()) files.push(...await walk(candidate));
    else if (entry.isFile()) files.push(candidate);
  }
  return files;
}

async function sha256(file) {
  return createHash("sha256").update(await readFile(file)).digest("hex");
}

export async function verifyReleaseProvenance({ input, provenance }) {
  const root = path.resolve(input);
  const provenancePath = path.resolve(provenance);
  const statement = JSON.parse(await readFile(provenancePath, "utf8"));
  if (
    statement._type !== "https://in-toto.io/Statement/v1"
    || statement.predicateType !== "https://slsa.dev/provenance/v1"
    || statement.predicate?.buildDefinition?.buildType
      !== "https://github.com/godfin/release-workflow/v1"
  ) {
    throw new Error("Release provenance has an unsupported statement or predicate type.");
  }
  const excluded = new Set([provenancePath, path.join(root, "SHA256SUMS.txt")]);
  const actualFiles = (await walk(root))
    .map((file) => path.resolve(file))
    .filter((file) => !excluded.has(file));
  const actualNames = new Set(
    actualFiles.map((file) => path.relative(root, file).split(path.sep).join("/")),
  );
  const subjects = statement.subject || [];
  const subjectNames = new Set(subjects.map((subject) => subject.name));
  const missing = [...actualNames].filter((name) => !subjectNames.has(name)).sort();
  const extra = [...subjectNames].filter((name) => !actualNames.has(name)).sort();
  if (missing.length || extra.length || subjectNames.size !== subjects.length) {
    throw new Error(
      `Release provenance inventory mismatch (missing: ${missing.join(", ") || "none"}; `
      + `extra/duplicate: ${extra.join(", ") || "none"}).`,
    );
  }
  for (const subject of subjects) {
    const file = path.join(root, subject.name);
    const actual = await sha256(file);
    if (!/^[0-9a-f]{64}$/.test(subject.digest?.sha256 || "") || subject.digest.sha256 !== actual) {
      throw new Error(`Release provenance digest mismatch: ${subject.name}`);
    }
  }
  const commit = statement.predicate?.buildDefinition?.resolvedDependencies?.[0]?.digest?.gitCommit;
  if (!/^[0-9a-f]{40}$/.test(commit || "")) {
    throw new Error("Release provenance does not bind a full Git commit SHA.");
  }
  return { subjects: subjects.length, commit };
}

if (import.meta.url === `file://${process.argv[1]}`) {
  try {
    const result = await verifyReleaseProvenance(parseArguments(process.argv.slice(2)));
    console.log(JSON.stringify(result));
  } catch (error) {
    console.error(error.message);
    process.exitCode = 1;
  }
}
