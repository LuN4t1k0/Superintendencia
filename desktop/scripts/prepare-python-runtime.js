const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");

const desktopRoot = path.resolve(__dirname, "..");
const projectRoot = path.resolve(desktopRoot, "..");
const runtimeDir = path.join(desktopRoot, "python-runtime");
const browsersDir = path.join(desktopRoot, "ms-playwright");
const isWindows = process.platform === "win32";
const embedVersion = process.env.PYTHON_EMBED_VERSION || "3.12.10";

function run(command, args, options = {}) {
  console.log(`$ ${[command, ...args].join(" ")}`);
  const result = spawnSync(command, args, {
    stdio: "inherit",
    shell: isWindows,
    ...options
  });

  if (result.status !== 0) {
    process.exit(result.status || 1);
  }
}

function pythonFromRuntime() {
  if (!isWindows) {
    return path.join(runtimeDir, "bin", "python");
  }

  const candidates = [
    path.join(runtimeDir, "python.exe"),
    path.join(runtimeDir, "Scripts", "python.exe")
  ];

  return candidates.find((candidate) => fs.existsSync(candidate)) || candidates[0];
}

const sourcePython = process.env.PYTHON_BIN || (isWindows ? "python" : "python3");

fs.rmSync(runtimeDir, { recursive: true, force: true });
fs.rmSync(browsersDir, { recursive: true, force: true });

if (isWindows) {
  const downloadDir = path.join(desktopRoot, ".runtime-downloads");
  const embedZip = path.join(downloadDir, `python-${embedVersion}-embed-amd64.zip`);
  const getPipPath = path.join(downloadDir, "get-pip.py");
  const embedUrl = `https://www.python.org/ftp/python/${embedVersion}/python-${embedVersion}-embed-amd64.zip`;

  fs.mkdirSync(downloadDir, { recursive: true });
  run("powershell", [
    "-NoProfile",
    "-ExecutionPolicy",
    "Bypass",
    "-Command",
    `Invoke-WebRequest -Uri '${embedUrl}' -OutFile '${embedZip}'`
  ]);
  fs.mkdirSync(runtimeDir, { recursive: true });
  run("powershell", [
    "-NoProfile",
    "-ExecutionPolicy",
    "Bypass",
    "-Command",
    `Expand-Archive -Path '${embedZip}' -DestinationPath '${runtimeDir}' -Force`
  ]);

  const pthFile = path.join(runtimeDir, `python${embedVersion.split(".").slice(0, 2).join("")}._pth`);
  if (fs.existsSync(pthFile)) {
    const pth = fs.readFileSync(pthFile, "utf8")
      .replace(/^#import site$/m, "import site");
    const lines = pth.split(/\r?\n/);
    if (!lines.includes("Lib\\site-packages")) {
      lines.splice(Math.max(lines.findIndex((line) => line === "import site"), 0), 0, "Lib\\site-packages");
    }
    fs.writeFileSync(pthFile, lines.join("\r\n"));
  }

  run("powershell", [
    "-NoProfile",
    "-ExecutionPolicy",
    "Bypass",
    "-Command",
    `Invoke-WebRequest -Uri 'https://bootstrap.pypa.io/get-pip.py' -OutFile '${getPipPath}'`
  ]);
  run(pythonFromRuntime(), [getPipPath, "--no-warn-script-location"]);
  fs.rmSync(downloadDir, { recursive: true, force: true });
} else {
  run(sourcePython, ["-m", "venv", runtimeDir]);
}

const runtimePython = pythonFromRuntime();
run(runtimePython, ["-m", "pip", "install", "--upgrade", "pip"]);
run(runtimePython, ["-m", "pip", "install", "-r", path.join(projectRoot, "desktop_backend", "requirements.txt")]);
run(runtimePython, ["-m", "playwright", "install", "chromium"], {
  env: {
    ...process.env,
    PLAYWRIGHT_BROWSERS_PATH: browsersDir
  }
});

console.log(`Runtime listo: ${runtimeDir}`);
console.log(`Playwright listo: ${browsersDir}`);
