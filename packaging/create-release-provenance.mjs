#!/usr/bin/env node

import { createHash } from "node:crypto";
import { readdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import process from "node:process";

function parseArguments(argv) {
  const values = new Map();
  for (let index = 0; index < argv.length; index += 2) {
    const key = argv[index];
    const value = argv[index + 1];
    if (!key?.startsWith("--") || value === undefined) {
      throw new Error(`Invalid argument near ${key || "end of command"}.`);
    }
    values.set(key.slice(2), value);
  }
  const required = [
    "input",
    "output",
    "version",
    "repository",
    "commit",
    "ref",
    "workflow",
    "run-id",
    "run-attempt",
    "generated-at",
  ];
  for (const name of required) {
    if (!values.get(name)) throw new Error(`--${name} is required.`);
  }
  return Object.fromEntries(values);
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

async function digest(file) {
  return createHash("sha256").update(await readFile(file)).digest("hex");
}

export async function createReleaseProvenance(options) {
  const input = path.resolve(options.input);
  const output = path.resolve(options.output);
  const excluded = new Set([
    output,
    path.join(input, "SHA256SUMS.txt"),
  ]);
  const files = (await walk(input))
    .map((file) => path.resolve(file))
    .filter((file) => !excluded.has(file))
    .sort();
  if (!files.length) throw new Error("No release subjects were found.");
  const subjects = [];
  for (const file of files) {
    subjects.push({
      name: path.relative(input, file).split(path.sep).join("/"),
      digest: { sha256: await digest(file) },
    });
  }
  const statement = {
    _type: "https://in-toto.io/Statement/v1",
    subject: subjects,
    predicateType: "https://slsa.dev/provenance/v1",
    predicate: {
      buildDefinition: {
        buildType: "https://github.com/godfin/release-workflow/v1",
        externalParameters: {
          version: options.version,
          repository: options.repository,
          ref: options.ref,
          workflow: options.workflow,
        },
        internalParameters: {
          runId: options["run-id"],
          runAttempt: options["run-attempt"],
        },
        resolvedDependencies: [
          {
            uri: `git+https://github.com/${options.repository}@${options.commit}`,
            digest: { gitCommit: options.commit },
          },
        ],
      },
      runDetails: {
        builder: {
          id: `https://github.com/${options.repository}/actions/runs/${options["run-id"]}`,
        },
        metadata: {
          invocationId: `${options["run-id"]}-${options["run-attempt"]}`,
          startedOn: options["generated-at"],
          finishedOn: options["generated-at"],
        },
      },
    },
  };
  await writeFile(output, `${JSON.stringify(statement, null, 2)}\n`, "utf8");
  return statement;
}

if (import.meta.url === `file://${process.argv[1]}`) {
  try {
    const options = parseArguments(process.argv.slice(2));
    await createReleaseProvenance(options);
    console.log(`Created ${options.output}`);
  } catch (error) {
    console.error(error.message);
    process.exitCode = 1;
  }
}
