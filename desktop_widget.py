from __future__ import annotations

import atexit
import subprocess
import sys
import time
from pathlib import Path

import requests
import webview  # type: ignore[import-not-found]

BASE_DIR = Path(__file__).resolve().parent
HOST = "127.0.0.1"
PORT = "8765"
URL = f"http://{HOST}:{PORT}/"


def _start_server() -> subprocess.Popen[str]:
    cmd = [
        sys.executable,
        "manage.py",
        "runserver",
        f"{HOST}:{PORT}",
        "--noreload",
    ]
    return subprocess.Popen(cmd, cwd=str(BASE_DIR))


def _wait_for_server(timeout_seconds: int = 30) -> None:
    started_at = time.time()
    while (time.time() - started_at) < timeout_seconds:
        try:
            response = requests.get(URL, timeout=2)
            if response.status_code < 500:
                return
        except requests.RequestException:
            pass
        time.sleep(0.4)
    raise RuntimeError("No fue posible iniciar el servidor local del widget.")


def main() -> None:
    server = _start_server()

    def _cleanup() -> None:
        if server.poll() is None:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()

    atexit.register(_cleanup)

    _wait_for_server()

    webview.create_window(
        "Market Widget",
        URL,
        width=430,
        height=760,
        resizable=False,
        frameless=True,
        easy_drag=True,
    )
    webview.start()


if __name__ == "__main__":
    main()
