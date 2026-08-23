import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { spawnSync } from "node:child_process";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

const desktopRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const projectRoot = path.resolve(desktopRoot, "..");
const frontendRoot = path.join(projectRoot, "frontend");
const backendRoot = path.join(projectRoot, "backend");
const localPython = process.platform === "win32"
  ? path.join(backendRoot, "venv", "Scripts", "python.exe")
  : path.join(backendRoot, "venv", "bin", "python");
const python = process.env.PYTHON_BIN || (existsSync(localPython) ? localPython : "python");
const npm = process.platform === "win32" ? "npm.cmd" : "npm";

function gitSha() {
  const result = spawnSync("git", ["rev-parse", "HEAD"], {
    cwd: projectRoot,
    encoding: "utf8",
    shell: false,
  });
  const candidate = String(result.stdout || "").trim().toLowerCase();
  return /^[0-9a-f]{40}$/.test(candidate) ? candidate : "unknown";
}

const packageJson = JSON.parse(
  readFileSync(path.join(desktopRoot, "package.json"), "utf8"),
);
const identity = {
  version: packageJson.version,
  full_sha: process.env.GODFIN_BUILD_SHA || gitSha(),
  channel: process.env.GODFIN_BUILD_CHANNEL || "private-local",
  built_at_utc: process.env.GODFIN_BUILD_TIMESTAMP || new Date().toISOString(),
};
const identityDir = path.join(backendRoot, "build");
mkdirSync(identityDir, { recursive: true });
writeFileSync(
  path.join(identityDir, "build-identity.json"),
  `${JSON.stringify(identity, null, 2)}\n`,
  { encoding: "utf8", mode: 0o600 },
);

function run(command, args, cwd) {
  const result = spawnSync(command, args, {
    cwd,
    env: process.env,
    stdio: "inherit",
    shell: false,
  });
  if (result.error) {
    throw new Error(
      `Could not start ${command}: ${result.error.message}. ` +
      "Create backend/venv with Python 3.12 and install requirements-build-lock.txt.",
    );
  }
  if (result.status !== 0) {
    throw new Error(
      `${command} ${args.join(" ")} failed with exit code ${result.status ?? "unknown"}.`,
    );
  }
}

run(npm, ["run", "build"], frontendRoot);
run(
  python,
  [
    "-m",
    "PyInstaller",
    "--clean",
    "--noconfirm",
    "--distpath",
    path.join(backendRoot, "dist"),
    "--workpath",
    path.join(backendRoot, "build", "pyinstaller"),
    path.join(backendRoot, "godfin-backend.spec"),
  ],
  backendRoot,
);
