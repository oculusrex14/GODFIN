"use strict";

const { app, BrowserWindow, dialog, net, protocol, session, shell } = require("electron");
const { autoUpdater } = require("electron-updater");
const { existsSync, readFileSync } = require("node:fs");
const { randomBytes } = require("node:crypto");
const http = require("node:http");
const path = require("node:path");
const { spawn } = require("node:child_process");

const BACKEND_PORT = 5100;
const BACKEND_ORIGIN = `http://127.0.0.1:${BACKEND_PORT}`;
const BACKEND_REQUEST_FILTER = { urls: [`${BACKEND_ORIGIN}/*`] };
const LAUNCH_SECRET_HEADER = "X-GODFIN-Launch";
const verificationSecret = process.env.GODFIN_PACKAGE_VERIFICATION_SECRET;
const launchSecret = (
  process.env.GODFIN_PACKAGE_VERIFICATION === "1"
  && typeof verificationSecret === "string"
  && /^[A-Za-z0-9_-]{43,128}$/.test(verificationSecret)
)
  ? verificationSecret
  : randomBytes(32).toString("base64url");
const APP_ORIGIN = "godfin://app";
const UPDATE_ORIGIN = "https://releases.godfin.dev";
const WEBSITE_ORIGINS = new Set([
  "https://godfin.vercel.app",
  "https://godfin.dev",
  "https://accounts.google.com",
  "https://ollama.com",
]);
const CONTENT_SECURITY_POLICY = [
  "default-src 'self'",
  "base-uri 'none'",
  `connect-src 'self' ${BACKEND_ORIGIN}`,
  "font-src 'self' data:",
  "form-action 'none'",
  "frame-ancestors 'none'",
  "img-src 'self' data: blob:",
  "object-src 'none'",
  "script-src 'self'",
  "style-src 'self' 'unsafe-inline'",
].join("; ");

protocol.registerSchemesAsPrivileged([
  {
    scheme: "godfin",
    privileges: {
      standard: true,
      secure: true,
      supportFetchAPI: true,
      corsEnabled: true,
    },
  },
]);

let backendProcess = null;
let mainWindow = null;
let quittingForUpdate = false;

function frontendRoot() {
  return app.isPackaged
    ? path.join(process.resourcesPath, "frontend")
    : path.join(__dirname, "..", "frontend", "dist");
}

function mimeType(filename) {
  const extension = path.extname(filename).toLowerCase();
  return {
    ".css": "text/css; charset=utf-8",
    ".html": "text/html; charset=utf-8",
    ".ico": "image/x-icon",
    ".js": "text/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".webp": "image/webp",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
  }[extension] || "application/octet-stream";
}

function registerAppProtocol() {
  const root = path.resolve(frontendRoot());
  protocol.handle("godfin", (request) => {
    const requestUrl = new URL(request.url);
    const relativePath = decodeURIComponent(requestUrl.pathname).replace(/^\/+/, "");
    let candidate = path.resolve(root, relativePath || "index.html");
    const insideRoot = candidate === root || candidate.startsWith(`${root}${path.sep}`);
    if (!insideRoot) return new Response("Not found", { status: 404 });
    if (!existsSync(candidate) || path.extname(candidate) === "") {
      candidate = path.join(root, "index.html");
    }
    if (!existsSync(candidate)) {
      return new Response("Desktop assets are missing.", { status: 503 });
    }
    return new Response(readFileSync(candidate), {
      headers: {
        "Content-Type": mimeType(candidate),
        "Content-Security-Policy": CONTENT_SECURITY_POLICY,
        "Cross-Origin-Opener-Policy": "same-origin",
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
      },
    });
  });
}

