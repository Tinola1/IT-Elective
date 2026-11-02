"""notifications.py - the admin's notification bell.

Instead of a pop-up asking "N guests are asking to become a host", an admin now sees a bell in the top bar with
a red badge showing how many host requests are waiting. Clicking the bell opens a notification panel that lists
every request (who, when) and a button that opens the admin dashboard on the Users tab, filtered to guests.

It is a mixin for the main window:   class RoamRestApp(AdminNotifications, NavBar, LandingPage): ...
It only relies on what app.py already uses: db.host_requests(), self.nav (the right-hand part of the top bar),
self.open_admin() and the dashboard's go("users", "guest"). If any of these is missing it degrades quietly.
"""
import sys
import tkinter as tk
from datetime import datetime
from tkinter import messagebox

import database as db

try:  # use the app's palette when it is available
    import theme as _theme
except ImportError:  # pragma: no cover
    _theme = None


def _color(name, default):
    return getattr(_theme, name, default)


PAPER, PAPER2, CARD = _color("PAPER", "#F4EEE1"), _color("PAPER2", "#FAF5E9"), _color("CARD", "#FFFDF6")
INK, MUTED, LINE = _color("INK", "#232015"), _color("MUTED", "#6B6353"), _color("LINE", "#E1D7C0")
CLAY, CLAY_DEEP, PILL_BG = _color("CLAY", "#B44A1E"), _color("CLAY_DEEP", "#8F3A13"), _color("PILL_BG", "#F0DDD0")
WHITE, RED, CIRCLE = "#FFFFFF", "#D92D20", "#EDE6D6"
PANEL_W, ROW_H, MAX_ROWS = 400, 74, 5


def _get(row, *keys, default=""):
    """First non-empty value among `keys` for a sqlite Row or dict (a missing column is fine)."""
    for k in keys:
        try:
            v = row[k]
        except (KeyError, IndexError, TypeError):
            continue
        if v not in (None, ""):
            return v
    return default


