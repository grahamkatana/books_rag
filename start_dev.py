"""
Starts the API server, the main frontend dev server, the admin app dev
server, and the verify app dev server together -- a bare-host
alternative to docker-compose for local development. One Ctrl+C stops
all four cleanly. Opens a browser tab for each frontend automatically,
once its dev server is actually ready to respond (not just "probably
started by now").

Before starting each service, this also clears anything already
listening on its target port. That matters more than it might look
like: if a previous run wasn't shut down cleanly -- the terminal closed
directly instead of Ctrl+C, a crash, anything other than this script's
own stop() -- the old process keeps running and keeps answering
requests with whatever code it had loaded back then. A route that's
genuinely in your source can still 404 in the browser if an old, stale
server process is the one actually receiving the request. Pre-clearing
the port removes that entire failure mode rather than relying on every
shutdown having gone cleanly.

Usage:
    uv run python dev_up.py
    uv run python dev_up.py --admin-path ../book_rag_admin
    uv run python dev_up.py --verify-path ../book_rag_verify
    uv run python dev_up.py --skip-admin       (skip just the admin app)
    uv run python dev_up.py --skip-verify       (skip just the verify app)
    uv run python dev_up.py --skip-frontend    (skip just the main frontend)
    uv run python dev_up.py --no-browser       (don't open any browser tabs)
    uv run python dev_up.py --no-kill-stale    (don't pre-clear ports -- if something
                                                 else legitimately needs to be on one of them)
"""

import argparse
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

IS_WINDOWS = os.name == "nt"
PROJECT_ROOT = Path(__file__).resolve().parent

# ANSI colors to tell each service's output apart when all four are
# interleaved in one terminal. Falls back gracefully either way -- even
# without color support, the "[api]"/"[frontend]"/"[admin]"/"[verify]"
# text prefix alone is enough to tell streams apart.
COLORS = {"api": "\033[36m", "frontend": "\033[35m", "admin": "\033[33m", "verify": "\033[32m"}
RESET = "\033[0m"


