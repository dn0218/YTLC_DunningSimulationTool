# -*- coding: utf-8 -*-
"""
widgets.py - reusable UI widgets (preprod tools stack style).
"""

import tkinter as tk
from tkinter import ttk, scrolledtext

from .theme import FONT_CONSOLE, ZEBRA, TEXT_MUTED


class ConsoleWidget(scrolledtext.ScrolledText):
    """Dark terminal-style read-only console with a simple append API."""

    def __init__(self, parent, **kwargs):
        super().__init__(
            parent,
            state="disabled",
            wrap=tk.WORD,
            bg="#1e1e1e",
            fg="#d4d4d4",
            insertbackground="white",
            font=FONT_CONSOLE,
            relief="flat",
            borderwidth=0,
            **kwargs
        )

    def append(self, text):
        self.config(state="normal")
        self.insert(tk.END, text + "\n")
        self.see(tk.END)
        self.config(state="disabled")

    def clear(self):
        self.config(state="normal")
        self.delete("1.0", tk.END)
        self.config(state="disabled")


class RowDetailPopup:
    """Transient toplevel that shows one table row as label: value lines.

    Long values (error texts, JSON blobs...) stay fully readable here even
    though the table cell itself is clipped.
    """

    WIDTH = 560
    HEIGHT = 420

    def __init__(self, table, columns, values):
        self.table = table
        self.columns = columns
        self.values = values

        self.win = tk.Toplevel(table)
        self.win.title(_("Row Detail", table))
        self.win.geometry("%dx%d" % (self.WIDTH, self.HEIGHT))
        self.win.transient(table.winfo_toplevel())

        body = ttk.Frame(self.win, padding=8)
        body.pack(fill="both", expand=True)

        txt = scrolledtext.ScrolledText(body, wrap="word", font=FONT_CONSOLE,
                                        width=64, height=20)
        txt.pack(fill="both", expand=True)
        for name, value in zip(columns, values):
            txt.insert("end", "%-22s: %s\n" % (name, value))
        txt.config(state="disabled")

        close = ttk.Button(self.win, text=_("Close", table),
                           command=self.win.destroy)
        close.pack(pady=6)

        # close on Escape / window close button. Deliberately NOT modal
        # (no grab_set): a grab steals all events and makes automated
        # tests and multi-window workflows flaky. The popup stays on top
        # of the main window via transient() and is cheap to reopen.
        self.win.bind("<Escape>", lambda e: self.win.destroy())
        self.win.protocol("WM_DELETE_WINDOW", self.win.destroy)


def _(text, widget):
    """Tiny translator hook so widgets can reuse the app language."""
    translator = getattr(widget, "_table_tr", None)
    if translator:
        try:
            return translator(text)
        except Exception:
            return text
    return text


