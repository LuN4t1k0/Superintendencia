const crypto = require("crypto");
const fs = require("fs");
const os = require("os");
const path = require("path");
const { spawn } = require("child_process");
const { app, BrowserWindow, dialog, ipcMain, shell } = require("electron");
const { autoUpdater } = require("electron-updater");

function loadBuildConfig() {
  try {
    return JSON.parse(fs.readFileSync(path.join(__dirname, "config.generated.json"), "utf8"));
  } catch {
    return {};
  }
}

const buildConfig = loadBuildConfig();
const APP_ID = process.env.APP_ID || buildConfig.appId || "afp-lookup";
const LICENSE_SERVER_URL = process.env.LICENSE_SERVER_URL || buildConfig.licenseServerUrl || "";
const LICENSE_OFFLINE_GRACE_DAYS = Number(
  process.env.LICENSE_OFFLINE_GRACE_DAYS || buildConfig.licenseOfflineGraceDays || "7"
);
const DEV_SERVER_URL = process.env.VITE_DEV_SERVER_URL || "http://127.0.0.1:5173";

let mainWindow;
let workerProcess;
let cancelRequested = false;
let autoUpdateInterval;

function getDeviceId() {
  const source = [
    os.hostname(),
    os.userInfo().username,
    os.platform(),
    os.arch()
  ].join(":");

  return crypto.createHash("sha256").update(source).digest("hex");
}

function getLicensePath() {
  return path.join(app.getPath("userData"), "license.json");
}

function readStoredLicense() {
  try {
    return JSON.parse(fs.readFileSync(getLicensePath(), "utf8"));
  } catch {
    return null;
  }
}

function writeStoredLicense(data) {
  fs.mkdirSync(app.getPath("userData"), { recursive: true });
  fs.writeFileSync(getLicensePath(), JSON.stringify(data, null, 2));
}

function isWithinOfflineGrace(license) {
  if (!license?.lastValidatedAt) {
    return false;
  }

  const lastValidatedAt = new Date(license.lastValidatedAt).getTime();
  const graceMs = LICENSE_OFFLINE_GRACE_DAYS * 24 * 60 * 60 * 1000;
  return Number.isFinite(lastValidatedAt) && Date.now() - lastValidatedAt <= graceMs;
}

