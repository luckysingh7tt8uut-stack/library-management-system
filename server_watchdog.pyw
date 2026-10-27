"""
server_watchdog.pyw - keeps the Library Management System running invisibly.

Run with pythonw.exe (no console window ever appears). It:

  1. Exits immediately if the app is already healthy on 127.0.0.1:8501
     (so starting it twice never creates a duplicate server).
  2. Starts Streamlit hidden on 127.0.0.1:8501 (port pinned in
     .streamlit/config.toml).
  3. Stays resident and restarts Streamlit whenever it dies:
       - if the process exits, it restarts within ~2 seconds;
       - if the server merely stops answering the health check (busy,
         warming up), it waits for UNHEALTHY_STRIKES consecutive failures
         (~6+ seconds) before restarting - a slow response during a
         browser page load never causes a pointless restart.
  4. Appends a short status line to server.log next to this file.

Disable it any time with "Disable Auto Start.bat".
"""

import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
LOG_FILE = APP_DIR / "server.log"

HOST = "127.0.0.1"
PORT = 8501
HEALTH_URL = "http://{}:{}/_stcore/health".format(HOST, PORT)

HEALTHY = "ok"

RESTART_DELAY = 2            # seconds between supervision checks
HEALTH_TIMEOUT = 5           # seconds before a health request counts as failed
HEALTH_POLL = 0.5            # seconds between health checks while booting
HEALTH_TIMEOUT_WAIT = 60     # seconds to wait for a fresh server to become healthy
UNHEALTHY_STRIKES = 3        # failed health checks (process alive) before restart
MAX_START_ATTEMPTS = 5       # consecutive failed boots before backing off longer
BACKOFF_AFTER_FAILURES = 30  # extra seconds once repeated starts fail


def log(message):
    """Append one timestamped line to server.log (never raises)."""
    line = "[{}] {}".format(datetime.now().strftime("%Y-%m-%d %H:%M:%S"), message)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except OSError:
        pass


def is_healthy():
    """True when the app on PORT answers the Streamlit health check."""
    try:
        with urllib.request.urlopen(HEALTH_URL, timeout=HEALTH_TIMEOUT) as response:
            return response.read().decode("utf-8", "replace").strip() == HEALTHY
    except (urllib.error.URLError, OSError):
        return False


def port_is_occupied():
    """True when *something* listens on PORT (our server or a foreign program)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1)
        return sock.connect_ex((HOST, PORT)) == 0


def spawn_server():
    """Start Streamlit hidden and return the new process."""
    # config.toml already pins address 127.0.0.1, port 8501 and headless=true,
    # so no extra command-line flags are needed.
    return subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", str(APP_DIR / "app.py")],
        cwd=str(APP_DIR),
        creationflags=subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def wait_until_healthy(process, timeout=HEALTH_TIMEOUT_WAIT):
    """Poll the health endpoint until healthy, the process dies, or timeout."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if is_healthy():
            return True
        if process.poll() is not None:
            return False
        time.sleep(HEALTH_POLL)
    return False


def stop_quietly(process):
    """Make sure a dead/stuck server process is fully gone."""
    try:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=10)
    except OSError:
        pass


def supervise(process):
    """Watch a healthy server; return when it must be restarted.

    A crashed process (poll() != None) triggers a restart within
    RESTART_DELAY seconds. A process that is merely not answering health
    checks gets UNHEALTHY_STRIKES chances first, so a busy server during a
    page load is never restarted needlessly.
    """
    strikes = 0
    while True:
        time.sleep(RESTART_DELAY)
        if process.poll() is not None:
            log("server process exited (code {})".format(process.returncode))
            return
        if is_healthy():
            strikes = 0
            continue
        strikes += 1
        if strikes >= UNHEALTHY_STRIKES:
            log("server alive but unhealthy for {} checks - restarting".format(strikes))
            return
    # unreachable


def main():
    log("watchdog started (pid {})".format(__import__("os").getpid()))

    # Already running (started earlier or by the launcher) -> do nothing.
    if is_healthy():
        log("server already healthy on port {}; nothing to do".format(PORT))
        return

    failed_starts = 0
    busy_warned = False
    while True:
        if port_is_occupied():
            # Something owns the port but does not answer the health check:
            # a foreign program, or a half-dead Streamlit from a crash.
            if is_healthy():
                log("server became healthy; watchdog exiting")
                return
            if not busy_warned:
                log("port {} is held by another process - waiting for it. "
                    "Run 'Start Library Manager.bat' to reclaim it now."
                    .format(PORT))
                busy_warned = True
            time.sleep(RESTART_DELAY)
            continue
        busy_warned = False

        process = spawn_server()
        log("started streamlit (pid {})".format(process.pid))

        if wait_until_healthy(process):
            failed_starts = 0
            log("server healthy on http://{}:{}".format(HOST, PORT))
            supervise(process)
            log("server stopped unexpectedly - restarting")
            stop_quietly(process)
            continue

        # The server never became healthy in time.
        failed_starts += 1
        exit_code = process.poll()
        if exit_code is None:
            stop_quietly(process)
            exit_code = "killed"
        log("server failed to start (exit={})".format(exit_code))

        if failed_starts >= MAX_START_ATTEMPTS:
            log("backing off {}s after {} failed starts".format(
                BACKOFF_AFTER_FAILURES, failed_starts))
            time.sleep(BACKOFF_AFTER_FAILURES)
        else:
            time.sleep(RESTART_DELAY)


if __name__ == "__main__":
    while True:
        try:
            main()
        except Exception as exc:  # last-resort: keep the watchdog alive
            log("watchdog error: {!r}".format(exc))
            time.sleep(RESTART_DELAY)
        else:
            break  # main() returned cleanly (server was already healthy)
