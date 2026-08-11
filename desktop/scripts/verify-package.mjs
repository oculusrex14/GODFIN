import {
  access,
  mkdtemp,
  readdir,
  rm,
  stat,
} from "node:fs/promises";
import { constants } from "node:fs";
import { randomBytes } from "node:crypto";
import { spawn, spawnSync } from "node:child_process";
import { tmpdir } from "node:os";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

import { assertPackagePrivacy } from "./package-privacy.mjs";
import { assertPackageIntegrity } from "./package-integrity.mjs";

const desktopRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const projectRoot = path.resolve(desktopRoot, "..");
const releaseRoot = path.resolve(
  process.env.GODFIN_PACKAGE_DIR || path.join(desktopRoot, "release"),
);
const budgets = JSON.parse(
  await import("node:fs/promises").then(({ readFile }) =>
    readFile(path.join(projectRoot, "performance", "budgets.json"), "utf8")
  ),
);

function effectiveLimit(name) {
  const budget = budgets.budgets[name];
  const regressionLimit = budget.accepted_baseline * (1 + budgets.regression_margin);
  return Math.min(budget.absolute_max, regressionLimit);
}

async function walk(directory) {
  const entries = await readdir(directory, { withFileTypes: true });
  const results = [];
  for (const entry of entries) {
    const candidate = path.join(directory, entry.name);
    if (entry.isDirectory()) {
      results.push(...await walk(candidate));
    } else {
      results.push(candidate);
    }
  }
  return results;
}

async function locatePackage() {
  const files = await walk(releaseRoot);
  if (process.platform === "darwin") {
    const executable = files.find((file) =>
      file.endsWith(`${path.sep}GODFIN.app${path.sep}Contents${path.sep}MacOS${path.sep}GODFIN`)
    );
    if (executable) {
      return {
        executable,
        fuseTarget: executable.slice(0, executable.indexOf(".app") + 4),
      };
    }
  }
  if (process.platform === "win32") {
    const executable = files.find((file) =>
      file.toLowerCase().endsWith(`${path.sep}win-unpacked${path.sep}godfin.exe`)
    );
    if (executable) return { executable, fuseTarget: executable };
  }
  if (process.platform === "linux") {
    const unpacked = files.filter((file) => file.includes(`${path.sep}linux-unpacked${path.sep}`));
    for (const executable of unpacked) {
      try {
        await access(executable, constants.X_OK);
        if (!path.extname(executable)) return { executable, fuseTarget: executable };
      } catch {
        // Continue looking for the Electron executable.
      }
    }
  }
  throw new Error(`No unpacked GODFIN application was found under ${releaseRoot}.`);
}

function runCheck(command, args, message) {
  const result = spawnSync(command, args, {
    cwd: desktopRoot,
    encoding: "utf8",
    shell: false,
  });
  if (result.error || result.status !== 0) {
    throw new Error(
      `${message}\n${result.error?.message || result.stderr || result.stdout}`.trim(),
    );
  }
  return `${result.stdout || ""}${result.stderr || ""}`;
}

function verifySignature(target) {
  const requireSigning = process.env.GODFIN_REQUIRE_SIGNING === "1";
  if (process.platform === "darwin") {
    runCheck(
      "codesign",
      ["--verify", "--deep", "--strict", "--verbose=2", target],
      "The macOS application signature is invalid.",
    );
    if (requireSigning) {
      const details = runCheck(
        "codesign",
        ["-dv", "--verbose=4", target],
        "The macOS signing identity could not be read.",
      );
      if (!details.includes("Authority=Developer ID Application:")) {
        throw new Error("A Developer ID Application signature is required for release artifacts.");
      }
    }
  }
  if (process.platform === "win32" && requireSigning) {
    const script = [
      "$signature = Get-AuthenticodeSignature -FilePath",
      `'${target.replaceAll("'", "''")}'`,
      "; if ($signature.Status -ne 'Valid') {",
      "Write-Error \"Authenticode status: $($signature.Status)\"; exit 1 }",
    ].join(" ");
    runCheck(
      "powershell.exe",
      ["-NoProfile", "-NonInteractive", "-Command", script],
      "The Windows Authenticode signature is invalid.",
    );
  }
}

