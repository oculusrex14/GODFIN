import { existsSync } from "node:fs";
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
