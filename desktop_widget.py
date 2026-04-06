from __future__ import annotations
# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false

import ctypes
import os
import sys
import threading
import time
from pathlib import Path
from socketserver import ThreadingMixIn
from typing import Any
from wsgiref.simple_server import WSGIServer, make_server
from wsgiref.simple_server import WSGIRequestHandler

import requests
import webview  # type: ignore[import-not-found]
from PIL import Image, ImageDraw  # type: ignore[import-not-found]
import pystray  # type: ignore[import-not-found]

HOST = "127.0.0.1"
PORT = 8765
URL = f"http://{HOST}:{PORT}/"


class ThreadedWSGIServer(ThreadingMixIn, WSGIServer):
    daemon_threads = True


class QuietRequestHandler(WSGIRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:
        return


class WidgetDesktopApp:
    def __init__(self) -> None:
        self.window: webview.Window | None = None
        self.httpd = None
        self.server_thread: threading.Thread | None = None
        self.tray_icon: Any = None
        self.closing = False
        self.always_on_top = self._env_flag("WIDGET_ALWAYS_ON_TOP", default=False)

    def _env_flag(self, name: str, default: bool = False) -> bool:
        value = str(os.getenv(name, "1" if default else "0")).strip().lower()
        return value in {"1", "true", "yes", "on"}

    def _base_dir(self) -> Path:
        if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
            return Path(getattr(sys, "_MEIPASS"))
        return Path(__file__).resolve().parent

    def _configure_django(self) -> None:
        base_dir = self._base_dir()
        if str(base_dir) not in sys.path:
            sys.path.insert(0, str(base_dir))
        os.chdir(base_dir)
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "btc_widget.settings")

    def _start_server(self) -> None:
        from django.contrib.staticfiles.handlers import StaticFilesHandler
        from django.core.wsgi import get_wsgi_application

        self._configure_django()

        app = StaticFilesHandler(get_wsgi_application())
        self.httpd = make_server(
            HOST,
            PORT,
            app,
            server_class=ThreadedWSGIServer,
            handler_class=QuietRequestHandler,
        )
        self.server_thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.server_thread.start()

    def _wait_for_server(self, timeout_seconds: int = 30) -> None:
        started_at = time.time()
        while (time.time() - started_at) < timeout_seconds:
            try:
                response = requests.get(URL, timeout=2)
                if response.status_code < 500:
                    return
            except requests.RequestException:
                pass
            time.sleep(0.25)
        raise RuntimeError("No fue posible iniciar el servidor local del widget.")

    def _tray_image(self):
        image = Image.new("RGBA", (64, 64), (7, 24, 37, 255))
        draw: Any = ImageDraw.Draw(image)
        draw.rounded_rectangle((4, 4, 60, 60), radius=12, outline=(33, 194, 142, 255), width=3)
        draw.text((14, 20), "BTC", fill=(255, 255, 255, 255))
        return image

    def _show_window(self, _icon: Any = None, _item: Any = None) -> None:
        if self.window is None:
            return
        try:
            was_on_top = bool(self.window.on_top)
            self.window.on_top = True
            self.window.show()
            self.window.restore()
            self._bring_to_front_windows()
            if not was_on_top:
                self.window.on_top = self.always_on_top
        except Exception:
            pass

    def _is_menu_checked(self, _item: Any) -> bool:
        return bool(self.always_on_top)

    def _toggle_always_on_top(self, _icon: Any = None, _item: Any = None) -> None:
        if self.window is None:
            return

        self.always_on_top = not self.always_on_top
        try:
            self.window.on_top = self.always_on_top
            if self.always_on_top:
                self._bring_to_front_windows()
        except Exception:
            pass

    def _bring_to_front_windows(self) -> None:
        if self.window is None or sys.platform != "win32":
            return

        try:
            from webview.platforms import winforms  # type: ignore

            browser: Any = winforms.BrowserView.instances.get(self.window.uid)
            if browser is None:
                return

            hwnd = int(browser.Handle)
            user32 = ctypes.windll.user32
            SW_RESTORE = 9

            user32.ShowWindow(hwnd, SW_RESTORE)
            user32.SetForegroundWindow(hwnd)
        except Exception:
            pass

    def _quit_app(self, _icon: Any = None, _item: Any = None) -> None:
        if self.closing:
            return
        self.closing = True

        try:
            if self.tray_icon is not None:
                self.tray_icon.stop()
        except Exception:
            pass

        try:
            if self.window is not None:
                self.window.destroy()
        except Exception:
            pass

        try:
            if self.httpd is not None:
                self.httpd.shutdown()
                self.httpd.server_close()
        except Exception:
            pass

    def _start_tray(self) -> None:
        menu = pystray.Menu(
            pystray.MenuItem("Mostrar widget", self._show_window),
            pystray.MenuItem("Siempre al frente", self._toggle_always_on_top, checked=self._is_menu_checked),
            pystray.MenuItem("Salir", self._quit_app),
        )
        self.tray_icon = pystray.Icon("btc_widget", self._tray_image(), "BTC Widget", menu)
        self.tray_icon.run_detached()

    def run(self) -> None:
        self._start_server()
        self._wait_for_server()
        self._start_tray()

        self.window = webview.create_window(
            "Market Widget",
            URL,
            width=430,
            height=700,
            resizable=False,
            frameless=True,
            easy_drag=True,
            on_top=self.always_on_top,
        )

        def _on_closed() -> None:
            self._quit_app()

        self.window.events.closed += _on_closed
        webview.start()


if __name__ == "__main__":
    WidgetDesktopApp().run()