async function validateLicense(token) {
  if (!LICENSE_SERVER_URL) {
    if (app.isPackaged) {
      throw new Error("LICENSE_SERVER_URL no esta configurado para validar licencias.");
    }

    return {
      ok: true,
      mode: "dev",
      message: "Validacion de licencia omitida porque LICENSE_SERVER_URL no esta configurado."
    };
  }

  const response = await fetch(`${LICENSE_SERVER_URL.replace(/\/$/, "")}/licenses/validate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      appId: APP_ID,
      token,
      deviceId: getDeviceId(),
      appVersion: app.getVersion(),
      platform: process.platform
    })
  });

  if (!response.ok) {
    throw new Error(`Servidor de licencias respondio ${response.status}`);
  }

  const payload = await response.json();
  if (!payload.valid) {
    throw new Error(payload.message || "Licencia no autorizada para este equipo.");
  }

  return payload;
}

async function hasValidLicense() {
  const stored = readStoredLicense();
  if (!stored?.token) {
    return false;
  }

  try {
    const validation = await validateLicense(stored.token);
    writeStoredLicense({
      ...stored,
      lastValidatedAt: new Date().toISOString(),
      validation
    });
    return true;
  } catch (error) {
    return isWithinOfflineGrace(stored);
  }
}

function appRoot() {
  if (app.isPackaged) {
    return path.join(process.resourcesPath, "app");
  }
  return path.resolve(__dirname, "..", "..");
}

function workerPath() {
  return path.join(appRoot(), "desktop_backend", "worker.py");
}

function resolveExecutable(command) {
  if (!command || path.isAbsolute(command)) {
    return command;
  }

  const candidates = [
    path.resolve(process.cwd(), command),
    path.resolve(__dirname, "..", command),
    path.resolve(appRoot(), command)
  ];

  return candidates.find((candidate) => fs.existsSync(candidate)) || command;
}

function pythonCommand() {
  if (process.env.PYTHON_BIN) {
    return resolveExecutable(process.env.PYTHON_BIN);
  }

  if (app.isPackaged) {
    const runtimeRoot = path.join(process.resourcesPath, "python-runtime");
    const bundledPython = process.platform === "win32"
      ? path.join(runtimeRoot, "Scripts", "python.exe")
      : path.join(runtimeRoot, "bin", "python");

    if (fs.existsSync(bundledPython)) {
      return bundledPython;
    }
  }

  return process.platform === "win32" ? "python" : "python3";
}

function backendEnv() {
  const env = { ...process.env };
  if (app.isPackaged) {
    const browsersPath = path.join(process.resourcesPath, "ms-playwright");
    if (fs.existsSync(browsersPath)) {
      env.PLAYWRIGHT_BROWSERS_PATH = browsersPath;
    }
  }
  return env;
}

function createWindow() {
  if (mainWindow && !mainWindow.isDestroyed()) {
    return;
  }

  mainWindow = new BrowserWindow({
    width: 1180,
    height: 820,
    minWidth: 960,
    minHeight: 700,
    title: "AFP Lookup",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false
    }
  });

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: "deny" };
  });
}

async function showActivation() {
  createWindow();
  await mainWindow.loadFile(path.join(__dirname, "activation.html"));
}

async function showApp() {
  createWindow();
  if (app.isPackaged) {
    await mainWindow.loadFile(path.join(__dirname, "..", "dist-ui", "index.html"));
  } else {
    await mainWindow.loadURL(DEV_SERVER_URL);
  }

  setupAutoUpdates();
}

function setupAutoUpdates() {
  if (!app.isPackaged || autoUpdateInterval) {
    return;
  }

  autoUpdater.autoDownload = true;
  autoUpdater.autoInstallOnAppQuit = true;

  autoUpdater.on("error", (error) => {
    console.error("autoUpdater error:", error);
  });

  autoUpdater.checkForUpdatesAndNotify().catch((error) => {
    console.error("No se pudo revisar actualizaciones:", error);
  });

  autoUpdateInterval = setInterval(() => {
    autoUpdater.checkForUpdatesAndNotify().catch((error) => {
      console.error("No se pudo revisar actualizaciones:", error);
    });
  }, 4 * 60 * 60 * 1000);
}

ipcMain.handle("license:activate", async (_event, token) => {
  const cleanToken = String(token || "").trim();
  if (!cleanToken) {
    return { ok: false, message: "Ingresa una licencia valida." };
  }

  try {
    const validation = await validateLicense(cleanToken);
    writeStoredLicense({
      token: cleanToken,
      deviceId: getDeviceId(),
      lastValidatedAt: new Date().toISOString(),
      validation
    });

    await showApp();
    return { ok: true };
  } catch (error) {
    return { ok: false, message: error.message };
  }
});

app.whenReady().then(async () => {
  try {
    if (await hasValidLicense()) {
      await showApp();
    } else {
      await showActivation();
    }
  } catch (error) {
    dialog.showErrorBox("AFP Lookup", error.message);
    app.quit();
  }
});

ipcMain.handle("file:select", async () => {
  const result = await dialog.showOpenDialog(mainWindow, {
    title: "Selecciona el Excel con RUTs",
    properties: ["openFile"],
    filters: [{ name: "Excel", extensions: ["xlsx"] }]
  });

  if (result.canceled || result.filePaths.length === 0) {
    return null;
  }

  return result.filePaths[0];
});

ipcMain.handle("file:saveResult", async (_event, sourcePath) => {
  if (!sourcePath || !fs.existsSync(sourcePath)) {
    return { ok: false, message: "No hay resultado disponible para guardar." };
  }

  const result = await dialog.showSaveDialog(mainWindow, {
    title: "Guardar resultado",
    defaultPath: "resultado_afp.xlsx",
    filters: [{ name: "Excel", extensions: ["xlsx"] }]
  });

  if (result.canceled || !result.filePath) {
    return { ok: false, canceled: true };
  }

  fs.copyFileSync(sourcePath, result.filePath);
  return { ok: true, filePath: result.filePath };
});

ipcMain.handle("process:start", async (_event, options) => {
  if (workerProcess) {
    return { ok: false, message: "Ya hay un proceso en ejecucion." };
  }
  cancelRequested = false;

  const inputPath = options?.inputPath;
  if (!inputPath || !fs.existsSync(inputPath)) {
    return { ok: false, message: "Selecciona un archivo Excel valido." };
  }

  const outputPath = path.join(
    app.getPath("temp"),
    `afp-lookup-${Date.now()}-${crypto.randomBytes(4).toString("hex")}.xlsx`
  );

  const args = [
    workerPath(),
    "--input",
    inputPath,
    "--output",
    outputPath,
    "--batch-size",
    String(options.batchSize || 3),
    "--pause-seconds",
    String(options.pauseSeconds ?? 1.5)
  ];

  const python = pythonCommand();
  if (python.includes(path.sep) && !fs.existsSync(python)) {
    return {
      ok: false,
      message: `No se encontro Python en ${python}. Define PYTHON_BIN con una ruta valida.`
    };
  }

  workerProcess = spawn(python, args, {
    cwd: appRoot(),
    env: backendEnv(),
    windowsHide: true
  });

  workerProcess.on("error", (error) => {
    workerProcess = null;
    mainWindow.webContents.send("process:event", {
      type: "error",
      message: `No se pudo iniciar Python: ${error.message}`
    });
  });

  workerProcess.stdout.setEncoding("utf8");
  workerProcess.stderr.setEncoding("utf8");

  let buffer = "";
  workerProcess.stdout.on("data", (chunk) => {
    buffer += chunk;
    const lines = buffer.split(/\r?\n/);
    buffer = lines.pop() || "";
    for (const line of lines) {
      if (!line.trim()) {
        continue;
      }
      try {
        mainWindow.webContents.send("process:event", JSON.parse(line));
      } catch {
        mainWindow.webContents.send("process:event", { type: "log", message: line });
      }
    }
  });

  workerProcess.stderr.on("data", (chunk) => {
    mainWindow.webContents.send("process:event", {
      type: "log",
      level: "error",
      message: chunk.trim()
    });
  });

  workerProcess.on("exit", (code) => {
    workerProcess = null;
    if (cancelRequested) {
      mainWindow.webContents.send("process:event", {
        type: "canceled",
        code,
        outputPath
      });
      cancelRequested = false;
      return;
    }

    mainWindow.webContents.send("process:event", {
      type: "exit",
      code,
      outputPath
    });
  });

  return { ok: true, outputPath };
});

ipcMain.handle("process:cancel", async () => {
  if (!workerProcess) {
    return { ok: true };
  }

  cancelRequested = true;
  workerProcess.kill();
  return { ok: true };
});

app.on("before-quit", () => {
  if (autoUpdateInterval) {
    clearInterval(autoUpdateInterval);
  }
  if (workerProcess) {
    workerProcess.kill();
  }
});

app.on("window-all-closed", () => {
  app.quit();
});
