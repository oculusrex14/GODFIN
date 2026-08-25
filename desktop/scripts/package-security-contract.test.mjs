import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const main = readFileSync(path.join(here, "..", "main.cjs"), "utf8");
const afterPack = readFileSync(path.join(here, "after-pack.cjs"), "utf8");
const buildAssets = readFileSync(path.join(here, "build-assets.mjs"), "utf8");
const verifyPackage = readFileSync(path.join(here, "verify-package.mjs"), "utf8");
const pkg = JSON.parse(readFileSync(path.join(here, "..", "package.json"), "utf8"));

test("updates require separate download and install consent", () => {
  assert.match(main, /autoUpdater\.autoDownload = false/);
  assert.match(main, /autoUpdater\.autoInstallOnAppQuit = false/);
  assert.match(main, /autoUpdater\.on\("update-available"/);
  assert.match(main, /autoUpdater\.downloadUpdate\(\)/);
  assert.match(main, /autoUpdater\.on\("update-downloaded"/);
  assert.doesNotMatch(main, /checkForUpdatesAndNotify/);
});

test("downgrades require an explicit signed-rollback owner switch", () => {
  assert.match(
    main,
    /autoUpdater\.allowDowngrade = process\.env\.GODFIN_ALLOW_SIGNED_ROLLBACK === "1"/,
  );
});

test("backup restore is main-frame-only, one-at-a-time, and token-bound", () => {
  assert.match(main, /event\.senderFrame === mainWindow\.webContents\.mainFrame/);
  assert.match(main, /!isTrustedRendererEvent\(event\)/);
  assert.match(main, /\|\| backendMaintenanceInProgress/);
  assert.match(main, /\^\[A-Za-z0-9_-\]\{40,128\}\$/);
  assert.doesNotMatch(main, /senderUrl\.startsWith/);
});

test("local mac packaging cannot emit an unsigned distributable installer", () => {
  assert.match(pkg.scripts["dist:mac:local"], /--dir/);
  assert.doesNotMatch(pkg.scripts["dist:mac"], /notarize=false|identity=-/);
});

test("fuse hardening resolves the platform-specific packaged executable", () => {
  assert.match(afterPack, /context\.electronPlatformName/);
  assert.match(afterPack, /platform === "linux"/);
  assert.match(afterPack, /context\.packager\.executableName/);
  assert.match(afterPack, /context\.packager\.appInfo\.productFilename/);
  assert.match(verifyPackage, /linux-unpacked\$\{path\.sep\}godfin-desktop/);
  assert.doesNotMatch(verifyPackage, /constants\.X_OK/);
  assert.match(buildAssets, /process\.platform === "win32" && command\.endsWith\("\.cmd"\)/);
  assert.match(buildAssets, /shell: requiresWindowsShell/);
  assert.match(verifyPackage, /process\.platform === "win32" && command\.endsWith\("\.cmd"\)/);
  assert.match(verifyPackage, /shell: requiresWindowsShell/);
  assert.match(verifyPackage, /\/proc\/\$\{pid\}\/smaps_rollup/);
  assert.match(verifyPackage, /\^Pss:\\s\+\(\\d\+\)\\s\+kB\$/m);
  assert.match(verifyPackage, /child\.once\("exit", finish\)/);
  assert.match(verifyPackage, /maxRetries: 10/);
  assert.match(verifyPackage, /retryDelay: 250/);
  assert.match(verifyPackage, /setTimeout\(resolve, 20\)/);
  assert.match(verifyPackage, /async function waitForPortRelease\(timeoutMs = 5_000\)/);
  assert.match(verifyPackage, /if \(await portIsFree\(\)\) return/);
  assert.match(verifyPackage, /await waitForPortRelease\(\)/);
  assert.match(verifyPackage, /const coldStartLimitMs = effectiveLimit\("cold_start_ms"\)/);
  assert.match(verifyPackage, /const restartLimitMs = budgets\.budgets\.cold_start_ms\.absolute_max/);
  assert.match(
    verifyPackage,
    /launchOnce\(packaged\.executable, userData, coldStartLimitMs\)/,
  );
  assert.match(
    verifyPackage,
    /launchOnce\(packaged\.executable, userData, restartLimitMs\)/,
  );
});

test("initial backend startup overlaps Electron readiness without exposing the renderer", () => {
  const initialBackendStart = main.indexOf("const initialBackendReady");
  const electronReady = main.indexOf('app.whenReady().then');
  assert.ok(initialBackendStart > 0);
  assert.ok(electronReady > initialBackendStart);
  assert.match(
    main.slice(initialBackendStart, electronReady),
    /startBackend\(\);[\s\S]*await waitForBackend\(\);/,
  );
  assert.match(
    main.slice(electronReady),
    /configureBackendRequestTrust\(\);[\s\S]*await initialBackendReady;[\s\S]*createWindow\(\);/,
  );
});
