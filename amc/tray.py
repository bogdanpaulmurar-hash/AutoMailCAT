"""Icon next to the Windows clock (pystray + Pillow, both optional).

Not shown when DevPilot owns the tray: then the same options appear in the
DevPilot hub (see devpilot.tool.json).
"""
from __future__ import annotations

import logging
import webbrowser
from typing import Callable

LOG = logging.getLogger("automailcat.tray")

try:
    import pystray  # type: ignore
    from PIL import Image, ImageDraw  # type: ignore
    AVAILABLE = True
except Exception:  # noqa: BLE001
    AVAILABLE = False

LABELS = {
    "ro": {"open": "Deschide", "today": "Ziua de azi", "rules": "Reguli", "journal": "Jurnal",
           "sweep": "Procesează acum", "pause": "Pauză", "resume": "Reia", "quit": "Ieșire"},
    "en": {"open": "Open", "today": "Today", "rules": "Rules", "journal": "Journal",
           "sweep": "Process now", "pause": "Pause", "resume": "Resume", "quit": "Quit"},
}


def make_icon(size: int = 64):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = size / 64
    d.rounded_rectangle([4 * s, 12 * s, 60 * s, 52 * s], radius=7 * s, fill=(31, 92, 153, 255))
    d.line([(8 * s, 17 * s), (32 * s, 35 * s), (56 * s, 17 * s)], fill=(255, 255, 255, 255), width=int(4 * s))
    d.ellipse([40 * s, 34 * s, 62 * s, 56 * s], fill=(242, 169, 59, 255), outline=(255, 255, 255, 255), width=int(2 * s))
    d.polygon([(46 * s, 45 * s), (50 * s, 49 * s), (57 * s, 40 * s)], fill=(255, 255, 255, 255))
    return img


class Tray:
    def __init__(self, app, url: str, on_quit: Callable[[], None]):
        self.app, self.url, self.on_quit = app, url, on_quit
        self.icon = None

    def _t(self, key: str) -> str:
        lang = self.app.settings.get().get("language", "ro")
        return LABELS.get(lang, LABELS["ro"])[key]

    def _all(self, fn):
        for w in list(self.app.workers.values()):
            fn(w)

    def _paused(self) -> bool:
        return any(w.paused for w in self.app.workers.values())

    def _toggle_pause(self, *_):
        paused = not self._paused()
        def set_state(w):
            w.paused = paused
            if not paused:
                w.request_sweep()
        self._all(set_state)

    def run(self):
        menu = pystray.Menu(
            pystray.MenuItem(lambda _: self._t("open"), lambda: webbrowser.open(self.url), default=True),
            pystray.MenuItem(lambda _: self._t("today"), lambda: webbrowser.open(self.url + "#/today")),
            pystray.MenuItem(lambda _: self._t("rules"), lambda: webbrowser.open(self.url + "#/rules")),
            pystray.MenuItem(lambda _: self._t("journal"), lambda: webbrowser.open(self.url + "#/journal")),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(lambda _: self._t("sweep"), lambda: self._all(lambda w: w.request_sweep())),
            pystray.MenuItem(lambda _: self._t("resume") if self._paused() else self._t("pause"), self._toggle_pause),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(lambda _: self._t("quit"), self._quit),
        )
        self.icon = pystray.Icon("AutoMailCAT", make_icon(), "AutoMailCAT", menu)
        self.app.on_quit = self._quit
        LOG.info("Tray icon started")
        self.icon.run()

    def _quit(self, *_):
        if self.icon:
            self.icon.stop()
        self.on_quit()