function backendCommand() {
  if (app.isPackaged) {
    const executable = process.platform === "win32"
      ? "godfin-backend.exe"
      : "godfin-backend";
    return {
      command: path.join(
        process.resourcesPath,
        "backend",
        "godfin-backend",
        executable,
      ),
      args: [],
      // All relative writes (including logs and seeded backup settings) must
      // remain outside the signed application bundle.
      cwd: app.getPath("userData"),
    };
  }
  const projectRoot = path.join(__dirname, "..");
  const python = process.platform === "win32"
    ? path.join(projectRoot, "backend", "venv", "Scripts", "python.exe")
    : path.join(projectRoot, "backend", "venv", "bin", "python");
  return {
    command: python,
    args: ["-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", String(BACKEND_PORT)],
    cwd: path.join(projectRoot, "backend"),
  };
}

function backendEnvironment() {
  const userData = app.getPath("userData");
  return {
    ...process.env,
    DB_PATH: path.join(userData, "godfin.db"),
    GODFIN_BACKUP_DIR: path.join(userData, "backups"),
    GODFIN_BACKEND_PORT: String(BACKEND_PORT),
    GODFIN_ENCRYPTION_KEY_FILE: path.join(userData, ".encryption_key"),
    GODFIN_MACHINE_ID_FILE: path.join(userData, ".machine_id"),
    GODFIN_GMAIL_TOKEN_FILE: path.join(userData, "gmail_token.json"),
    GODFIN_GMAIL_CLIENT_SECRETS_FILE: path.join(userData, "client_secret.json"),
    GODFIN_MODEL_CACHE_DIR: path.join(userData, "models"),
    GODFIN_UPDATE_RECOVERY_JOURNAL: path.join(userData, "update-recovery.json"),
    GODFIN_APP_VERSION: app.getVersion(),
    GODFIN_PACKAGED: app.isPackaged ? "1" : "0",
    GODFIN_LAUNCH_SECRET: launchSecret,
    MPLCONFIGDIR: path.join(userData, "matplotlib"),
  };
}

function backendMaintenanceCommand(currentVersion, targetVersion) {
  const argumentsForTransition = [
    "--prepare-update-transition",
    "--current-version",
    currentVersion,
    "--target-version",
    targetVersion,
  ];
  if (app.isPackaged) {
    const launch = backendCommand();
    return { ...launch, args: argumentsForTransition };
  }
  const projectRoot = path.join(__dirname, "..");
  const python = process.platform === "win32"
    ? path.join(projectRoot, "backend", "venv", "Scripts", "python.exe")
    : path.join(projectRoot, "backend", "venv", "bin", "python");
  return {
    command: python,
    args: [path.join(projectRoot, "backend", "desktop_entry.py"), ...argumentsForTransition],
    cwd: path.join(projectRoot, "backend"),
  };
}

function startBackend() {
  if (process.env.GODFIN_SKIP_BACKEND === "1") return;
  const launch = backendCommand();
  if (!existsSync(launch.command)) {
    throw new Error(`Local backend executable was not found: ${launch.command}`);
  }
  backendProcess = spawn(launch.command, launch.args, {
    cwd: launch.cwd,
    env: backendEnvironment(),
    shell: false,
    stdio: app.isPackaged ? "ignore" : "inherit",
    windowsHide: true,
  });
  backendProcess.once("exit", (code, signal) => {
    backendProcess = null;
    if (!quittingForUpdate && !app.isQuitting && code !== 0) {
      dialog.showErrorBox(
        "GODFIN backend stopped",
        `The local finance service exited (${signal || code}). Restart GODFIN to continue.`,
      );
    }
  });
}

function waitForBackend(timeoutMs = 30_000) {
  const startedAt = Date.now();
  return new Promise((resolve, reject) => {
    const check = () => {
      const request = http.get(`${BACKEND_ORIGIN}/api/v1/health`, {
        headers: { [LAUNCH_SECRET_HEADER]: launchSecret },
      }, (response) => {
        response.resume();
        if (response.statusCode === 200) {
          resolve();
        } else if (Date.now() - startedAt >= timeoutMs) {
          reject(new Error(`Backend health returned ${response.statusCode}.`));
        } else {
          setTimeout(check, 250);
        }
      });
      request.setTimeout(1_000);
      request.on("timeout", () => request.destroy());
      request.on("error", () => {
        if (Date.now() - startedAt >= timeoutMs) {
          reject(new Error("The local backend did not start in time."));
        } else {
          setTimeout(check, 250);
        }
      });
    };
    check();
  });
}

