"""One window at a time: the Nav stack, the Page base class with its Back bar, front_window()."""

import functools
import re
import tkinter as tk

from theme import CARD, INK, LINE, MUTED, PAPER2


NAV = None  # the Nav instance, created by RoamRestApp


class Nav:
    """Keeps exactly one RoamRest window on screen.

    Opening a page hides the page under it and puts a Back bar at the top of the new one. Back (or the
    window's X button, or Esc where a page has it) closes the page and shows the one before it again.
    """

    def __init__(self, root):
        global NAV
        NAV = self
        self.root = root
        self.stack = [root]
        self.frame = ("normal", "")  # state + position/size of the last window you looked at
        root.bind("<Configure>", lambda e: e.widget is root and self.remember(root), add="+")

    # ----- bookkeeping
    def remember(self, w):
        try:
            self.frame = (w.state(), w.geometry())
        except tk.TclError:
            pass

    @staticmethod
    def name(w):
        try:
            if isinstance(w, tk.Tk):
                return "Home"
            t = w.title() or "Page"
        except tk.TclError:
            return "Page"
        return t if len(t) <= 26 else t[:25] + "\u2026"

    def alive(self, w):
        try:
            return bool(w.winfo_exists())
        except tk.TclError:
            return False

    # ----- opening
    def push(self, page):
        prev = self.stack[-1]
        self.stack.append(page)
        self.add_bar(page)
        state, geo = self.frame
        m = re.match(r"(\d+)x(\d+)", geo or "")
        if state == "zoomed":
            try:
                page.state("zoomed")
            except tk.TclError:
                try:
                    page.attributes("-zoomed", True)
                except tk.TclError:
                    pass
        elif m and int(m.group(1)) > 300 and int(m.group(2)) > 300:
            page.geometry(geo)  # open exactly where (and as big as) the window it replaces
        page.bind("<Configure>", lambda e: e.widget is page and self.remember(page), add="+")
        try:
            if prev.winfo_exists():
                prev.withdraw()
        except tk.TclError:
            pass
        page.deiconify()
        page.lift()
        page.focus_force()

    def add_bar(self, page):
        bar = tk.Frame(page, bg=PAPER2)
        row = tk.Frame(bar, bg=PAPER2, padx=14, pady=8)
        row.pack(fill="x")
        back = tk.Button(row, text="\u2190  Back", command=page.destroy, relief="flat", bd=0, bg=CARD, fg=INK,
                         activebackground=LINE, activeforeground=INK, font=("Arial", 10, "bold"), padx=14, pady=5,
                         cursor="hand2", highlightthickness=1, highlightbackground=LINE)
        back.pack(side="left")
        back.bind("<Enter>", lambda e: back.config(bg=LINE))
        back.bind("<Leave>", lambda e: back.config(bg=CARD))
        trail = "  \u203A  ".join(self.name(w) for w in self.stack[-3:])
        tk.Label(row, text=trail, bg=PAPER2, fg=MUTED, font=("Arial", 9)).pack(side="left", padx=(14, 0))
        tk.Frame(bar, bg=LINE, height=1).pack(fill="x", side="bottom")
        packed, gridded = page.pack_slaves(), page.grid_slaves()
        if gridded and not packed:  # shift the page's own grid down one row to make room
            cols, rows = page.grid_size()
            for w in gridded:
                w.grid_configure(row=int(w.grid_info()["row"]) + 1)
            for r in range(rows - 1, -1, -1):
                cfg = page.grid_rowconfigure(r)
                page.grid_rowconfigure(r + 1, weight=cfg["weight"], minsize=cfg["minsize"], pad=cfg["pad"])
            page.grid_rowconfigure(0, weight=0, minsize=0, pad=0)
            bar.grid(row=0, column=0, columnspan=max(cols, 1), sticky="ew")
        elif packed:
            bar.pack(side="top", fill="x", before=packed[0])
        else:
            bar.pack(side="top", fill="x")
        page.back_bar = bar
        page.bind("<Alt-Left>", lambda e: page.destroy(), add="+")

    # ----- closing / jumping
    def closed(self, page):
        if page in self.stack:
            self.stack.remove(page)
        try:
            self.root.after_idle(self.reveal)
        except tk.TclError:
            pass

    def reveal(self):
        self.stack = [w for w in self.stack if w is self.root or self.alive(w)]
        top = self.stack[-1]
        try:
            if top.state() == "withdrawn":
                top.deiconify()
            top.lift()
            top.focus_force()
        except tk.TclError:
            pass

    def goto(self, page):
        """Bring an already-open page to the front, closing whatever was opened on top of it."""
        if page in self.stack:
            for p in reversed(self.stack[self.stack.index(page) + 1:]):
                if self.alive(p):
                    p.destroy()
        self.reveal()


class Page(tk.Toplevel):
    """A full-screen page: starts hidden, shows itself once built, hides the page beneath it (see Nav)."""

    def __init_subclass__(cls, **kw):
        super().__init_subclass__(**kw)
        init = cls.__dict__.get("__init__")
        if init is None:
            return

        @functools.wraps(init)
        def wrapped(self, *a, **k):
            init(self, *a, **k)  # the page builds its own content...
            if type(self) is cls and self.winfo_exists():  # ...then Nav puts it on screen
                if NAV is None:
                    self.deiconify()
                else:
                    NAV.push(self)
        cls.__init__ = wrapped

    def __init__(self, master=None, **kw):
        super().__init__(master, **kw)
        self.withdraw()
        self.protocol("WM_DELETE_WINDOW", self.destroy)  # the X button goes back too
        self.bind("<Destroy>", self._gone, add="+")

    def _gone(self, e):
        if e.widget is self and NAV is not None:
            NAV.closed(self)


def front_window():
    """The window currently on screen. Popups attach to this one (not to the hidden main window)."""
    return NAV.stack[-1] if NAV is not None and NAV.stack else None