class ResultTable(ttk.Treeview):
    """Read-only tabular result widget with zebra striping and sorting.

    Designed for wide result sets (20+ columns, long text cells):

    * every column gets a data-driven width (content sampling) so widths
      are readable without squeezing each other;
    * horizontal scrolling is smooth: mouse-wheel tilt, Shift+wheel,
      Ctrl+wheel horizontal, and an always-visible h-scrollbar;
    * over-long cell texts are elided ("very long te…") - double-click a
      row (or press Enter) to see the full row in a detail popup;
    * click a header to sort, click again to reverse.
    """

    CLIP = 40             # max chars shown in a cell before eliding
    MIN_W = 70            # minimum column width
    MAX_W = 320           # maximum column width
    HEAD_PAD = 34         # header padding allowance

    def __init__(self, parent, **kwargs):
        super().__init__(parent, selectmode="browse", **kwargs)

        self._col_ids = []
        self._columns = []
        self._rows = []
        self._sort_state = {}

        self._vsb = ttk.Scrollbar(parent, orient="vertical", command=self.yview)
        self._hsb = ttk.Scrollbar(parent, orient="horizontal",
                                  command=self.xview)
        self.configure(yscrollcommand=self._vsb.set,
                       xscrollcommand=self._hsb.set)

        self.tag_configure("odd", background=ZEBRA)
        self.tag_configure("muted", foreground=TEXT_MUTED)

        # horizontal wheel support: tilt buttons, Shift+wheel, Ctrl+wheel
        self.bind("<Button-6>", self._h_wheel)
        self.bind("<Button-7>", self._h_wheel)
        self.bind("<Shift-MouseWheel>", self._h_wheel)
        self.bind("<Control-MouseWheel>", self._h_wheel)
        # detail popup
        self.bind("<Double-1>", self._on_detail)
        self.bind("<Return>", self._on_detail)

    # ------------------------------------------------------------------
    # layout helper
    # ------------------------------------------------------------------
    def pack_table(self, **kwargs):
        """Pack the table together with its scrollbars."""
        self._vsb.pack(side="right", fill="y")
        self._hsb.pack(side="bottom", fill="x")
        super().pack(fill="both", expand=True, **kwargs)

    # ------------------------------------------------------------------
    # data loading
    # ------------------------------------------------------------------
    def load(self, columns, rows):
        """Replace contents with (columns, rows)."""
        columns = [str(c) for c in (columns or [])]
        rows = [[None if v is None else v for v in row]
                for row in (rows or [])]

        self._columns = columns
        self._rows = rows
        self._sort_state.clear()

        self._col_ids = [self._safe_col(c) for c in columns]
        # displaycolumns must be reset BEFORE replacing columns: swapping
        # to a different column set while displaycolumns still holds the
        # old ids makes Tk raise 'Invalid column index'
        self["displaycolumns"] = "#all"
        self["columns"] = self._col_ids
        self["displaycolumns"] = self._col_ids

        if self._col_ids:
            self["show"] = "headings"
            widths = self._compute_widths(columns, rows)
            for name, cid, width in zip(columns, self._col_ids, widths):
                self.heading(cid, text=name,
                             command=lambda c=cid: self.sort_by(c, None))
                self.column(cid, width=width, minwidth=width,
                            stretch=False, anchor="w")
        else:
            self["show"] = "tree"

        self._render(rows)
        # new dataset: jump to the left-top corner
        self.xview_moveto(0.0)
        self.yview_moveto(0.0)

    def clear(self):
        self._columns = []
        self._rows = []
        self.delete(*self.get_children())

    # ------------------------------------------------------------------
    # rendering helpers
    # ------------------------------------------------------------------
    def _render(self, rows):
        self.delete(*self.get_children())
        for i, row in enumerate(rows):
            vals = [self._fmt(v) for v in row]
            tag = "odd" if i % 2 else ""
            self.insert("", "end", values=vals, tags=(tag,))

    @classmethod
    def _fmt(cls, value):
        """Cell display text: stringify + elide long values."""
        if value is None:
            return ""
        text = str(value)
        if len(text) > cls.CLIP:
            return text[:cls.CLIP - 1] + "…"
        return text

    def _compute_widths(self, columns, rows, sample=30):
        """Per-column width from header + sampled cell content."""
        widths = []
        n = len(rows)
        step = max(1, n // sample) if n else 1
        for ci, name in enumerate(columns):
            cells = [str(r[ci]) for r in rows[::step] if ci < len(r)]
            longest = max((len(c) for c in cells), default=0)
            text_w = max(len(name), min(longest, self.CLIP))
            widths.append(max(self.MIN_W,
                              min(self.MAX_W, text_w * 7 + self.HEAD_PAD)))
        return widths

    @staticmethod
    def _safe_col(name):
        return "".join(ch for ch in str(name) if ch.isalnum() or ch == "_") or "c"

    # ------------------------------------------------------------------
    # interaction
    # ------------------------------------------------------------------
    def _h_wheel(self, event):
        """Horizontal scrolling: wheel tilt / Shift+wheel / Ctrl+wheel."""
        if event.num == 6:            # tilt left
            self.xview_scroll(-2, "units")
        elif event.num == 7:          # tilt right
            self.xview_scroll(2, "units")
        elif event.delta:
            if event.state & 0x0004:  # Ctrl held -> horizontal zoom-free pan
                self.xview_scroll(2 if event.delta < 0 else -2, "units")
            else:                     # Shift held
                self.xview_scroll(-1 if event.delta > 0 else 1, "units")
        return "break"

    def _on_detail(self, event=None):
        """Double-click / Enter: show the full row in a popup."""
        sel = self.selection()
        if not sel:
            return
        idx = self.index(sel[0])
        if 0 <= idx < len(self._rows):
            values = ["" if v is None else str(v) for v in self._rows[idx]]
            RowDetailPopup(self, self._columns, values)

    def sort_by(self, col, descending=None):
        """Sort the underlying rows by column id `col` and re-render.

        The heading command always passes descending=False, which here
        means "toggle": the first click sorts ascending, the next click
        on the same column reverses. Passing True/False explicitly forces
        a direction (used by tests and programmatic sorts).
        """
        try:
            ci = self._col_ids.index(col)
        except ValueError:
            return
        if descending is None:
            descending = not self._sort_state.get(col, False)
        self._sort_state[col] = descending

        def key(row):
            v = row[ci] if ci < len(row) else None
            if v is None:
                return (1, "")
            if isinstance(v, (int, float)):
                return (0, v)
            return (0, str(v))

        self._rows.sort(key=key, reverse=descending)
        self._render(self._rows)


def install_wheel_horizontal(widget):
    """Attach horizontal wheel scrolling to an arbitrary widget (legacy)."""
    widget.bind("<Shift-MouseWheel>",
                lambda e: widget.xview_scroll(-1 if e.delta > 0 else 1,
                                              "units"))
    return widget