def _ago(text):
    try:
        d = datetime.fromisoformat(str(text))
    except (ValueError, TypeError):
        return ""
    secs = (datetime.now() - d).total_seconds()
    if secs < 90:
        return "just now"
    if secs < 3600:
        return f"{int(secs // 60)} min ago"
    if secs < 86400:
        h = int(secs // 3600)
        return f"{h} hour{'s' if h != 1 else ''} ago"
    if secs < 86400 * 7:
        n = int(secs // 86400)
        return f"{n} day{'s' if n != 1 else ''} ago"
    return f"{d:%b} {d.day}, {d.year}"


def _label(parent, text, size=10, weight="normal", fg=INK, bg=None, family="Arial", **kw):
    return tk.Label(parent, text=text, font=(family, size, weight), fg=fg, bg=bg or parent.cget("bg"), **kw)


def draw_bell(cv, count, bg=CIRCLE):
    """A bell with a red number badge, drawn with plain canvas shapes (no image files needed)."""
    cv.delete("all")
    cv.create_oval(1, 1, 37, 37, fill=bg, outline="")
    cv.create_oval(17.2, 7, 20.8, 10.6, fill=INK, outline="")                      # top knob
    cv.create_polygon(19, 9.5, 23.2, 11, 25.6, 14.5, 26, 19.5, 26.8, 23.2, 29.6, 25.6, 29.6, 27.4,
                      8.4, 27.4, 8.4, 25.6, 11.2, 23.2, 12, 19.5, 12.4, 14.5, 14.8, 11,
                      smooth=True, fill=INK, outline=INK, width=1)                  # the bell
    cv.create_oval(16.4, 28.3, 21.6, 32.2, fill=INK, outline="")                   # clapper
    if count:
        text = str(count) if count < 10 else "9+"
        cv.create_oval(19.5, -1, 37.5, 17, fill=RED, outline=bg, width=2)
        cv.create_text(28.5, 8, text=text, fill=WHITE, font=("Arial", 8 if count < 10 else 7, "bold"))


class AdminNotifications:
    """Mixin for the main window. Adds the bell for admins and removes the old pop-up."""

    _bell = None
    _bell_panel = None
    _bell_count = 0
    _bell_job = None
    _bell_wired = False
    _bell_tip_widget = None

    # ----- data
    def host_request_rows(self):
        try:
            return list(db.host_requests())
        except Exception:
            return []

    def is_admin(self):
        u = getattr(self, "user", None)
        return bool(u) and u.get("role") == "admin"

    # ----- the bell in the top bar
    def refresh_nav(self):
        super().refresh_nav()  # the normal bar: avatar, menu button, ...
        self.paint_bell()

    def paint_bell(self):
        if self._bell is not None:
            try:
                self._bell.destroy()
            except tk.TclError:
                pass
            self._bell = None
        if not self.is_admin():
            self.close_bell_panel()
            return
        self._bell_count = len(self.host_request_rows())
        bell = tk.Canvas(getattr(self, "nav", None) or self.root, width=38, height=38,
                         bg=(getattr(self, "nav", None) or self.root).cget("bg"), highlightthickness=0, cursor="hand2")
        draw_bell(bell, self._bell_count)
        bell.bind("<Button-1>", lambda e: self.toggle_bell_panel())
        bell.bind("<Enter>", lambda e: self._bell_hover(True))
        bell.bind("<Leave>", lambda e: self._bell_hover(False))
        nav = getattr(self, "nav", None)
        if nav is not None:
            kids = [k for k in nav.winfo_children() if k is not bell]
            if kids:
                bell.pack(side="left", padx=(0, 10), before=kids[0])
            else:
                bell.pack(side="left", padx=(0, 10))
        else:  # no right-hand container to join: float it just left of the avatar
            bell.place(relx=1.0, x=-122, y=8, anchor="ne")
        self._bell = bell
        self._wire_bell()
        if self._bell_job is None:
            self._bell_job = self.root.after(4000, self._bell_poll)

    def _bell_hover(self, on):
        tip = getattr(self, "show_tip", None)
        hide = getattr(self, "hide_tip", None)
        if on and tip and self._bell is not None:
            n = self._bell_count
            tip(self._bell, f"{n} host request{'s' if n != 1 else ''}" if n else "No new requests")
        elif hide:
            hide()

    def _bell_poll(self):
        """Keep the badge fresh while an admin is signed in (requests can arrive at any time)."""
        self._bell_job = None
        if not self.is_admin():
            return
        n = len(self.host_request_rows())
        if n != self._bell_count:
            self._bell_count = n
            if self._bell is not None:
                draw_bell(self._bell, n)
            if self._bell_panel is not None:
                self.open_bell_panel()  # re-draw the open panel with the new list
        self._bell_job = self.root.after(4000, self._bell_poll)

    # ----- the old pop-up is gone; anything that still calls it just refreshes the bell
    def admin_prompt(self):
        self.paint_bell()

    # ----- the panel
    def _wire_bell(self):
        if self._bell_wired:
            return
        self._bell_wired = True
        self.root.bind("<Button-1>", self._bell_outside_click, add="+")
        self.root.bind("<Escape>", lambda e: self.close_bell_panel(), add="+")

    def _bell_outside_click(self, e):
        p = self._bell_panel
        if p is None:
            return
        w = str(e.widget)
        if w == str(p) or w.startswith(str(p) + ".") or (self._bell is not None and w == str(self._bell)):
            return
        self.close_bell_panel()

    def toggle_bell_panel(self):
        if self._bell_panel is not None:
            self.close_bell_panel()
        else:
            self.open_bell_panel()

    def close_bell_panel(self):
        if self._bell_panel is not None:
            try:
                self._bell_panel.destroy()
            except tk.TclError:
                pass
            self._bell_panel = None

    def open_bell_panel(self):
        self.close_bell_panel()
        hide = getattr(self, "hide_tip", None)
        if hide:
            hide()
        close_menu = getattr(self, "close_menu", None)
        if close_menu:
            close_menu()
        rows = self.host_request_rows()
        self._bell_count = len(rows)
        if self._bell is not None:
            draw_bell(self._bell, self._bell_count)

        p = self._bell_panel = tk.Frame(self.root, bg=WHITE, highlightbackground=LINE, highlightthickness=1)
        tk.Frame(p, bg=WHITE, width=PANEL_W, height=1).pack()

        head = tk.Frame(p, bg=WHITE, padx=18, pady=14)
        head.pack(fill="x")
        _label(head, "Notifications", 14, "bold", family="Georgia").pack(side="left")
        if rows:
            _label(head, f" {len(rows)} NEW ", 8, "bold", fg=WHITE, bg=RED).pack(side="right")
        tk.Frame(p, bg=LINE, height=1).pack(fill="x")

        if not rows:
            empty = tk.Frame(p, bg=WHITE, pady=30)
            empty.pack(fill="x")
            ring = tk.Canvas(empty, width=52, height=52, bg=WHITE, highlightthickness=0)
            ring.pack()
            ring.create_oval(2, 2, 50, 50, fill=PAPER2, outline=LINE)
            ring.create_text(26, 27, text="\u2713", fill=CLAY, font=("Arial", 20, "bold"))
            _label(empty, "You're all caught up", 12, "bold", family="Georgia").pack(pady=(12, 2))
            _label(empty, "New host requests will show up here.", 9, fg=MUTED).pack()
        else:
            _label(p, "HOST REQUESTS", 8, "bold", fg=CLAY, padx=18).pack(anchor="w", pady=(12, 4))
            holder = tk.Frame(p, bg=WHITE)
            holder.pack(fill="x")
            if len(rows) > MAX_ROWS:  # scroll inside the panel when there are many
                cv = tk.Canvas(holder, bg=WHITE, highlightthickness=0, width=PANEL_W - 2, height=ROW_H * MAX_ROWS)
                cv.pack(side="left", fill="x")
                inner = tk.Frame(cv, bg=WHITE)
                cv.create_window((0, 0), window=inner, anchor="nw", width=PANEL_W - 2)
                inner.bind("<Configure>", lambda e: cv.configure(scrollregion=cv.bbox("all")))
                scroll = lambda e: (cv.yview_scroll(int(-e.delta / 120) or (-1 if e.delta > 0 else 1), "units"), "break")[1]
                cv.bind("<MouseWheel>", scroll)
            else:
                inner, scroll = holder, None
            for r in rows:
                self._request_row(inner, r, scroll)
            if scroll:
                for w in self._all_children(inner):
                    w.bind("<MouseWheel>", scroll)

        tk.Frame(p, bg=LINE, height=1).pack(fill="x", pady=(4, 0))
        foot = tk.Frame(p, bg=WHITE, padx=18, pady=14)
        foot.pack(fill="x")
        tk.Button(foot, text="Review all requests" if rows else "Open admin dashboard",
                  command=self.open_host_requests, bg=CLAY if rows else LINE, fg=WHITE if rows else INK,
                  activebackground=CLAY_DEEP if rows else "#D3C7AA", activeforeground=WHITE if rows else INK,
                  relief="flat", font=("Arial", 10, "bold"), pady=8, cursor="hand2").pack(fill="x")

        self.root.update_idletasks()
        bar, rule = getattr(self, "bar", None), getattr(self, "rule_root", None)
        y = (bar.winfo_height() if bar else 50) + (rule.winfo_height() if rule else 1) + 4
        p.place(relx=1.0, x=-24, y=y, anchor="ne")
        p.lift()

    @staticmethod
    def _all_children(w):
        for c in w.winfo_children():
            yield c
            yield from AdminNotifications._all_children(c)

    def _request_row(self, parent, r, scroll=None):
        name = str(_get(r, "name", "full_name", default="A guest"))
        email = str(_get(r, "email", default=""))
        when = _ago(_get(r, "host_requested_at", "requested_at", "host_request_at", "created_at"))
        row = tk.Frame(parent, bg=WHITE, padx=18, pady=10, cursor="hand2")
        row.pack(fill="x")
        av = tk.Canvas(row, width=42, height=42, bg=WHITE, highlightthickness=0, cursor="hand2")
        av.create_oval(1, 1, 41, 41, fill=PILL_BG, outline="")
        av.create_text(21, 21, text=name[:1].upper() or "?", fill=CLAY_DEEP, font=("Arial", 15, "bold"))
        av.pack(side="left")
        text = tk.Frame(row, bg=WHITE, cursor="hand2")
        text.pack(side="left", padx=12, fill="x", expand=True)
        a = _label(text, name, 10, "bold", cursor="hand2", anchor="w")
        a.pack(anchor="w")
        b = _label(text, "wants to become a host" + (f"  \u00B7  {when}" if when else ""), 9, fg=CLAY,
                   cursor="hand2", anchor="w")
        b.pack(anchor="w")
        c = _label(text, email, 9, fg=MUTED, cursor="hand2", anchor="w")
        c.pack(anchor="w")
        arrow = _label(row, "\u203A", 18, "bold", fg=MUTED, cursor="hand2")
        arrow.pack(side="right")
        parts = [row, av, text, a, b, c, arrow]

        def paint(color):
            for w in parts:
                w.config(bg=color)
        for w in parts:
            w.bind("<Enter>", lambda e: paint(PAPER2))
            w.bind("<Leave>", lambda e: paint(WHITE))
            w.bind("<Button-1>", lambda e: self.open_host_requests())
            if scroll:
                w.bind("<MouseWheel>", scroll)

    # ----- open the dashboard on the requests
    def open_host_requests(self):
        self.close_bell_panel()
        opener = getattr(self, "open_admin", None)
        if opener is None:  # find the admin window class wherever the app keeps it
            for mod in list(sys.modules.values()):
                cls = getattr(mod, "AdminWindow", None)
                if isinstance(cls, type):
                    opener = lambda cls=cls: self._open("admin", cls)
                    break
        if opener is None:
            return messagebox.showinfo(
                "Host requests", "Open the admin dashboard from the menu, then go to Users and choose the "
                                 "'guest' filter.", parent=self.root)
        opener()
        for w in list(getattr(self, "child", {}).values()):  # jump to the Users tab, filtered to guests (a pending host request is still a guest)
            if w.winfo_exists() and hasattr(w, "go") and hasattr(w, "filters"):
                w.go("users", "guest")