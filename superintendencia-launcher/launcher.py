import queue
import socket
import subprocess
import threading
import tkinter as tk
from tkinter import messagebox
from tkinter import ttk

import runner
import setup
import updater

_LOCK_PORT = 48502


def acquire_single_instance_lock() -> socket.socket | None:
    lock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        lock.bind(("127.0.0.1", _LOCK_PORT))
        lock.listen(1)
        return lock
    except OSError:
        lock.close()
        root = tk.Tk()
        root.withdraw()
        messagebox.showinfo(
            "AFP Lookup",
            "AFP Lookup ya se esta ejecutando. Espera a que termine la instalacion.",
        )
        root.destroy()
        return None


class LauncherWindow:
    def __init__(self, instance_lock: socket.socket):
        self._instance_lock = instance_lock
        self._proc: subprocess.Popen | None = None
        self._q: queue.Queue = queue.Queue()

        self.root = tk.Tk()
        self.root.title("AFP Lookup")
        self.root.geometry("340x130")
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self._status_var = tk.StringVar(value="Iniciando...")
        tk.Label(self.root, textvariable=self._status_var, wraplength=300).pack(
            pady=(18, 6)
        )

        self._bar = ttk.Progressbar(self.root, mode="indeterminate", length=280)
        self._bar.pack()
        self._bar.start(12)

        self._btn = tk.Button(
            self.root,
            text="Abrir app",
            state="disabled",
            command=self._open_browser,
            width=16,
        )
        self._btn.pack(pady=(10, 0))

        threading.Thread(target=self._worker, daemon=True).start()
        self.root.after(100, self._poll_queue)
        self.root.mainloop()

    def _worker(self):
        try:
            setup.ensure_desktop_shortcut(on_status=self._post)

            if not setup.is_python_ready():
                setup.install_python(on_status=self._post)

            if not setup.is_playwright_ready() or updater.needs_update():
                updater.download_and_install(on_status=self._post)

            if not setup.is_playwright_ready():
                setup.install_playwright(on_status=self._post)

            self._proc = runner.launch(on_status=self._post)
            self._q.put(("done", None))
        except Exception as exc:
            self._q.put(("error", str(exc)))

    def _post(self, msg: str):
        self._q.put(("status", msg))

    def _poll_queue(self):
        try:
            while True:
                kind, payload = self._q.get_nowait()
                if kind == "status":
                    self._status_var.set(payload)
                elif kind == "done":
                    self._bar.stop()
                    self._bar.config(mode="determinate", value=100)
                    self._btn.config(state="normal")
                    self._status_var.set("App en ejecucion")
                elif kind == "error":
                    self._bar.stop()
                    self._status_var.set(f"Error: {payload}")
        except queue.Empty:
            pass
        self.root.after(150, self._poll_queue)

    def _open_browser(self):
        import webbrowser

        webbrowser.open(f"http://localhost:{runner.PORT}")

    def _on_close(self):
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
        self._instance_lock.close()
        self.root.destroy()


if __name__ == "__main__":
    instance_lock = acquire_single_instance_lock()
    if instance_lock:
        LauncherWindow(instance_lock)