function configureBackendRequestTrust() {
  session.defaultSession.webRequest.onBeforeSendHeaders(
    BACKEND_REQUEST_FILTER,
    (details, callback) => {
      callback({
        requestHeaders: {
          ...details.requestHeaders,
          [LAUNCH_SECRET_HEADER]: launchSecret,
        },
      });
    },
  );
}

function isTrustedExternal(rawUrl) {
  try {
    const parsed = new URL(rawUrl);
    return parsed.protocol === "https:" && (
      WEBSITE_ORIGINS.has(parsed.origin) ||
      parsed.hostname.endsWith(".google.com")
    );
  } catch {
    return false;
  }
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 920,
    minWidth: 900,
    minHeight: 640,
    show: false,
    title: "GODFIN",
    backgroundColor: "#0b2344",
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      webSecurity: true,
      devTools: !app.isPackaged,
      spellcheck: false,
    },
  });

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (isTrustedExternal(url)) void shell.openExternal(url);
    return { action: "deny" };
  });
  mainWindow.webContents.on("will-navigate", (event, url) => {
    if (url.startsWith(APP_ORIGIN) || url.startsWith(BACKEND_ORIGIN)) return;
    event.preventDefault();
    if (isTrustedExternal(url)) void shell.openExternal(url);
  });
  mainWindow.once("ready-to-show", () => mainWindow?.show());
  mainWindow.on("closed", () => {
    mainWindow = null;
  });

  const developmentUrl = process.env.GODFIN_DEV_SERVER_URL;
  void mainWindow.loadURL(developmentUrl || `${APP_ORIGIN}/`);
}

function configureUpdater() {
  if (!app.isPackaged || process.env.GODFIN_DISABLE_UPDATES === "1") return;
  const updateOrigin = process.env.GODFIN_UPDATE_ORIGIN || UPDATE_ORIGIN;
  const updateChannel = `${process.platform}-${process.arch}`;
  autoUpdater.setFeedURL({
    provider: "generic",
    url: `${updateOrigin.replace(/\/+$/, "")}/${updateChannel}`,
  });
  autoUpdater.autoDownload = true;
  // A downloaded binary is never installed merely because the app quits. The
  // explicit install path below first creates the verified database recovery
  // state required for both upgrade failure and signed rollback.
  autoUpdater.autoInstallOnAppQuit = false;
  // Release metadata can point to a previously signed immutable version only
  // through the owner-confirmed rollback workflow. Code signing remains the
  // authenticity boundary for every downloaded application.
  autoUpdater.allowDowngrade = true;
  autoUpdater.on("error", (error) => {
    console.error("Auto-update failed", error);
  });
  autoUpdater.on("update-downloaded", (event) => {
    const currentVersion = autoUpdater.currentVersion.version;
    const targetVersion = event.version;
    const isDowngrade = autoUpdater.currentVersion.compare(targetVersion) > 0;
    dialog.showMessageBox(mainWindow, {
      type: isDowngrade ? "warning" : "info",
      title: isDowngrade ? "GODFIN rollback ready" : "GODFIN update ready",
      message: isDowngrade
        ? `Restore the verified ${targetVersion} snapshot and roll back?`
        : `GODFIN ${targetVersion} is ready to install.`,
      detail: isDowngrade
        ? "GODFIN will preserve a safety backup of the current database, then restore the database snapshot made before the newer version was installed. Activity added after that snapshot will not appear while the older version is active."
        : "Before restarting, GODFIN will create and verify a private recovery snapshot. Choosing Later leaves the current version unchanged.",
      buttons: [isDowngrade ? "Restore snapshot and roll back" : "Back up and install", "Later"],
      defaultId: 0,
      cancelId: 1,
    })
      .then(({ response }) => {
        if (response === 0) {
          void installDownloadedUpdate(currentVersion, targetVersion);
        }
      })
      .catch((error) => {
        console.error("Could not display the update prompt", error);
      });
  });
  setTimeout(() => {
    autoUpdater.checkForUpdatesAndNotify().catch(() => {
      // The updater emits a detailed "error" event above. Offline startup is
      // expected and must never surface as an unhandled promise rejection.
    });
  }, 10_000);
}

