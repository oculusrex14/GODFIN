import { spawn } from "node:child_process";
import { mkdir, rm } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { bundle } from "@remotion/bundler";
import { renderMedia, renderStill, selectComposition } from "@remotion/renderer";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(scriptDir, "..");
const output = path.resolve(root, "../public/video");
const temporary = path.join(root, ".render-tmp");
await mkdir(output, { recursive: true });
await mkdir(temporary, { recursive: true });

const serveUrl = await bundle({
  entryPoint: path.join(root, "src/index.ts"),
  publicDir: path.join(root, "public"),
});

async function composition(id) {
  return selectComposition({ serveUrl, id, inputProps: {} });
}

async function run(command, args) {
  await new Promise((resolve, reject) => {
    const child = spawn(command, args, { stdio: "inherit" });
    child.on("error", reject);
    child.on("exit", (code) => code === 0 ? resolve() : reject(new Error(`${command} exited ${code}`)));
  });
}

async function renderVideo({ id, name, codec, crf }) {
  const selected = await composition(id);
  const extension = codec === "vp9" ? "webm" : "mp4";
  const raw = path.join(temporary, `${name}.raw.${extension}`);
  const destination = path.join(output, `${name}.${extension}`);
  let lastProgress = -1;
  await renderMedia({
    composition: selected,
    serveUrl,
    codec,
    crf,
    outputLocation: raw,
    overwrite: true,
    muted: true,
    enforceAudioTrack: false,
    pixelFormat: "yuv420p",
    colorSpace: "bt709",
    x264Preset: codec === "h264" ? "medium" : null,
    concurrency: 2,
    logLevel: "warn",
    envVariables: { SOURCE_DATE_EPOCH: "1788048000" },
    metadata: {},
    onProgress: ({ progress }) => {
      const percent = Math.floor(progress * 10) * 10;
      if (percent !== lastProgress) {
        lastProgress = percent;
        process.stdout.write(`${name} ${percent}%\n`);
      }
    },
  });
  const metadataArgs = [
    "-y", "-i", raw,
    "-map_metadata", "-1",
    "-fflags", "+bitexact",
    "-flags:v", "+bitexact",
    "-metadata", "encoder=",
    "-metadata", "comment=",
    "-metadata:s:v:0", "encoder=",
    "-metadata:s:v:0", "handler_name=",
    "-c", "copy",
  ];
  if (codec === "h264") metadataArgs.push("-movflags", "+faststart");
  metadataArgs.push(destination);
  await run("ffmpeg", metadataArgs);
  await rm(raw, { force: true });
}

async function poster({ id, name, frame }) {
  await renderStill({
    composition: await composition(id),
    serveUrl,
    output: path.join(output, `${name}.poster.webp`),
    frame,
    imageFormat: "webp",
    overwrite: true,
    logLevel: "warn",
  });
}

await renderVideo({ id: "GodfinBetaHero16x9", name: "godfin-beta-hero", codec: "h264", crf: 18 });
await renderVideo({ id: "GodfinBetaHero16x9", name: "godfin-beta-hero", codec: "vp9", crf: 28 });
await poster({ id: "GodfinBetaHero16x9", name: "godfin-beta-hero", frame: 270 });
await renderVideo({ id: "GodfinDemoWalkthrough16x9", name: "godfin-demo-walkthrough", codec: "h264", crf: 18 });
await renderVideo({ id: "GodfinDemoWalkthrough16x9", name: "godfin-demo-walkthrough", codec: "vp9", crf: 28 });
await poster({ id: "GodfinDemoWalkthrough16x9", name: "godfin-demo-walkthrough", frame: 570 });
await renderVideo({ id: "GodfinBetaSocial9x16", name: "godfin-beta-social", codec: "h264", crf: 18 });

console.log(`Rendered GODFIN media to ${output}`);
