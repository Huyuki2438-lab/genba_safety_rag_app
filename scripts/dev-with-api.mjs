import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { join } from "node:path";

const isWin = process.platform === "win32";
const npmCmd = isWin ? "npm.cmd" : "npm";
const venvPython = isWin
  ? join(process.cwd(), ".venv", "Scripts", "python.exe")
  : join(process.cwd(), ".venv", "bin", "python");
const defaultPython = existsSync(venvPython) ? venvPython : (isWin ? "python" : "python3");
const pythonCmd = process.env.PYTHON_BIN || defaultPython;

const backendHost = process.env.BACKEND_HOST || "127.0.0.1";
const backendPort = process.env.BACKEND_PORT || "8000";
const backendApp = process.env.BACKEND_APP || "main:app";
const backendOrigin =
  process.env.VITE_BACKEND_ORIGIN || `http://${backendHost}:${backendPort}`;
const backendReload = process.env.BACKEND_RELOAD === "1";

let shuttingDown = false;

const backend = spawn(
  pythonCmd,
  [
    "-m",
    "uvicorn",
    backendApp,
    "--host",
    backendHost,
    "--port",
    backendPort,
    ...(backendReload ? ["--reload"] : [])
  ],
  {
    stdio: "inherit",
    env: process.env
  }
);

const frontendCommand = isWin ? "cmd.exe" : npmCmd;
const frontendArgs = isWin
  ? ["/d", "/s", "/c", `${npmCmd} run dev:frontend`]
  : ["run", "dev:frontend"];

const frontend = spawn(frontendCommand, frontendArgs, {
  stdio: "inherit",
  env: {
    ...process.env,
    VITE_BACKEND_ORIGIN: backendOrigin
  }
});

const stopChild = (child) => {
  if (!child || child.killed) return;
  child.kill("SIGTERM");
};

const shutdown = (exitCode = 0) => {
  if (shuttingDown) return;
  shuttingDown = true;
  stopChild(frontend);
  stopChild(backend);
  setTimeout(() => process.exit(exitCode), 250);
};

backend.on("exit", (code) => {
  if (!shuttingDown) {
    console.error(`backend exited with code ${code ?? 0}`);
    shutdown(code ?? 1);
  }
});

frontend.on("exit", (code) => {
  if (!shuttingDown) {
    console.error(`frontend exited with code ${code ?? 0}`);
    shutdown(code ?? 1);
  }
});

process.on("SIGINT", () => shutdown(0));
process.on("SIGTERM", () => shutdown(0));