function verifyFuses(target) {
  const binary = path.join(
    desktopRoot,
    "node_modules",
    ".bin",
    process.platform === "win32" ? "electron-fuses.cmd" : "electron-fuses",
  );
  const output = runCheck(
    binary,
    ["read", "--app", target],
    "Electron fuse inspection failed.",
  );
  const required = [
    "RunAsNode is Disabled",
    "EnableCookieEncryption is Enabled",
    "EnableNodeOptionsEnvironmentVariable is Disabled",
    "EnableNodeCliInspectArguments is Disabled",
    "EnableEmbeddedAsarIntegrityValidation is Enabled",
    "OnlyLoadAppFromAsar is Enabled",
  ];
  const missing = required.filter((line) => !output.includes(line));
  if (missing.length) {
    throw new Error(`Required Electron fuses are missing: ${missing.join(", ")}`);
  }
}

function processRows() {
  if (process.platform === "win32") {
    const script = [
      "Get-CimInstance Win32_Process |",
      "Select-Object ProcessId,ParentProcessId,WorkingSetSize,Name |",
      "ConvertTo-Json -Compress",
    ].join(" ");
    const output = runCheck(
      "powershell.exe",
      ["-NoProfile", "-NonInteractive", "-Command", script],
      "Could not inspect packaged process memory.",
    );
    const parsed = JSON.parse(output);
    return (Array.isArray(parsed) ? parsed : [parsed]).map((row) => ({
      pid: Number(row.ProcessId),
      ppid: Number(row.ParentProcessId),
      rssKb: Number(row.WorkingSetSize) / 1024,
      command: row.Name,
    }));
  }

  const output = runCheck(
    "ps",
    ["-axo", "pid=,ppid=,rss=,command="],
    "Could not inspect packaged process memory.",
  );
  return output
    .trim()
    .split("\n")
    .map((line) => {
      const match = line.trim().match(/^(\d+)\s+(\d+)\s+(\d+)\s+(.+)$/);
      return match
        ? {
            pid: Number(match[1]),
            ppid: Number(match[2]),
            rssKb: Number(match[3]),
            command: match[4],
          }
        : null;
    })
    .filter(Boolean);
}

function processTree(rootPid) {
  const rows = processRows();
  const ids = new Set([rootPid]);
  let added = true;
  while (added) {
    added = false;
    for (const row of rows) {
      if (ids.has(row.ppid) && !ids.has(row.pid)) {
        ids.add(row.pid);
        added = true;
      }
    }
  }
  return rows.filter((row) => ids.has(row.pid));
}

async function portIsFree() {
  try {
    await fetch("http://127.0.0.1:5100/api/v1/health");
    return false;
  } catch {
    return true;
  }
}

async function terminateTree(child, tree) {
  if (process.platform === "win32") {
    spawnSync("taskkill.exe", ["/PID", String(child.pid), "/T", "/F"], {
      stdio: "ignore",
      shell: false,
    });
    return;
  }
  child.kill("SIGTERM");
  await new Promise((resolve) => setTimeout(resolve, 1_500));
  for (const row of [...tree].reverse()) {
    try {
      process.kill(row.pid, "SIGTERM");
    } catch {
      // The process already exited.
    }
  }
}

