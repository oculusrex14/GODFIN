import assert from "node:assert/strict";
import {
  mkdir,
  mkdtemp,
  rm,
  symlink,
  writeFile,
} from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";

import { assertPackagePrivacy } from "./package-privacy.mjs";

test("accepts synthetic application assets", async () => {
  const directory = await mkdtemp(path.join(tmpdir(), "godfin-privacy-"));
  try {
    const asset = path.join(directory, "app.asar");
    await writeFile(asset, "synthetic account 0000");
    const assetsDirectory = path.join(directory, "assets");
    const assetsLink = path.join(directory, "assets-link");
    await mkdir(assetsDirectory);
    await symlink(assetsDirectory, assetsLink);
    await assertPackagePrivacy([asset, assetsLink], {
      forbiddenMarkers: ["9876"],
    });
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});

test("rejects databases, statements, credentials and private markers", async () => {
  const directory = await mkdtemp(path.join(tmpdir(), "godfin-privacy-"));
  try {
    const database = path.join(directory, "godfin.db");
    await writeFile(database, "local data");
    await assert.rejects(
      assertPackagePrivacy([database]),
      /forbidden data file/,
    );

    const binary = path.join(directory, "app.asar");
    await writeFile(binary, "embedded private marker 9876");
    await assert.rejects(
      assertPackagePrivacy([binary], { forbiddenMarkers: ["9876"] }),
      /private account marker/,
    );
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});
