import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { spawn } from "node:child_process";
import { readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const output = path.resolve(root, "../public/video");

const expected = [
  { file: "godfin-beta-hero.mp4", width: 1920, height: 1080, duration: 24, codec: "h264" },
  { file: "godfin-beta-hero.webm", width: 1920, height: 1080, duration: 24, codec: "vp9" },
  { file: "godfin-demo-walkthrough.mp4", width: 1920, height: 1080, duration: 54, codec: "h264" },
  { file: "godfin-demo-walkthrough.webm", width: 1920, height: 1080, duration: 54, codec: "vp9" },
  { file: "godfin-beta-social.mp4", width: 1080, height: 1920, duration: 18, codec: "h264" },
];

async function capture(command, args) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, { stdio: ["ignore", "pipe", "pipe"] });
    const stdout = [];
    const stderr = [];
    child.stdout.on("data", (chunk) => stdout.push(chunk));
    child.stderr.on("data", (chunk) => stderr.push(chunk));
    child.on("error", reject);
    child.on("exit", (code) => code === 0
      ? resolve(Buffer.concat(stdout))
      : reject(new Error(`${command} failed: ${Buffer.concat(stderr).toString("utf8")}`)));
  });
}

const updateManifest = process.argv.includes("--update-manifest");
const report = {
  schema_version: 2,
  frame_hash_format: "rawvideo:yuv420p",
  files: [],
};
for (const item of expected) {
  const source = path.join(output, item.file);
  const probe = JSON.parse((await capture("ffprobe", ["-v", "error", "-show_streams", "-show_format", "-of", "json", source])).toString("utf8"));
  const video = probe.streams.find((stream) => stream.codec_type === "video");
  const audio = probe.streams.find((stream) => stream.codec_type === "audio");
  if (!video || audio) throw new Error(`${item.file} must contain one video stream and no audio stream.`);
  if (video.width !== item.width || video.height !== item.height) throw new Error(`${item.file} dimensions are wrong.`);
  if (video.codec_name !== item.codec || video.pix_fmt !== "yuv420p") throw new Error(`${item.file} codec or pixel format is wrong.`);
  if (video.sample_aspect_ratio && video.sample_aspect_ratio !== "1:1") throw new Error(`${item.file} sample aspect ratio is wrong.`);
  if (Math.abs(Number(probe.format.duration) - item.duration) > 0.08) throw new Error(`${item.file} duration is wrong.`);
  if (video.avg_frame_rate !== "30/1") throw new Error(`${item.file} frame rate is wrong.`);
  await capture("ffmpeg", ["-v", "error", "-xerror", "-i", source, "-f", "null", "-"]);

  const frameHashes = [];
  for (const percent of [0, 20, 50, 80, 99]) {
    const timestamp = Math.max(0, item.duration * percent / 100 - (percent === 99 ? 0.05 : 0));
    const frame = await capture("ffmpeg", [
      "-v",
      "error",
      "-ss",
      timestamp.toFixed(3),
      "-i",
      source,
      "-frames:v",
      "1",
      "-pix_fmt",
      "yuv420p",
      "-f",
      "rawvideo",
      "-",
    ]);
    frameHashes.push({ percent, sha256: createHash("sha256").update(frame).digest("hex") });
  }
  const bytes = await readFile(source);
  report.files.push({
    ...item,
    bytes: bytes.length,
    sha256: createHash("sha256").update(bytes).digest("hex"),
    frame_hashes: frameHashes,
  });
}

for (const base of ["godfin-beta-hero", "godfin-demo-walkthrough"]) {
  const poster = await readFile(path.join(output, `${base}.poster.webp`));
  report.files.push({ file: `${base}.poster.webp`, bytes: poster.length, sha256: createHash("sha256").update(poster).digest("hex") });
}

const manifestPath = path.join(output, "render-verification.json");
if (updateManifest) {
  const updated = {
    schema_version: report.schema_version,
    verified_at: new Date().toISOString(),
    frame_hash_format: report.frame_hash_format,
    files: report.files,
  };
  await writeFile(manifestPath, `${JSON.stringify(updated, null, 2)}\n`, "utf8");
} else {
  const recorded = JSON.parse(await readFile(manifestPath, "utf8"));
  assert.equal(recorded.schema_version, report.schema_version);
  assert.equal(recorded.frame_hash_format, report.frame_hash_format);
  assert.deepEqual(
    recorded.files,
    report.files,
    "Committed media no longer matches its deterministic verification manifest.",
  );
}
console.log(
  updateManifest
    ? `Verified ${expected.length} silent media files and 2 WebP posters; updated the manifest explicitly.`
    : `Verified ${expected.length} silent media files and 2 WebP posters without modifying the manifest.`,
);
