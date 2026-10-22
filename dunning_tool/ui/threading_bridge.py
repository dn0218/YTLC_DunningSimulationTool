# -*- coding: utf-8 -*-
"""
threading_bridge.py - marshals calls from worker threads onto the Tk main
loop safely (preprod tools stack style, hardened with a queue poller).

Worker threads NEVER call tk directly (calling root.after from a non-main
thread raises "main thread is not in main loop" while the mainloop is not
pumping). Instead every call is pushed onto a queue which a poller -
scheduled from the main thread via after() - drains on each tick.
"""

import queue
import threading


class UIThreadBridge:
    """Thread-safe bridge between background workers and the Tk UI."""

    POLL_MS = 80

    def __init__(self, root):
        self._root = root
        self._queue = queue.SimpleQueue()
        self._started = False
        self._after_id = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    def start(self):
        """Start the queue poller. MUST be called from the main thread."""
        with self._lock:
            if self._started:
                return
            self._started = True
        # stop cleanly when the window goes away, otherwise the pending
        # after() callback fires on a dead widget ("invalid command name")
        self._root.bind("<Destroy>", self._stop, add="+")
        self._poll()

    def _poll(self):
        """Drain pending calls; runs on the UI thread only."""
        while True:
            try:
                fn, args, kwargs = self._queue.get_nowait()
            except queue.Empty:
                break
            try:
                fn(*args, **kwargs)
            except Exception:
                import traceback
                traceback.print_exc()
        self._after_id = self._root.after(self.POLL_MS, self._poll)

    def _stop(self, event=None):
        # <Destroy> also fires for every child widget - only react to root
        if event is not None and getattr(event, "widget", None) is not self._root:
            return
        if self._after_id is not None:
            try:
                self._root.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None

    # ------------------------------------------------------------------
    def run_on_ui(self, fn, *args, **kwargs):
        """Schedule fn(*args, **kwargs) on the UI thread; non-blocking."""
        self._queue.put((fn, args, kwargs))

    def log(self, console, text):
        """Append a log line to a console widget from any thread."""
        self.run_on_ui(console.append, text)

    def ask_yes_no(self, title, message, **msgbox_kwargs):
        """Show a yes/no dialog on the UI thread, blocking the caller."""
        if threading.current_thread() is threading.main_thread():
            from tkinter import messagebox
            return bool(messagebox.askyesno(title, message, **msgbox_kwargs))

        done = threading.Event()
        answer = [False]

        def _ask():
            from tkinter import messagebox
            answer[0] = bool(messagebox.askyesno(title, message,
                                                 **msgbox_kwargs))
            done.set()

        self.run_on_ui(_ask)
        done.wait(timeout=600)
        return answer[0]

    def show_info(self, title, message):
        self.run_on_ui(self._msg, "info", title, message)

    def show_warning(self, title, message):
        self.run_on_ui(self._msg, "warn", title, message)

    def show_error(self, title, message):
        self.run_on_ui(self._msg, "error", title, message)

    @staticmethod
    def _msg(kind, title, message):
        from tkinter import messagebox
        fn = {"info": messagebox.showinfo,
              "warn": messagebox.showwarning,
              "error": messagebox.showerror}[kind]
        fn(title, message)