def wait_for_url(url: str, timeout: float = 20, interval: float = 0.3) -> bool:
    """Polls a URL until it responds (any response at all -- even a 404
    means the server is up) or timeout elapses. Used to open a browser
    tab only once a dev server is genuinely ready, instead of guessing a
    fixed delay that's too short on a slow machine or wastes time on a
    fast one."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(url, timeout=1)
            return True
        except Exception:
            time.sleep(interval)
    return False


def find_pids_on_port(port: int) -> list[int]:
    """Finds every process ID currently LISTENING on this port. Only
    LISTENING, not TIME_WAIT or other transient states -- a TIME_WAIT
    entry on Windows reports PID 0, which isn't a real, killable
    process, and killing whatever else might transiently own a closing
    connection on this port (rather than the actual listener) would be
    pointless at best. Best-effort throughout: if netstat/lsof aren't
    available or parsing fails for any reason, this returns an empty
    list and the caller just proceeds exactly as it always did before
    this existed -- a new service that fails to bind a genuinely
    occupied port still fails with its own clear "address in use" error,
    no worse off than before."""
    pids = set()
    try:
        if IS_WINDOWS:
            output = subprocess.run(
                ["netstat", "-ano"], capture_output=True, text=True, shell=True
            ).stdout
            for line in output.splitlines():
                parts = line.split()
                if len(parts) >= 5 and parts[0] in ("TCP", "TCP6") and parts[3] == "LISTENING":
                    local_addr = parts[1]  # e.g. "0.0.0.0:8000" or "[::]:8000"
                    if local_addr.rsplit(":", 1)[-1] == str(port):
                        pid_str = parts[-1]
                        if pid_str.isdigit() and int(pid_str) != 0:
                            pids.add(int(pid_str))
        else:
            output = subprocess.run(
                ["lsof", "-t", "-i", f":{port}", "-sTCP:LISTEN"], capture_output=True, text=True
            ).stdout
            for line in output.splitlines():
                if line.strip().isdigit():
                    pids.add(int(line.strip()))
    except Exception:
        pass
    return list(pids)


def kill_stale_port(port: int, label: str):
    """Kills anything already listening on this port before a new
    service tries to bind it. See the module docstring for why this
    exists -- in short, a previous run's process that wasn't shut down
    cleanly can sit there indefinitely, silently serving stale code."""
    pids = find_pids_on_port(port)
    if not pids:
        return
    print(f"[{label}] port {port} is already in use by PID(s) {pids} -- stopping them first")
    for pid in pids:
        try:
            if IS_WINDOWS:
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(pid)],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
            else:
                os.kill(pid, 9)
        except Exception as e:
            print(f"[{label}] couldn't stop PID {pid}: {e}")
    time.sleep(1)  # give the OS a moment to actually release the port before the new process tries to bind it


class Service:
    def __init__(self, name, cmd, cwd, url=None, port=None):
        self.name = name
        self.cmd = cmd
        self.cwd = Path(cwd)
        self.url = url  # if set, dev_up.py will open this in a browser once it's ready
        self.port = port  # if set, dev_up.py will clear anything already bound to it before starting
        self.process = None

    def start(self, kill_stale: bool = True) -> bool:
        if not self.cwd.exists():
            print(f"[{self.name}] SKIPPED -- directory not found: {self.cwd}")
            return False

        if kill_stale and self.port is not None:
            kill_stale_port(self.port, self.name)

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

    def open_browser_when_ready(self):
        if not self.url:
            return
        if wait_for_url(self.url):
            opened = webbrowser.open(self.url)
            if opened:
                print(f"[{self.name}] opened {self.url} in your browser")
            else:
                print(f"[{self.name}] ready at {self.url} -- couldn't open a browser automatically, open it yourself")
        else:
            print(f"[{self.name}] gave up waiting for {self.url} to come up -- open it manually once it's ready")

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
    parser = argparse.ArgumentParser(description="Start the API, main frontend, admin app, and verify app together.")
    parser.add_argument(
        "--admin-path",
        default=str(PROJECT_ROOT / "admin_app"),
        help="Path to the admin app folder (default: ./admin_app, inside this project)",
    )
    parser.add_argument(
        "--verify-path",
        default=str(PROJECT_ROOT / "verify_app"),
        help="Path to the verify app folder (default: ./verify_app, inside this project)",
    )
    parser.add_argument("--skip-admin", action="store_true", help="Don't start the admin app")
    parser.add_argument("--skip-verify", action="store_true", help="Don't start the verify app")
    parser.add_argument("--skip-frontend", action="store_true", help="Don't start the main frontend")
    parser.add_argument("--no-browser", action="store_true", help="Don't open any browser tabs automatically")
    parser.add_argument("--no-kill-stale", action="store_true",
                         help="Don't pre-clear target ports -- skip this if something else legitimately needs to be on one of them")
    parser.add_argument("--api-port", type=int, default=8000, help="API server's port")
    parser.add_argument("--frontend-port", type=int, default=5173, help="Main frontend's dev server port")
    parser.add_argument("--admin-port", type=int, default=5174, help="Admin app's dev server port")
    parser.add_argument("--verify-port", type=int, default=5175, help="Verify app's dev server port")
    args = parser.parse_args()

    check_tool("uv")
    check_tool("npm")

    npm_cmd = "npm.cmd" if IS_WINDOWS else "npm"
    kill_stale = not args.no_kill_stale

    services = [Service(
        "api", ["uv", "run", "python", "server.py", "--port", str(args.api_port)], PROJECT_ROOT,
        port=args.api_port,
    )]
    if not args.skip_frontend:
        services.append(Service(
            "frontend", [npm_cmd, "run", "dev"], PROJECT_ROOT / "frontend",
            url=None if args.no_browser else f"http://localhost:{args.frontend_port}",
            port=args.frontend_port,
        ))
    if not args.skip_admin:
        services.append(Service(
            "admin", [npm_cmd, "run", "dev"], args.admin_path,
            url=None if args.no_browser else f"http://localhost:{args.admin_port}",
            port=args.admin_port,
        ))
    if not args.skip_verify:
        services.append(Service(
            "verify", [npm_cmd, "run", "dev"], args.verify_path,
            url=None if args.no_browser else f"http://localhost:{args.verify_port}",
            port=args.verify_port,
        ))

    started = [s for s in services if s.start(kill_stale=kill_stale)]
    if not started:
        print("Nothing started -- check the paths above.")
        return

    for s in started:
        if s.url:
            threading.Thread(target=s.open_browser_when_ready, daemon=True).start()

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