"""SirJoe VPN - pannello di controllo per Cloudflare WARP (Windows).

Richiede il client ufficiale "Cloudflare WARP" installato (fornisce warp-cli.exe).
Questa app lo comanda: Connetti/Disconnetti, stato, IP pubblico, avvio con Windows,
icona vicino all'orologio.
"""
import os
import queue
import shutil
import subprocess
import sys
import threading
import tkinter as tk
import urllib.request
from tkinter import messagebox

try:
    import winreg
except ImportError:  # non-Windows (solo per test)
    winreg = None

try:
    import pystray
    from PIL import Image, ImageDraw
except ImportError:
    pystray = None

APP = "SirJoe VPN"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
NO_WINDOW = 0x08000000
WARP_PATHS = [
    r"C:\Program Files\Cloudflare\Cloudflare WARP\warp-cli.exe",
    r"C:\Program Files (x86)\Cloudflare\Cloudflare WARP\warp-cli.exe",
]
GREEN, RED, GREY, ORANGE = "#1e9e4a", "#c62828", "#757575", "#ef8f00"


def find_warp():
    exe = shutil.which("warp-cli")
    if exe:
        return exe
    for p in WARP_PATHS:
        if os.path.exists(p):
            return p
    return None


def warp(*args):
    """Esegue warp-cli e ritorna l'output; None se WARP non e' installato."""
    exe = find_warp()
    if not exe:
        return None
    try:
        r = subprocess.run(
            [exe, *args], capture_output=True, text=True, timeout=25,
            creationflags=NO_WINDOW if os.name == "nt" else 0,
        )
        return (r.stdout + r.stderr).strip()
    except Exception as e:  # noqa: BLE001
        return str(e)


def get_state():
    out = warp("status")
    if out is None:
        return "missing"
    lo = out.lower()
    if "disconnected" in lo:
        return "off"
    if "connecting" in lo:
        return "connecting"
    if "connected" in lo:
        return "on"
    return "unknown"


def public_info():
    """(ip, warp_attivo) dal servizio di Cloudflare; (None, False) se offline."""
    try:
        with urllib.request.urlopen("https://www.cloudflare.com/cdn-cgi/trace", timeout=6) as r:
            lines = r.read().decode().splitlines()
        d = dict(line.split("=", 1) for line in lines if "=" in line)
        return d.get("ip", "?"), d.get("warp", "off") == "on"
    except Exception:  # noqa: BLE001
        return None, False


def do_connect():
    out = warp("connect") or ""
    lo = out.lower()
    if "registration" in lo and ("missing" in lo or "no " in lo):
        reg = warp("registration", "new") or ""
        if "unknown" in reg.lower() or "unrecognized" in reg.lower() or "error" in reg.lower():
            warp("register")  # versioni piu' vecchie del client
        warp("connect")


def autostart_get():
    if not winreg:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, APP)
        return True
    except OSError:
        return False


def autostart_set(on):
    if not winreg:
        return
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if on:
            exe = sys.executable if getattr(sys, "frozen", False) else os.path.abspath(__file__)
            winreg.SetValueEx(k, APP, 0, winreg.REG_SZ, f'"{exe}" --minimized')
        else:
            try:
                winreg.DeleteValue(k, APP)
            except OSError:
                pass


def tray_image(color):
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    ImageDraw.Draw(img).ellipse((6, 6, 58, 58), fill=color)
    return img


