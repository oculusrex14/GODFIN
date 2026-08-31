import { createHash } from "node:crypto";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { bundle } from "@remotion/bundler";
import { renderStill, selectComposition } from "@remotion/renderer";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const temporary = await mkdtemp(path.join(os.tmpdir(), "godfin-remotion-smoke-"));
const serveUrl = await bundle({
  entryPoint: path.join(root, "src/index.ts"),
  publicDir: path.join(root, "public"),
});
const samples = [
  { id: "GodfinBetaHero16x9", frame: 270, width: 480, height: 270 },
  { id: "GodfinDemoWalkthrough16x9", frame: 810, width: 480, height: 270 },
  { id: "GodfinBetaSocial9x16", frame: 270, width: 270, height: 480 },
];

try {
  for (const sample of samples) {
    const output = path.join(temporary, `${sample.id}.png`);
    await renderStill({
      composition: await selectComposition({ serveUrl, id: sample.id, inputProps: {} }),
      serveUrl,
      output,
      frame: sample.frame,
      imageFormat: "png",
      scale: 0.25,
      overwrite: true,
      logLevel: "warn",
    });
    const bytes = await readFile(output);
    if (
      bytes.length < 1024 ||
      bytes.toString("hex", 0, 8) !== "89504e470d0a1a0a" ||
      bytes.readUInt32BE(16) !== sample.width ||
      bytes.readUInt32BE(20) !== sample.height
    ) {
      throw new Error(`${sample.id} smoke render is missing or has invalid dimensions.`);
    }
    process.stdout.write(
      `${sample.id} ${sample.width}x${sample.height} ${createHash("sha256").update(bytes).digest("hex")}\n`,
    );
  }
} finally {
  await rm(temporary, { recursive: true, force: true });
}
