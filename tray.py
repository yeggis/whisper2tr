#!/usr/bin/env python3
"""
tray.py — whisper2tr sistem tepsisi
StatusNotifierItem (SNI) — Quickshell uyumlu, dbus-next
Sol tık → tarayıcı aç
Sağ tık → Yeniden başlat / Çıkış
"""
import asyncio
import subprocess
import sys
import threading
import urllib.request
import webbrowser
from pathlib import Path

try:
    from dbus_next.aio import MessageBus
    from dbus_next.service import ServiceInterface, method, dbus_property
    from dbus_next.service import PropertyAccess
    from dbus_next import Variant, BusType
except ImportError:
    print("Eksik kütüphane: pip install dbus-next")
    sys.exit(1)

PORT    = 7860
APP_DIR = Path(__file__).parent.resolve()
APP_PY  = APP_DIR / "app.py"
PYTHON  = sys.executable

server_proc = None
_stop_event = None

# ── Sunucu yönetimi ───────────────────────────────────────────────────────────
def start_server():
    global server_proc
    if server_proc and server_proc.poll() is None:
        return
    server_proc = subprocess.Popen([PYTHON, str(APP_PY)])

    def wait_and_open():
        import time
        for _ in range(30):
            time.sleep(1)
            try:
                urllib.request.urlopen(f"http://localhost:{PORT}", timeout=1)
                webbrowser.open(f"http://localhost:{PORT}")
                return
            except Exception:
                continue

    threading.Thread(target=wait_and_open, daemon=True).start()

def stop_server():
    global server_proc
    if server_proc and server_proc.poll() is None:
        server_proc.terminate()
    server_proc = None

def open_browser():
    webbrowser.open(f"http://localhost:{PORT}")

def quit_app():
    stop_server()
    if _stop_event:
        _stop_event.set()

# ── StatusNotifierItem ────────────────────────────────────────────────────────
class StatusNotifierItem(ServiceInterface):
    def __init__(self):
        super().__init__("org.kde.StatusNotifierItem")

    @dbus_property(access=PropertyAccess.READ)
    def Category(self) -> "s":
        return "ApplicationStatus"

    @dbus_property(access=PropertyAccess.READ)
    def Id(self) -> "s":
        return "whisper2tr"

    @dbus_property(access=PropertyAccess.READ)
    def Title(self) -> "s":
        return "whisper2tr"

    @dbus_property(access=PropertyAccess.READ)
    def Status(self) -> "s":
        return "Active"

    @dbus_property(access=PropertyAccess.READ)
    def IconName(self) -> "s":
        return "accessories-dictionary"

    @dbus_property(access=PropertyAccess.READ)
    def Menu(self) -> "o":
        return "/MenuBar"

    @dbus_property(access=PropertyAccess.READ)
    def ItemIsMenu(self) -> "b":
        return False

    @dbus_property(access=PropertyAccess.READ)
    def ToolTip(self) -> "(sa(iiay)ss)":
        return ["", [], "whisper2tr", "İngilizce → Türkçe Altyazı"]

    @method()
    def Activate(self, x: "i", y: "i"):
        open_browser()

    @method()
    def SecondaryActivate(self, x: "i", y: "i"):
        open_browser()

    @method()
    def Scroll(self, delta: "i", orientation: "s"):
        pass

    @method()
    def ContextMenu(self, x: "i", y: "i"):
        pass


# ── DBus Menü ─────────────────────────────────────────────────────────────────
class DbusMenu(ServiceInterface):
    def __init__(self):
        super().__init__("com.canonical.dbusmenu")
        self._revision = 0
        self._items = [
            [0, {"type": Variant("s","standard"), "label": Variant("s","Yeniden başlat"),
                 "enabled": Variant("b",True), "visible": Variant("b",True)}],
            [1, {"type": Variant("s","separator"), "label": Variant("s",""),
                 "enabled": Variant("b",True), "visible": Variant("b",True)}],
            [2, {"type": Variant("s","standard"), "label": Variant("s","Çıkış"),
                 "enabled": Variant("b",True), "visible": Variant("b",True)}],
        ]

    @dbus_property(access=PropertyAccess.READ)
    def Version(self) -> "u":
        return 3

    @dbus_property(access=PropertyAccess.READ)
    def TextDirection(self) -> "s":
        return "ltr"

    @dbus_property(access=PropertyAccess.READ)
    def Status(self) -> "s":
        return "normal"

    @dbus_property(access=PropertyAccess.READ)
    def IconThemePath(self) -> "as":
        return []

    @method()
    def GetLayout(self, parentId: "i", recursionDepth: "i", propertyNames: "as") -> "u(ia{sv}av)":
        children = []
        for item_id, props in self._items:
            children.append(Variant("(ia{sv}av)", [item_id, props, []]))
        return [
            self._revision,
            [0, {}, children],
        ]

    @method()
    def GetGroupProperties(self, ids: "ai", propertyNames: "as") -> "a(ia{sv})":
        result = []
        for item_id, props in self._items:
            if not ids or item_id in ids:
                result.append([item_id, props])
        return result

    @method()
    def GetProperty(self, id: "i", name: "s") -> "v":
        for item_id, props in self._items:
            if item_id == id and name in props:
                return props[name]
        return Variant("s", "")

    @method()
    def Event(self, id: "i", eventId: "s", data: "v", timestamp: "u"):
        if eventId == "clicked":
            if id == 0:
                stop_server()
                threading.Timer(1.5, start_server).start()
            elif id == 2:
                quit_app()

    @method()
    def EventGroup(self, events: "a(isvu)") -> "ai":
        for args in events:
            self.Event(*args)
        return []

    @method()
    def AboutToShow(self, id: "i") -> "b":
        return False

    @method()
    def AboutToShowGroup(self, ids: "ai") -> "aiai":
        return [[], []]


# ── Ana döngü ─────────────────────────────────────────────────────────────────
async def main():
    global _stop_event
    _stop_event = asyncio.Event()

    bus  = await MessageBus(bus_type=BusType.SESSION).connect()
    sni  = StatusNotifierItem()
    menu = DbusMenu()

    bus.export("/StatusNotifierItem", sni)
    bus.export("/MenuBar", menu)

    await bus.request_name("org.kde.StatusNotifierItem-whisper2tr-1")

    try:
        watcher = bus.get_proxy_object(
            "org.kde.StatusNotifierWatcher",
            "/StatusNotifierWatcher",
            await bus.introspect("org.kde.StatusNotifierWatcher", "/StatusNotifierWatcher"),
        )
        iface = watcher.get_interface("org.kde.StatusNotifierWatcher")
        await iface.call_register_status_notifier_item(
            "org.kde.StatusNotifierItem-whisper2tr-1"
        )
        print("[Tray] Quickshell tray'e kayıt olundu ✓")
    except Exception as e:
        print(f"[Tray] Watcher kaydı başarısız: {e}")

    print(f"[Tray] Çalışıyor — http://localhost:{PORT}")
    print("[Tray] Durdurmak için Ctrl+C")

    await _stop_event.wait()


if __name__ == "__main__":
    start_server()
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    finally:
        stop_server()
        print("\n[Tray] Kapatıldı.")
