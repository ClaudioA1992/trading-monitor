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

from prices.i18n import get_language, set_language, tr

HOST = "127.0.0.1"
PORT = 8765
URL = f"http://{HOST}:{PORT}/"


class WidgetApi:
    def __init__(self, app: "WidgetDesktopApp") -> None:
        self._app = app

    def set_compact_mode(self, compact: bool) -> dict[str, object]:
        applied = self._app.set_compact_mode(bool(compact))
        return {"ok": True, "compact": bool(compact), "applied": applied}


class ThreadedWSGIServer(ThreadingMixIn, WSGIServer):
    daemon_threads = True


class WidgetDesktopApp:
    def __init__(self) -> None:
        self.window: webview.Window | None = None
        self.httpd = None
        self.server_thread: threading.Thread | None = None
        self.topmost_thread: threading.Thread | None = None
        self.tray_icon: Any = None
        self.closing = False
        self.always_on_top = self._env_flag("WIDGET_ALWAYS_ON_TOP", default=False)
        self._winforms_browser: Any = None
        self.languages = ["es", "en", "pt", "fr", "de", "ja", "zh"]
        self._force_exit_started = False
        self.compact_mode = False
        self.window_width = 420
        self.window_height_expanded = 560
        self.window_height_compact = 360
        self._expanded_height_snapshot: int | None = None

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
            handler_class=WSGIRequestHandler,
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
            self._apply_windows_topmost(True, bring_to_front=True)
            if not was_on_top:
                self.window.on_top = self.always_on_top
        except Exception:
            pass

    def set_compact_mode(self, compact: bool) -> bool:
        self.compact_mode = bool(compact)
        if self.window is None:
            return False

        try:
            current_width = self._get_current_window_width()
            if current_width is not None and current_width > 0:
                self.window_width = int(current_width)

            if self.compact_mode:
                current_height = self._get_current_window_height()
                if current_height is not None and current_height > 0:
                    self._expanded_height_snapshot = int(current_height)
                    self.window_height_expanded = int(current_height)

            target_height = self.window_height_compact if self.compact_mode else self.window_height_expanded
            if not self.compact_mode and self._expanded_height_snapshot is not None:
                target_height = int(self._expanded_height_snapshot)
            self._resize_window(self.window_width, target_height)
            return True
        except Exception:
            return False

    def _get_current_window_width(self) -> int | None:
        if self.window is None:
            return None

        if sys.platform != "win32":
            return self.window_width

        browser = self._get_winforms_browser()
        if browser is None:
            return self.window_width

        try:
            hwnd = self._get_window_hwnd(browser)
            if hwnd is None:
                return int(browser.Width)

            class RECT(ctypes.Structure):
                _fields_ = [
                    ("left", ctypes.c_long),
                    ("top", ctypes.c_long),
                    ("right", ctypes.c_long),
                    ("bottom", ctypes.c_long),
                ]

            rect = RECT()
            if ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                width = int(rect.right - rect.left)
                if width > 0:
                    return width

            return int(browser.Width)
        except Exception:
            return self.window_width

    def _get_current_window_height(self) -> int | None:
        if self.window is None:
            return None

        if sys.platform != "win32":
            return self.window_height_expanded

        browser = self._get_winforms_browser()
        if browser is None:
            return self.window_height_expanded

        try:
            hwnd = self._get_window_hwnd(browser)
            if hwnd is None:
                return int(browser.Height)

            class RECT(ctypes.Structure):
                _fields_ = [
                    ("left", ctypes.c_long),
                    ("top", ctypes.c_long),
                    ("right", ctypes.c_long),
                    ("bottom", ctypes.c_long),
                ]

            rect = RECT()
            if ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                height = int(rect.bottom - rect.top)
                if height > 0:
                    return height

            return int(browser.Height)
        except Exception:
            return self.window_height_expanded

    def _resize_window(self, width: int, height: int) -> None:
        if self.window is None:
            return

        target_width = int(width)
        target_height = int(height)

        if sys.platform == "win32":
            browser = self._get_winforms_browser()
            if browser is not None:
                hwnd = self._get_window_hwnd(browser)
                if hwnd is not None:
                    try:
                        user32 = ctypes.windll.user32
                        SWP_NOMOVE = 0x0002
                        SWP_NOZORDER = 0x0004
                        SWP_NOACTIVATE = 0x0010
                        SWP_SHOWWINDOW = 0x0040
                        user32.SetWindowPos(
                            hwnd,
                            0,
                            0,
                            0,
                            target_width,
                            target_height,
                            SWP_NOMOVE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_SHOWWINDOW,
                        )
                        return
                    except Exception:
                        pass

        self.window.resize(target_width, target_height)

    def _is_menu_checked(self, _item: Any) -> bool:
        return bool(self.always_on_top)

    def _toggle_always_on_top(self, _icon: Any = None, _item: Any = None) -> None:
        if self.window is None:
            return

        self.always_on_top = not self.always_on_top
        try:
            self.window.on_top = self.always_on_top
            self._apply_windows_topmost(self.always_on_top, bring_to_front=self.always_on_top)
        except Exception:
            pass

    def _language_item_checked_factory(self, lang_code: str):
        def _checked(_item: Any) -> bool:
            return get_language() == lang_code

        return _checked

    def _set_language_factory(self, lang_code: str):
        def _set_language(_icon: Any = None, _item: Any = None) -> None:
            set_language(lang_code)
            self._refresh_widget_language()

        return _set_language

    def _refresh_widget_language(self) -> None:
        if self.window is None:
            return

        try:
            self.window.evaluate_js(
                "if (window.__widgetSyncLanguage) { window.__widgetSyncLanguage(); }"
            )
            return
        except Exception:
            pass

        try:
            # Fallback when JS bridge is not ready yet.
            self.window.load_url(f"{URL}?v={int(time.time())}")
        except Exception:
            pass

    def _language_menu(self) -> Any:
        labels = {
            "es": "Espanol",
            "en": "English",
            "pt": "Portugues",
            "fr": "Francais",
            "de": "Deutsch",
            "ja": "日本語",
            "zh": "中文",
        }

        items = []
        for code in self.languages:
            items.append(
                pystray.MenuItem(
                    labels[code],
                    self._set_language_factory(code),
                    checked=self._language_item_checked_factory(code),
                )
            )
        return pystray.Menu(*items)

    def _get_winforms_browser(self) -> Any:
        if self.window is None or sys.platform != "win32":
            return None

        if self._winforms_browser is not None:
            return self._winforms_browser

        try:
            from webview.platforms import winforms  # type: ignore

            self._winforms_browser = winforms.BrowserView.instances.get(self.window.uid)
            return self._winforms_browser
        except Exception:
            return None

    def _get_window_hwnd(self, browser: Any) -> int | None:
        try:
            handle = browser.Handle
            if hasattr(handle, "ToInt64"):
                return int(handle.ToInt64())
            return int(handle)
        except Exception:
            return None

    def _run_on_winforms_ui(self, browser: Any, func: Any, wait: bool) -> None:
        try:
            from System import Action  # type: ignore

            if getattr(browser, "InvokeRequired", False):
                if wait:
                    browser.Invoke(Action(func))
                else:
                    browser.BeginInvoke(Action(func))
            else:
                func()
        except Exception:
            pass

    def _apply_windows_topmost(self, enabled: bool, bring_to_front: bool) -> None:
        if sys.platform != "win32":
            return

        browser = self._get_winforms_browser()
        if browser is None:
            return

        def _apply_winforms() -> None:
            browser.TopMost = bool(enabled)
            if bring_to_front:
                browser.Show()
                browser.Activate()
                browser.BringToFront()

        self._run_on_winforms_ui(browser, _apply_winforms, wait=True)

        hwnd = self._get_window_hwnd(browser)
        if hwnd is None:
            return

        try:
            user32 = ctypes.windll.user32
            HWND_TOPMOST = -1
            HWND_NOTOPMOST = -2
            SWP_NOMOVE = 0x0002
            SWP_NOSIZE = 0x0001
            SWP_NOACTIVATE = 0x0010
            SWP_SHOWWINDOW = 0x0040
            SW_RESTORE = 9

            user32.SetWindowPos(
                hwnd,
                HWND_TOPMOST if enabled else HWND_NOTOPMOST,
                0,
                0,
                0,
                0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW | (SWP_NOACTIVATE if not bring_to_front else 0),
            )

            if bring_to_front:
                user32.ShowWindow(hwnd, SW_RESTORE)
                user32.SetForegroundWindow(hwnd)
        except Exception:
            pass

    def _topmost_watchdog(self) -> None:
        while not self.closing:
            try:
                if self.always_on_top:
                    self._apply_windows_topmost(True, bring_to_front=False)
            except Exception:
                pass
            time.sleep(1.0)

    def _quit_app(self, _icon: Any = None, _item: Any = None) -> None:
        if self.closing:
            return
        self.closing = True

        if not self._force_exit_started:
            self._force_exit_started = True

            def _force_exit() -> None:
                # Ensure process termination even if tray/webview cleanup blocks.
                time.sleep(1.5)
                os._exit(0)

            threading.Thread(target=_force_exit, daemon=True).start()

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

    def _tray_show_label(self, _item: Any) -> str:
        return tr("tray_show", get_language())

    def _tray_language_label(self, _item: Any) -> str:
        localized = tr("tray_language", get_language())
        if localized.strip().lower() == "language":
            return localized
        return f"{localized} (Language)"

    def _tray_topmost_label(self, _item: Any) -> str:
        return tr("tray_always_on_top", get_language())

    def _tray_about_label(self, _item: Any) -> str:
        return tr("tray_about", get_language())

    def _tray_exit_label(self, _item: Any) -> str:
        return tr("tray_exit", get_language())

    def _show_about(self, _icon: Any = None, _item: Any = None) -> None:
        try:
            title = tr("about_title", get_language())
            body = tr("about_body", get_language())
            ctypes.windll.user32.MessageBoxW(0, body, title, 0x40)
        except Exception:
            pass

    def _start_tray(self) -> None:
        menu = pystray.Menu(
            pystray.MenuItem(self._tray_show_label, self._show_window),
            pystray.MenuItem(self._tray_topmost_label, self._toggle_always_on_top, checked=self._is_menu_checked),
            pystray.MenuItem(self._tray_language_label, self._language_menu()),
            pystray.MenuItem(self._tray_about_label, self._show_about),
            pystray.MenuItem(self._tray_exit_label, self._quit_app),
        )
        self.tray_icon = pystray.Icon("btc_widget", self._tray_image(), "BTC Widget", menu)
        self.tray_icon.run_detached()

    def run(self) -> None:
        self._start_server()
        self._wait_for_server()
        self._start_tray()
        window_url = f"{URL}?v={int(time.time())}"

        self.window = webview.create_window(
            "Market Widget",
            window_url,
            width=self.window_width,
            height=self.window_height_expanded,
            resizable=False,
            frameless=True,
            easy_drag=True,
            on_top=self.always_on_top,
            js_api=WidgetApi(self),
        )

        def _on_closed() -> None:
            self._quit_app()

        self.window.events.closed += _on_closed

        self.topmost_thread = threading.Thread(target=self._topmost_watchdog, daemon=True)
        self.topmost_thread.start()

        try:
            webview.start()
        finally:
            self._quit_app()


if __name__ == "__main__":
    WidgetDesktopApp().run()
