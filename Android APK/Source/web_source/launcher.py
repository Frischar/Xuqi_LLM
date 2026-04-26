import os
import shutil
import socket
import subprocess
import threading
import time
import webbrowser
from contextlib import closing
from pathlib import Path

import uvicorn

from app import BASE_DIR, app


HOST = "127.0.0.1"
PORT = 8000
APP_URL = f"http://{HOST}:{PORT}/chat"
WINDOW_SIZE = "1440,920"


def is_port_open(host: str, port: int) -> bool:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.settimeout(0.4)
        return sock.connect_ex((host, port)) == 0


def wait_for_port(host: str, port: int, timeout_seconds: float = 20.0) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if is_port_open(host, port):
            return True
        time.sleep(0.25)
    return False


def browser_profile_dir() -> Path:
    profile_dir = BASE_DIR / "browser_profile"
    profile_dir.mkdir(parents=True, exist_ok=True)
    return profile_dir


def find_browser_executable() -> str | None:
    candidates = [
        Path(os.environ.get("ProgramFiles(x86)", "")) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
        Path(os.environ.get("ProgramFiles", "")) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
        Path(os.environ.get("ProgramFiles(x86)", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
        Path(os.environ.get("ProgramFiles", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)

    for command_name in ("msedge", "chrome", "chrome.exe"):
        resolved = shutil.which(command_name)
        if resolved:
            return resolved
    return None


def start_local_server() -> tuple[uvicorn.Server, threading.Thread]:
    config = uvicorn.Config(
        app=app,
        host=HOST,
        port=PORT,
        reload=False,
        log_level="warning",
        access_log=False,
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    return server, thread


def launch_app_window(url: str) -> subprocess.Popen[str] | None:
    browser = find_browser_executable()
    if not browser:
        webbrowser.open(url)
        return None

    profile_path = browser_profile_dir()
    command = [
        browser,
        f"--app={url}",
        f"--window-size={WINDOW_SIZE}",
        f"--user-data-dir={profile_path}",
        "--no-first-run",
        "--disable-sync",
        "--disable-extensions",
        "--disable-default-apps",
    ]
    return subprocess.Popen(command)


def main() -> None:
    owns_server = False
    server: uvicorn.Server | None = None
    server_thread: threading.Thread | None = None
    app_process: subprocess.Popen[str] | None = None

    try:
        if not is_port_open(HOST, PORT):
            owns_server = True
            server, server_thread = start_local_server()
            if not wait_for_port(HOST, PORT):
                raise RuntimeError("Local service failed to start in time.")

        app_process = launch_app_window(APP_URL)
        if app_process is None:
            while True:
                time.sleep(1.0)
        else:
            app_process.wait()
    finally:
        if owns_server and server:
            server.should_exit = True
        if owns_server and server_thread:
            server_thread.join(timeout=5.0)


if __name__ == "__main__":
    main()
