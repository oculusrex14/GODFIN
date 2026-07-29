"use strict";

const { app, BrowserWindow, dialog, net, protocol, session, shell } = require("electron");
const { autoUpdater } = require("electron-updater");
const { existsSync, readFileSync } = require("node:fs");
const http = require("node:http");
const path = require("node:path");
const { spawn } = require("node:child_process");

const BACKEND_PORT = 5100;
const BACKEND_ORIGIN = `http://127.0.0.1:${BACKEND_PORT}`;
const APP_ORIGIN = "godfin://app";
const UPDATE_ORIGIN = "https://releases.godfin.dev";
const WEBSITE_ORIGINS = new Set([
  "https://godfin.dev",
  "https://accounts.google.com",
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
    GODFIN_PACKAGED: app.isPackaged ? "1" : "0",
    MPLCONFIGDIR: path.join(userData, "matplotlib"),
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
      const request = http.get(`${BACKEND_ORIGIN}/api/v1/health`, (response) => {
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
  autoUpdater.autoInstallOnAppQuit = true;
  // Release metadata can point to a previously signed immutable version only
  // through the owner-confirmed rollback workflow. Code signing remains the
  // authenticity boundary for every downloaded application.
  autoUpdater.allowDowngrade = true;
  autoUpdater.on("error", (error) => {
    console.error("Auto-update failed", error);
  });
  autoUpdater.on("update-downloaded", () => {
    dialog.showMessageBox(mainWindow, {
      type: "info",
      title: "GODFIN update ready",
      message: "A signed GODFIN update is ready to install.",
      detail: "Restart now to install it, or it will install when you next quit.",
      buttons: ["Restart and install", "Later"],
      defaultId: 0,
      cancelId: 1,
    })
      .then(({ response }) => {
        if (response === 0) {
          quittingForUpdate = true;
          autoUpdater.quitAndInstall();
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
