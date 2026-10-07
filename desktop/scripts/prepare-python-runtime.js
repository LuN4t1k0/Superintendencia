const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");

const desktopRoot = path.resolve(__dirname, "..");
const projectRoot = path.resolve(desktopRoot, "..");
const runtimeDir = path.join(desktopRoot, "python-runtime");
const browsersDir = path.join(desktopRoot, "ms-playwright");
const isWindows = process.platform === "win32";

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
  return isWindows
    ? path.join(runtimeDir, "Scripts", "python.exe")
    : path.join(runtimeDir, "bin", "python");
}

const sourcePython = process.env.PYTHON_BIN || (isWindows ? "python" : "python3");

fs.rmSync(runtimeDir, { recursive: true, force: true });
fs.rmSync(browsersDir, { recursive: true, force: true });

run(sourcePython, ["-m", "venv", runtimeDir]);

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
