# -*- coding: utf-8 -*-
"""
theme.py - centralized ttk theme (colors + styles), borrowed from the
preprod tools stack so both applications share one visual language.

apply_theme(root) configures a clam-based ttk.Style and returns it.
"""

import tkinter as tk
from tkinter import ttk

PRIMARY = "#0056b3"
PRIMARY_HOVER = "#004085"
SUCCESS = "#28a745"
SUCCESS_HOVER = "#218838"
DANGER = "#dc3545"
DANGER_HOVER = "#c82333"
BACKGROUND = "#f8f9fa"
SURFACE = "#ffffff"
TEXT_MAIN = "#212529"
TEXT_MUTED = "#6c757d"
ZEBRA = "#f1f3f5"

FONT_MAIN = ("Segoe UI", 10)
FONT_BOLD = ("Segoe UI", 10, "bold")
FONT_MUTED = ("Segoe UI", 9, "italic")
FONT_CONSOLE = ("Consolas", 9)
FONT_TABLE = ("Consolas", 9)


def apply_theme(root):
    """Apply the application-wide clam-based theme. Returns the ttk.Style."""
    style = ttk.Style(root)
    style.theme_use("clam")

    root.configure(bg=BACKGROUND)

    style.configure(".", background=BACKGROUND, foreground=TEXT_MAIN,
                    font=FONT_MAIN)

    # Notebook / Tabs
    style.configure("TNotebook", background=BACKGROUND, borderwidth=0)
    style.configure("TNotebook.Tab", background="#e9ecef", foreground=TEXT_MAIN,
                    padding=[16, 8], font=FONT_BOLD)
    style.map("TNotebook.Tab",
              background=[("selected", SURFACE), ("active", "#dee2e6")],
              foreground=[("selected", PRIMARY)])

    # LabelFrame
    style.configure("TLabelframe", background=SURFACE, relief="solid",
                    borderwidth=1, bordercolor="#dee2e6", padding=12)
    style.configure("TLabelframe.Label", background=SURFACE,
                    foreground=PRIMARY, font=FONT_BOLD)

    # Buttons
    style.configure("TButton", font=FONT_BOLD, padding=[12, 6],
                    background=PRIMARY, foreground="white")
    style.map("TButton",
              background=[("disabled", "#e9ecef"), ("active", PRIMARY_HOVER)],
              foreground=[("disabled", "#adb5bd")])

    style.configure("Success.TButton", background=SUCCESS, foreground="white")
    style.map("Success.TButton", background=[("active", SUCCESS_HOVER)])

    style.configure("Danger.TButton", background=DANGER, foreground="white")
    style.map("Danger.TButton", background=[("active", DANGER_HOVER)])

    # Segmented toggle ("TableSwitcher.TButton" used for blacklist/whitelist)
    style.configure("Toggle.TButton", padding=[10, 4])
    style.map("Toggle.TButton",
              background=[("selected", PRIMARY), ("active", "#dee2e6"),
                          ("!selected", "#e9ecef")],
              foreground=[("selected", "white"), ("!selected", TEXT_MAIN)])

    # Entries & Comboboxes
    style.configure("TEntry", padding=6)
    style.configure("TCombobox", padding=6)

    # Labels
    style.configure("TLabel", background=SURFACE, foreground=TEXT_MAIN)
    style.configure("Muted.TLabel", background=SURFACE,
                    foreground=TEXT_MUTED, font=FONT_MUTED)

    # Treeview (result tables)
    style.configure("Treeview", background=SURFACE, foreground=TEXT_MAIN,
                    fieldbackground=SURFACE, font=FONT_TABLE, rowheight=22)
    style.configure("Treeview.Heading", font=FONT_BOLD, padding=[4, 6])
    style.map("Treeview", background=[("selected", "#cfe2ff")])

    return style