class App:
    def __init__(self, start_hidden=False):
        self.root = tk.Tk()
        self.root.title(APP)
        self.root.geometry("360x330")
        self.root.resizable(False, False)
        self.q = queue.Queue()
        self.busy = False
        self.state = "unknown"
        self.icon = None

        tk.Label(self.root, text=APP, font=("Segoe UI", 16, "bold")).pack(pady=(14, 2))
        self.lbl_state = tk.Label(self.root, text="...", font=("Segoe UI", 13))
        self.lbl_state.pack(pady=4)
        self.btn = tk.Button(
            self.root, text="Connetti", font=("Segoe UI", 15, "bold"),
            width=14, height=2, fg="white", bg=GREY, command=self.toggle,
        )
        self.btn.pack(pady=10)
        self.lbl_ip = tk.Label(self.root, text="IP pubblico: ...", font=("Segoe UI", 10))
        self.lbl_ip.pack()
        self.lbl_warp = tk.Label(self.root, text="", font=("Segoe UI", 10))
        self.lbl_warp.pack()

        self.var_auto = tk.BooleanVar(value=autostart_get())
        tk.Checkbutton(
            self.root, text="Avvia con Windows (in background)",
            variable=self.var_auto, command=lambda: autostart_set(self.var_auto.get()),
        ).pack(pady=(12, 0))
        tk.Label(
            self.root, fg=GREY, font=("Segoe UI", 8),
            text="Cifra il traffico con Cloudflare WARP.\nL'IP resta del tuo paese.",
        ).pack(pady=6)

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        if pystray:
            self.start_tray()
        if start_hidden and pystray:
            self.root.withdraw()

        self.refresh()
        self.root.after(200, self.poll_queue)
        self.root.after(4000, self.auto_refresh)

    # --- stato ---
    def refresh(self):
        threading.Thread(target=self._refresh_worker, daemon=True).start()

    def _refresh_worker(self):
        st = get_state()
        ip, on = public_info() if st != "missing" else (None, False)
        self.q.put(("state", st, ip, on))

    def auto_refresh(self):
        if not self.busy:
            self.refresh()
        self.root.after(4000, self.auto_refresh)

    def poll_queue(self):
        try:
            while True:
                msg = self.q.get_nowait()
                if msg[0] == "state":
                    self.apply_state(*msg[1:])
                elif msg[0] == "done":
                    self.busy = False
                    self.refresh()
        except queue.Empty:
            pass
        self.root.after(200, self.poll_queue)

    def apply_state(self, st, ip, warp_on):
        self.state = st
        if st == "missing":
            self.lbl_state.config(text="WARP non installato", fg=RED)
            self.btn.config(text="Scarica WARP", bg=ORANGE, state="normal")
        elif st == "on":
            self.lbl_state.config(text="Protetto", fg=GREEN)
            self.btn.config(text="Disconnetti", bg=GREEN, state="normal")
        elif st == "connecting":
            self.lbl_state.config(text="Connessione...", fg=ORANGE)
            self.btn.config(text="Attendi", bg=ORANGE, state="disabled")
        else:
            self.lbl_state.config(text="Non protetto", fg=RED)
            self.btn.config(text="Connetti", bg=RED, state="normal")
        self.lbl_ip.config(text=f"IP pubblico: {ip or 'non disponibile'}")
        if st == "on" and ip:
            self.lbl_warp.config(text="Verifica Cloudflare: " + ("OK" if warp_on else "NON confermata"))
        else:
            self.lbl_warp.config(text="")
        if self.icon:
            self.icon.icon = tray_image(GREEN if st == "on" else RED)
            self.icon.title = f"{APP} - " + ("protetto" if st == "on" else "non protetto")

    # --- azioni ---
    def toggle(self):
        if self.busy:
            return
        if self.state == "missing":
            import webbrowser
            webbrowser.open("https://one.one.one.one/")
            messagebox.showinfo(APP, "Installa Cloudflare WARP, poi riapri questa app.")
            return
        self.busy = True
        self.btn.config(state="disabled", text="Attendi")
        want_off = self.state == "on"
        threading.Thread(target=self._toggle_worker, args=(want_off,), daemon=True).start()

    def _toggle_worker(self, want_off):
        if want_off:
            warp("disconnect")
        else:
            do_connect()
        self.q.put(("done",))

    # --- tray ---
    def start_tray(self):
        menu = pystray.Menu(
            pystray.MenuItem("Apri", lambda: self.root.after(0, self.show), default=True),
            pystray.MenuItem("Connetti / Disconnetti", lambda: self.root.after(0, self.toggle)),
            pystray.MenuItem("Esci", lambda: self.root.after(0, self.quit)),
        )
        self.icon = pystray.Icon(APP, tray_image(RED), APP, menu)
        threading.Thread(target=self.icon.run, daemon=True).start()

    def show(self):
        self.root.deiconify()
        self.root.lift()

    def on_close(self):
        if pystray:
            self.root.withdraw()  # resta nell'area di notifica
        else:
            self.quit()

    def quit(self):
        if self.icon:
            self.icon.stop()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    App(start_hidden="--minimized" in sys.argv).run()