async function launchOnce(executable, userData) {
  const startedAt = performance.now();
  const launchSecret = randomBytes(32).toString("base64url");
  const child = spawn(executable, [`--user-data-dir=${userData}`], {
    cwd: path.dirname(executable),
    env: {
      ...process.env,
      GODFIN_DISABLE_KEYCHAIN: "1",
      GODFIN_DISABLE_UPDATES: "1",
      GODFIN_PACKAGE_VERIFICATION: "1",
      GODFIN_PACKAGE_VERIFICATION_SECRET: launchSecret,
    },
    stdio: "ignore",
    shell: false,
  });

  let healthResponse;
  while (performance.now() - startedAt < effectiveLimit("cold_start_ms")) {
    if (child.exitCode !== null) {
      throw new Error(`The packaged desktop process exited with code ${child.exitCode}.`);
    }
    try {
      healthResponse = await fetch("http://127.0.0.1:5100/api/v1/health", {
        headers: { "X-GODFIN-Launch": launchSecret },
      });
      if (healthResponse.ok) break;
    } catch {
      // The local backend is still starting.
    }
    await new Promise((resolve) => setTimeout(resolve, 100));
  }

  const startupMs = Math.round(performance.now() - startedAt);
  if (!healthResponse?.ok) {
    child.kill("SIGTERM");
    throw new Error(
      `Packaged startup exceeded ${effectiveLimit("cold_start_ms")} ms (observed ${startupMs} ms).`,
    );
  }

  const missingTrust = await fetch("http://127.0.0.1:5100/api/v1/health");
  const developmentOrigin = await fetch("http://127.0.0.1:5100/api/v1/health", {
    headers: {
      "Origin": "http://localhost:5200",
      "X-GODFIN-Launch": launchSecret,
    },
  });
  if (missingTrust.status !== 403 || developmentOrigin.status !== 403) {
    await terminateTree(child, processTree(child.pid));
    throw new Error("The packaged local API trust boundary is not enforced.");
  }

  await new Promise((resolve) => setTimeout(resolve, 1_500));
  const tree = processTree(child.pid);
  const memoryMb = tree.reduce((total, row) => total + row.rssKb, 0) / 1024;
  await terminateTree(child, tree);
  return {
    startupMs,
    memoryMb,
    processCount: tree.length,
    trustBoundaryEnforced: true,
  };
}

if (!await portIsFree()) {
  throw new Error("Port 5100 is already in use; stop the running GODFIN backend first.");
}

const packaged = await locatePackage();
const packageFiles = await walk(releaseRoot);
await assertPackagePrivacy(packageFiles);
await assertPackageIntegrity(packageFiles, { projectRoot });
verifySignature(packaged.fuseTarget);
verifyFuses(packaged.fuseTarget);

const userData = await mkdtemp(path.join(tmpdir(), "godfin-package-smoke-"));
try {
  const first = await launchOnce(packaged.executable, userData);
  const database = path.join(userData, "godfin.db");
  const firstDatabase = await stat(database);
  if (firstDatabase.size === 0) throw new Error("The packaged database is empty after startup.");

  const second = await launchOnce(packaged.executable, userData);
  const secondDatabase = await stat(database);
  if (secondDatabase.size === 0) throw new Error("The packaged database was not preserved.");
  verifySignature(packaged.fuseTarget);
  verifyFuses(packaged.fuseTarget);

  const maxMemoryMb = Math.max(first.memoryMb, second.memoryMb);
  if (maxMemoryMb > effectiveLimit("idle_combined_memory_mb")) {
    throw new Error(
      `Idle memory exceeded ${effectiveLimit("idle_combined_memory_mb")} MB ` +
      `(observed ${maxMemoryMb.toFixed(1)} MB).`,
    );
  }

  console.log(JSON.stringify({
    package: packaged.fuseTarget,
    first_start_ms: first.startupMs,
    restart_ms: second.startupMs,
    max_idle_memory_mb: Number(maxMemoryMb.toFixed(1)),
    process_count: Math.max(first.processCount, second.processCount),
    database_preserved: secondDatabase.size > 0,
    trust_boundary_enforced: first.trustBoundaryEnforced && second.trustBoundaryEnforced,
  }, null, 2));
} finally {
  await rm(userData, { recursive: true, force: true });
}
