"""
Starts the API server, the main frontend dev server, and the admin app
dev server together -- a bare-host alternative to docker-compose for
local development. One Ctrl+C stops all three cleanly.

Usage:
    uv run python dev_up.py
    uv run python dev_up.py --admin-path ../book_rag_admin
    uv run python dev_up.py --skip-admin       (just the API + main frontend)
    uv run python dev_up.py --skip-frontend    (just the API + admin app)
"""

import argparse
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

IS_WINDOWS = os.name == "nt"
PROJECT_ROOT = Path(__file__).resolve().parent

# ANSI colors to tell each service's output apart when all three are
# interleaved in one terminal. Falls back gracefully either way -- even
# without color support, the "[api]"/"[frontend]"/"[admin]" text prefix
# alone is enough to tell streams apart.
COLORS = {"api": "\033[36m", "frontend": "\033[35m", "admin": "\033[33m"}
RESET = "\033[0m"


class Service:
    def __init__(self, name, cmd, cwd):
        self.name = name
        self.cmd = cmd
        self.cwd = Path(cwd)
        self.process = None

    def start(self) -> bool:
        if not self.cwd.exists():
            print(f"[{self.name}] SKIPPED -- directory not found: {self.cwd}")
            return False

        print(f"[{self.name}] starting: {' '.join(self.cmd)}  (in {self.cwd})")
        self.process = subprocess.Popen(
            self.cmd,
            cwd=str(self.cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            # shell=True on Windows specifically: npm resolves to npm.cmd,
            # not a directly-executable binary, and cmd.exe is what knows
            # how to find it. Harmless on POSIX too since each command
            # here is a single trusted, hardcoded list, not user input.
            shell=IS_WINDOWS,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if IS_WINDOWS else 0,
        )
        threading.Thread(target=self._stream_output, daemon=True).start()
        return True

    def _stream_output(self):
        prefix = f"{COLORS.get(self.name, '')}[{self.name}]{RESET}"
        for line in self.process.stdout:
            print(f"{prefix} {line.rstrip()}")

    def is_alive(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def stop(self):
        if self.process is None or self.process.poll() is not None:
            return
        print(f"[{self.name}] stopping (pid {self.process.pid})...")
        try:
            if IS_WINDOWS:
                # taskkill /T kills the whole process tree. This matters
                # specifically because npm/vite spawn child node
                # processes -- terminating just the npm.cmd process and
                # not its children is a common way to end up with an
                # orphaned node process still holding the dev server's
                # port open after the script exits.
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(self.process.pid)],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
            else:
                self.process.terminate()
                self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.process.kill()
        except Exception as e:
            print(f"[{self.name}] error while stopping: {e}")


def check_tool(name: str):
    if shutil.which(name) is None:
        print(f"WARNING: '{name}' not found on PATH -- services needing it will fail to start.")


def main():
    parser = argparse.ArgumentParser(description="Start the API, main frontend, and admin app together.")
    parser.add_argument(
        "--admin-path",
        default=str(PROJECT_ROOT / "admin_app"),
        help="Path to the admin app folder (default: ./admin_app, inside this project)",
    )
    parser.add_argument("--skip-admin", action="store_true", help="Don't start the admin app")
    parser.add_argument("--skip-frontend", action="store_true", help="Don't start the main frontend")
    args = parser.parse_args()

    check_tool("uv")
    check_tool("npm")

    npm_cmd = "npm.cmd" if IS_WINDOWS else "npm"

    services = [Service("api", ["uv", "run", "python", "server.py"], PROJECT_ROOT)]
    if not args.skip_frontend:
        services.append(Service("frontend", [npm_cmd, "run", "dev"], PROJECT_ROOT / "frontend"))
    if not args.skip_admin:
        services.append(Service("admin", [npm_cmd, "run", "dev"], args.admin_path))

    started = [s for s in services if s.start()]
    if not started:
        print("Nothing started -- check the paths above.")
        return

    print("\nAll services starting. Press Ctrl+C to stop everything.\n")

    try:
        while True:
            time.sleep(1)
            # If one process dies on its own (a real crash, not Ctrl+C),
            # stop everything else too -- a frontend left running against
            # a dead API is more confusing than just stopping cleanly.
            for s in started:
                if not s.is_alive():
                    print(f"\n[{s.name}] exited unexpectedly (code {s.process.returncode}) "
                          f"-- stopping everything else.")
                    raise KeyboardInterrupt
    except KeyboardInterrupt:
        print("\nStopping all services...")
    finally:
        for s in started:
            try:
                s.stop()
            except KeyboardInterrupt:
                # A second interrupt arriving mid-cleanup (impatient
                # double Ctrl+C) must not abandon the loop -- every
                # remaining service still needs its stop() attempted, or
                # whichever ones come after this one in `started` would
                # be left running.
                print(f"[{s.name}] interrupted again while stopping -- continuing cleanup anyway")
                continue
        print("Done.")


if __name__ == "__main__":
    main()