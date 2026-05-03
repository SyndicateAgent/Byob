#!/usr/bin/env python3
"""Start BYOB development services on Windows, macOS, or Linux."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
FRONTEND_DIR = PROJECT_ROOT / "frontend"
SUPPORTED_SYSTEMS = {"Windows", "Darwin", "Linux"}
DEFAULT_SERVICES = {"api", "frontend", "worker", "mcp"}


class StartupError(RuntimeError):
    """Raised when a development process cannot be started."""


def parse_args() -> argparse.Namespace:
    """Parse command line options."""

    parser = argparse.ArgumentParser(
        description="Start BYOB API, frontend, Celery worker, and MCP development services."
    )
    parser.add_argument(
        "--services",
        nargs="+",
        choices=sorted(DEFAULT_SERVICES),
        help="Services to start. Default: api frontend worker mcp.",
    )
    parser.add_argument(
        "--backend-only",
        action="store_true",
        help="Start only the FastAPI API. Kept for backward compatibility.",
    )
    parser.add_argument(
        "--frontend-only",
        action="store_true",
        help="Start only the Next.js frontend. Kept for backward compatibility.",
    )
    parser.add_argument(
        "--worker-only",
        action="store_true",
        help="Start only the Celery ingestion worker.",
    )
    parser.add_argument(
        "--mcp-only",
        action="store_true",
        help="Start only the MCP streamable HTTP server.",
    )
    parser.add_argument(
        "--api-host",
        default="127.0.0.1",
        help="Host passed to uvicorn. Default: 127.0.0.1.",
    )
    parser.add_argument(
        "--api-port",
        default="8000",
        help="Port passed to uvicorn. Default: 8000.",
    )
    parser.add_argument(
        "--frontend-port",
        default="3000",
        help="Port passed to Next.js dev server. Default: 3000.",
    )
    parser.add_argument(
        "--mcp-host",
        default="127.0.0.1",
        help="Host passed to the MCP streamable HTTP server. Default: 127.0.0.1.",
    )
    parser.add_argument(
        "--mcp-port",
        default="8010",
        help="Port passed to the MCP streamable HTTP server. Default: 8010.",
    )
    parser.add_argument(
        "--worker-queue",
        default="ingestion",
        help="Celery queue name. Default: ingestion.",
    )
    parser.add_argument(
        "--worker-loglevel",
        default="INFO",
        help="Celery worker log level. Default: INFO.",
    )
    parser.add_argument(
        "--install-frontend",
        action="store_true",
        help="Run npm install before starting the frontend when node_modules is missing.",
    )
    return parser.parse_args()


def selected_services(args: argparse.Namespace) -> set[str]:
    """Return the requested service set."""

    only_flags = {
        "api": args.backend_only,
        "frontend": args.frontend_only,
        "worker": args.worker_only,
        "mcp": args.mcp_only,
    }
    selected_only = [name for name, enabled in only_flags.items() if enabled]
    if len(selected_only) > 1:
        raise StartupError("Use only one *-only flag at a time.")
    if selected_only and args.services is not None:
        raise StartupError("Use either --services or one *-only flag, not both.")
    if selected_only:
        return {selected_only[0]}
    if args.services is not None:
        return set(args.services)
    return set(DEFAULT_SERVICES)


def executable(name: str) -> str:
    """Return an executable path or raise a clear setup error."""

    found = shutil.which(name)
    if found is None:
        raise StartupError(f"Required command not found: {name}")
    return found


def run_checked(command: list[str], cwd: Path) -> None:
    """Run a setup command and stop on failure."""

    print(f"[setup] {' '.join(command)}")
    result = subprocess.run(command, cwd=cwd, check=False)
    if result.returncode != 0:
        raise StartupError(f"Setup command failed with exit code {result.returncode}")


def stream_output(name: str, process: subprocess.Popen[str]) -> None:
    """Print one process stream with a stable prefix."""

    assert process.stdout is not None
    for line in iter(process.stdout.readline, ""):
        print(f"[{name}] {line}", end="")


def start_process(
    name: str,
    command: list[str],
    cwd: Path,
    env: dict[str, str],
) -> subprocess.Popen[str]:
    """Start one long-running development process."""

    print(f"[start] {name}: {' '.join(command)}")
    return subprocess.Popen(
        command,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )


def stop_processes(processes: list[tuple[str, subprocess.Popen[str]]]) -> None:
    """Terminate all running child processes."""

    for name, process in processes:
        if process.poll() is None:
            print(f"[stop] {name}")
            process.terminate()

    deadline = time.time() + 8
    for name, process in processes:
        while process.poll() is None and time.time() < deadline:
            time.sleep(0.1)
        if process.poll() is None:
            print(f"[kill] {name}")
            process.kill()


def main() -> int:
    """Start selected development services and keep them attached."""

    args = parse_args()
    services = selected_services(args)

    system = os.uname().sysname if hasattr(os, "uname") else sys.platform
    platform_name = {
        "win32": "Windows",
        "darwin": "Darwin",
        "linux": "Linux",
    }.get(sys.platform, system)
    if platform_name not in SUPPORTED_SYSTEMS:
        raise StartupError(f"Unsupported system: {platform_name}")

    uv = executable("uv") if services - {"frontend"} else ""
    npm = executable("npm") if "frontend" in services else ""

    if "frontend" in services and not FRONTEND_DIR.exists():
        raise StartupError(f"Frontend directory not found: {FRONTEND_DIR}")
    if "frontend" in services and not (FRONTEND_DIR / "node_modules").exists():
        if args.install_frontend:
            run_checked([npm, "install"], FRONTEND_DIR)
        else:
            raise StartupError(
                "frontend/node_modules is missing. Run 'npm install' in frontend "
                "or start with --install-frontend."
            )

    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("PYTHONUTF8", "1")
    processes: list[tuple[str, subprocess.Popen[str]]] = []

    if "api" in services:
        processes.append(
            (
                "api",
                start_process(
                    "api",
                    [
                        uv,
                        "run",
                        "uvicorn",
                        "api.app.main:app",
                        "--reload",
                        "--host",
                        args.api_host,
                        "--port",
                        args.api_port,
                    ],
                    PROJECT_ROOT,
                    env,
                ),
            )
        )

    if "worker" in services:
        processes.append(
            (
                "worker",
                start_process(
                    "worker",
                    [
                        uv,
                        "run",
                        "celery",
                        "-A",
                        "workers.celery_app.celery_app",
                        "worker",
                        "-Q",
                        args.worker_queue,
                        "--loglevel",
                        args.worker_loglevel,
                    ],
                    PROJECT_ROOT,
                    env,
                ),
            )
        )

    if "mcp" in services:
        processes.append(
            (
                "mcp",
                start_process(
                    "mcp",
                    [
                        uv,
                        "run",
                        "python",
                        "-m",
                        "api.app.mcp_server",
                        "--transport",
                        "streamable-http",
                        "--host",
                        args.mcp_host,
                        "--port",
                        args.mcp_port,
                    ],
                    PROJECT_ROOT,
                    env,
                ),
            )
        )

    if "frontend" in services:
        frontend_env = env.copy()
        frontend_env["PORT"] = str(args.frontend_port)
        processes.append(
            (
                "frontend",
                start_process(
                    "frontend",
                    [npm, "run", "dev", "--", "--port", str(args.frontend_port)],
                    FRONTEND_DIR,
                    frontend_env,
                ),
            )
        )

    for name, process in processes:
        thread = threading.Thread(target=stream_output, args=(name, process), daemon=True)
        thread.start()

    if "api" in services:
        print(f"[ready] API: http://{args.api_host}:{args.api_port}")
    if "frontend" in services:
        print(f"[ready] Frontend: http://localhost:{args.frontend_port}")
    if "worker" in services:
        print(f"[ready] Celery worker: queue={args.worker_queue}")
    if "mcp" in services:
        print(f"[ready] MCP: http://{args.mcp_host}:{args.mcp_port}/mcp")
    print("[hint] Press Ctrl+C to stop all started services.")

    try:
        while True:
            for name, process in processes:
                exit_code = process.poll()
                if exit_code is not None:
                    print(f"[exit] {name} exited with code {exit_code}")
                    stop_processes(processes)
                    return int(exit_code)
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n[stop] Received Ctrl+C")
        stop_processes(processes)
        return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except StartupError as exc:
        print(f"[error] {exc}", file=sys.stderr)
        raise SystemExit(1) from None