function stopBackendForUpdate(timeoutMs = 10_000) {
  if (!backendProcess) return Promise.resolve();
  const child = backendProcess;
  return new Promise((resolve, reject) => {
    let timedOut = false;
    const timeout = setTimeout(() => {
      timedOut = true;
      child.kill("SIGKILL");
    }, timeoutMs);
    child.once("exit", () => {
      clearTimeout(timeout);
      if (timedOut) {
        reject(new Error("The local finance service did not stop safely in time."));
      } else {
        resolve();
      }
    });
    child.kill("SIGTERM");
  });
}

function runUpdateMaintenance(currentVersion, targetVersion, timeoutMs = 120_000) {
  const launch = backendMaintenanceCommand(currentVersion, targetVersion);
  return new Promise((resolve, reject) => {
    const child = spawn(launch.command, launch.args, {
      cwd: launch.cwd,
      env: backendEnvironment(),
      shell: false,
      stdio: ["ignore", "pipe", "pipe"],
      windowsHide: true,
    });
    let stdout = "";
    let stderr = "";
    let settled = false;
    child.stdout.on("data", (chunk) => {
      stdout = `${stdout}${chunk}`.slice(-16_384);
    });
    child.stderr.on("data", (chunk) => {
      stderr = `${stderr}${chunk}`.slice(-16_384);
    });
    const timeout = setTimeout(() => child.kill("SIGKILL"), timeoutMs);
    child.once("error", () => {
      if (settled) return;
      settled = true;
      clearTimeout(timeout);
      reject(new Error("The local update recovery tool could not start."));
    });
    child.once("exit", (code) => {
      if (settled) return;
      settled = true;
      clearTimeout(timeout);
      if (code !== 0) {
        console.error("Update recovery preparation failed", stderr);
        reject(new Error("GODFIN could not establish a verified update recovery point."));
        return;
      }
      try {
        const result = JSON.parse(stdout.trim());
        if (!result || !["upgrade", "downgrade"].includes(result.direction)) {
          throw new Error("unknown maintenance result");
        }
        resolve(result);
      } catch {
        reject(new Error("The local update recovery tool returned an invalid result."));
      }
    });
  });
}

async function installDownloadedUpdate(currentVersion, targetVersion) {
  quittingForUpdate = true;
  try {
    await stopBackendForUpdate();
    await runUpdateMaintenance(currentVersion, targetVersion);
    autoUpdater.quitAndInstall();
  } catch (error) {
    quittingForUpdate = false;
    try {
      startBackend();
      await waitForBackend();
    } catch (restartError) {
      console.error("Backend restart after update failure failed", restartError);
    }
    await dialog.showMessageBox(mainWindow, {
      type: "error",
      title: "Update not installed",
      message: error.message,
      detail: "Your current GODFIN version and database were kept active. Try again after checking available disk space and backup permissions.",
      buttons: ["OK"],
    });
  }
}

function stopBackend() {
  if (!backendProcess) return;
  backendProcess.kill("SIGTERM");
  backendProcess = null;
}

if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on("second-instance", () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.focus();
    }
  });

  app.whenReady().then(async () => {
    app.setAppUserModelId("dev.godfin.desktop");
    session.defaultSession.setPermissionRequestHandler((_webContents, _permission, callback) => {
      callback(false);
    });
    configureBackendRequestTrust();
    registerAppProtocol();
    try {
      startBackend();
      await waitForBackend();
      createWindow();
      configureUpdater();
    } catch (error) {
      dialog.showErrorBox("GODFIN could not start", error.message);
      app.quit();
    }
  });
}

app.on("before-quit", () => {
  app.isQuitting = true;
  stopBackend();
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});

app.on("activate", () => {
  if (BrowserWindow.getAllWindows().length === 0) createWindow();
});
