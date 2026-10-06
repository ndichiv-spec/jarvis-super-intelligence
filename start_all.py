#!/usr/bin/env python3
"""
JARVIS Unified Launcher
=======================
Main project root launcher. Starts the unified JARVIS API (with the Silverwing
AI backend mounted) and the JARVIS Next.js frontend together so everything runs
from the JARVIS root.

Usage:
  python start_all.py                # api + jarvis next.js frontend
  python start_all.py --no-frontend  # api only
"""

import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
JARVIS_FRONTEND = ROOT / "frontend" / "web"


class UnifiedLauncher:
    def __init__(self):
        self.processes = {}
        self.commands: dict[str, tuple[list[str], Path]] = {}
        self.restart_attempts: dict[str, int] = {}
        self.next_restart: dict[str, float] = {}
        self.running = True

    def _spawn(self, name, cmd, cwd):
        self.commands[name] = (cmd, cwd)
        proc = subprocess.Popen(
            cmd,
            cwd=str(cwd),
            stdout=None,
            stderr=None,
        )
        self.processes[name] = proc
        return proc

    def start_api(self):
        print("Starting supervised JARVIS backend (independent of frontend) on :8000 ...")
        cmd = [sys.executable, str(ROOT / "scripts" / "supervise_backend.py")]
        self._spawn("api", cmd, ROOT)
        time.sleep(3)
        return self.processes["api"].poll() is None

    def start_jarvis_frontend(self):
        print("Starting JARVIS Next.js frontend ...")
        cwd = JARVIS_FRONTEND
        if not (cwd / "node_modules").exists():
            print("Installing JARVIS frontend dependencies ...")
            npm = ["npm"] if os.name != "nt" else ["npm.cmd"]
            subprocess.run([*npm, "install"], cwd=str(cwd), check=True)
        cmd = ["npm", "run", "dev"]
        if os.name == "nt":
            cmd = ["cmd", "/c", "npm", "run", "dev"]
        self._spawn("jarvis", cmd, cwd)
        time.sleep(5)
        return self.processes["jarvis"].poll() is None

    def monitor(self):
        while self.running:
            now = time.monotonic()
            for name, proc in list(self.processes.items()):
                if proc.poll() is not None:
                    attempt = self.restart_attempts.get(name, 0) + 1
                    self.restart_attempts[name] = attempt
                    delay = min(2 ** min(attempt, 7), 120)
                    if now >= self.next_restart.get(name, 0):
                        print(
                            f"Process {name} stopped unexpectedly; restarting "
                            f"(attempt {attempt})"
                        )
                        cmd, cwd = self.commands[name]
                        self._spawn(name, cmd, cwd)
                        self.next_restart[name] = now + delay
            time.sleep(2)

    def stop_all(self):
        print("Stopping all processes ...")
        for proc in self.processes.values():
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
        self.processes.clear()

    def run(self, start_frontend):
        def _sig(*_):
            self.running = False
            self.stop_all()
            sys.exit(0)

        signal.signal(signal.SIGINT, _sig)
        signal.signal(signal.SIGTERM, _sig)

        api_ok = self.start_api()
        if not api_ok:
            print("Backend supervisor failed to start.")
            self.stop_all()
            return 1
        if start_frontend and not self.start_jarvis_frontend():
            print("Frontend did not start; backend remains available and will be supervised.")

        print("\nJARVIS Unified System is running!")
        print("=" * 56)
        print("Unified API (+ Silverwing backend): http://localhost:8000")
        print("API docs:                          http://localhost:8000/docs")
        print("Silverwing backend (mounted):      http://localhost:8000/silverwing")
        if start_frontend:
            print("JARVIS Next.js frontend:           http://localhost:3000")
        print("Press Ctrl+C to stop all services")
        print("=" * 56)
        try:
            self.monitor()
        except KeyboardInterrupt:
            pass
        finally:
            self.stop_all()
        return 0


def main():
    parser = argparse.ArgumentParser(description="JARVIS Unified Launcher")
    parser.add_argument(
        "--no-frontend",
        action="store_true",
        help="Start only the unified API, not the JARVIS Next.js frontend",
    )
    args = parser.parse_args()
    return UnifiedLauncher().run(start_frontend=not args.no_frontend)


if __name__ == "__main__":
    sys.exit(main())
