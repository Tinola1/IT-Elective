"""Small helpers every screen uses: currency + date formatting, labels, buttons, tables."""

import tkinter as tk
from datetime import datetime
from tkinter import ttk

import database as db
from theme import CLAY, CLAY_DEEP, INK, LINE, MUTED


CUR = {"code": "USD"}  # the currency prices are shown in right now


def _cur():
    sym, rate, _ = db.CURRENCIES.get(CUR["code"], db.CURRENCIES["USD"])
    return sym, rate


def money(x):
    """x is in US dollars; shown in the current currency with 2 decimals."""
    sym, rate = _cur()
    return f"{sym}{x * rate:,.2f}"


def money0(x):
    """Same, rounded to whole units."""
    sym, rate = _cur()
    return f"{sym}{x * rate:,.0f}"


def fmt_night(x):
    """A nightly price such as $124 or \u20B17,192."""
    sym, rate = _cur()
    v = x * rate
    if CUR["code"] == "USD":
        return f"{sym}{v:,.2f}".rstrip("0").rstrip(".")
    return f"{sym}{v:,.0f}"


def to_usd(text):
    """Turns what a host typed (in their currency) into dollars. Bad text is passed on so the
    database can show its normal error."""
    sym, rate = _cur()
    try:
        v = float(str(text).strip().replace(sym, "").replace("$", "").replace(",", ""))
    except ValueError:
        return text
    return v / rate


def L(parent, text, size=10, weight="normal", slant="roman", family="Arial", fg=INK, bg=None, **kw):
    """A label that inherits its parent's background."""
    return tk.Label(parent, text=text, font=(family, size, f"{weight} {slant}"), fg=fg,
                    bg=bg or parent.cget("bg"), **kw)


def heading(parent, plain, accent="", size=24, fg=INK, accent_fg=CLAY, wrap=620, anchor="w", justify="left"):
    f = tk.Frame(parent, bg=parent.cget("bg"))
    L(f, plain, size, "bold", family="Georgia", fg=fg, wraplength=wrap, justify=justify).pack(anchor=anchor)
    if accent:
        L(f, accent, size, "bold", "italic", family="Georgia", fg=accent_fg, wraplength=wrap,
          justify=justify).pack(anchor=anchor)
    return f


def link(parent, text, cmd, fg=MUTED, size=10, hover=CLAY, bold=False):
    lb = L(parent, text, size, "bold" if bold else "normal", fg=fg, cursor="hand2")
    lb.bind("<Button-1>", lambda e: cmd())
    lb.bind("<Enter>", lambda e: lb.config(fg=hover))
    lb.bind("<Leave>", lambda e: lb.config(fg=fg))
    return lb


def button(parent, text, command, primary=True, small=False, **kw):
    size, padx = (9, 9) if small else (10, 14)
    if primary:
        return tk.Button(parent, text=text, command=command, bg=CLAY, fg="white",
                         activebackground=CLAY_DEEP, activeforeground="white", relief="flat",
                         font=("Arial", size, "bold"), padx=padx, pady=4, cursor="hand2", **kw)
    return tk.Button(parent, text=text, command=command, bg=LINE, fg=INK,
                     activebackground="#D3C7AA", relief="flat", font=("Arial", size),
                     padx=padx - 2, pady=4, cursor="hand2", **kw)


def make_tree(parent, columns, widths, height=10):
    """Treeview + scrollbar. columns = [(id, heading)]. Returns (frame, tree)."""
    frame = ttk.Frame(parent)
    tree = ttk.Treeview(frame, columns=[c[0] for c in columns], show="headings",
                        height=height, selectmode="browse")
    for (cid, heading_text), w in zip(columns, widths):
        tree.heading(cid, text=heading_text, anchor="w")
        tree.column(cid, width=w, anchor="w")
    sb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)

    def on_scroll(lo, hi):  # only show the scrollbar when the rows don't all fit
        if float(lo) <= 0 and float(hi) >= 1:
            sb.pack_forget()
        elif not sb.winfo_ismapped():
            sb.pack(side="right", fill="y")
        sb.set(lo, hi)

    tree.configure(yscrollcommand=on_scroll)
    tree.pack(side="left", fill="both", expand=True)
    return frame, tree


def selected_id(tree):
    sel = tree.selection()
    return int(sel[0]) if sel else None  # the DB id is stored as the row iid


def clear(tree):
    tree.delete(*tree.get_children())


def fmt_day(s):
    try:
        d = datetime.strptime(s, "%Y-%m-%d")
        return f"{d:%b} {d.day}, {d.year}"
    except (ValueError, TypeError):
        return s or "\u2014"


def fmt_range(ci, co):
    try:
        a, b = datetime.strptime(ci, "%Y-%m-%d"), datetime.strptime(co, "%Y-%m-%d")
    except (ValueError, TypeError):
        return f"{ci} \u2192 {co}"
    if a.year == b.year:
        return f"{a:%b} {a.day} \u2013 {b:%b} {b.day}, {b.year}"
    return f"{fmt_day(ci)} \u2013 {fmt_day(co)}"


def fmt_when(s):
    try:
        d = datetime.fromisoformat(s)
    except (ValueError, TypeError):
        return "\u2014"
    return f"{d:%b} {d.day}, {d.year} at {d:%I:%M %p}".replace(" 0", " ")


def trip_nights(t):
    try:
        return (datetime.strptime(t["check_out"], "%Y-%m-%d") - datetime.strptime(t["check_in"], "%Y-%m-%d")).days
    except ValueError:
        return 1


def booking_ref(t):
    return f"RR-{t['id']:05d}"
