"""The top bar and its dropdown menu (a mixin of RoamRestApp)."""

import tkinter as tk
from tkinter import messagebox

import database as db
from account import AccountWindow, CurrencyWindow
from helpers import L, link
from hosting import HostWindow
from images import avatar_photo
from navigation import front_window
from theme import CLAY, CLAY_DEEP, INK, LINE, MUTED, PAPER, PAPER2, PILL_BG
from toolkit import AdminWindow, PaymentsWindow, PayoutsWindow
from trips import TripsWindow

RED = "#D92D20"  # the notification badge colour


class NavBar:
    """Top bar, avatar circle and dropdown menu."""

    # ----- nav (Airbnb-style: link + avatar + menu)
    def build_nav(self):
        bar = tk.Frame(self.root, bg=PAPER, padx=24, pady=10)
        bar.pack(fill="x")
        self.bar = bar
        brand = L(bar, "\u2229 RoamRest", 18, "bold", family="Georgia", cursor="hand2")
        brand.pack(side="left")
        brand.bind("<Button-1>", lambda e: self.goto("top"))
        links = tk.Frame(bar, bg=PAPER)
        links.pack(side="left", padx=24)
        for text, key in [("Explore", "explore"), ("How it works", "how"), ("Why us", "why"),
                          ("Reviews", "reviews"), ("FAQ", "faq")]:
            link(links, text, lambda k=key: self.goto(k)).pack(side="left", padx=8)
        self.nav = tk.Frame(bar, bg=PAPER)
        self.nav.pack(side="right")
        self.rule_root = tk.Frame(self.root, bg=LINE, height=1)
        self.rule_root.pack(fill="x")
        self.menu = None
        self.toggles = []
        self.root.bind_all("<Button-1>", self.menu_outside_click, add="+")
        self.root.bind("<Escape>", lambda e: self.close_menu())
        self.trip_alerts = 0
        self.root.after(4000, self._trip_poll)

    def circle(self, parent, text, bg, fg, font, command, photo=None, tip=None):
        size = 38
        cv = tk.Canvas(parent, width=size, height=size, bg=parent.cget("bg"),
                       highlightthickness=0, cursor="hand2")
        if photo is not None:
            cv.photo = photo  # keep a reference or Tk drops the picture
            cv.create_image(size // 2, size // 2, image=photo)
        else:
            cv.create_oval(1, 1, size - 1, size - 1, fill=bg, outline="")
            cv.create_text(size // 2, size // 2, text=text, fill=fg, font=font)
        cv.bind("<Button-1>", lambda e: command())
        if tip:  # no highlight on hover, only the name appears under it
            cv.bind("<Enter>", lambda e: self.show_tip(cv, tip))
            cv.bind("<Leave>", lambda e: self.hide_tip())
        return cv

    def show_tip(self, widget, text):
        self.hide_tip()
        lbl = tk.Label(self.root, text=text, bg=INK, fg=PAPER, font=("Arial", 9), padx=8, pady=3)
        x = widget.winfo_rootx() - self.root.winfo_rootx() + widget.winfo_width() // 2
        y = widget.winfo_rooty() - self.root.winfo_rooty() + widget.winfo_height() + 4
        lbl.update_idletasks()
        x = min(x, self.root.winfo_width() - lbl.winfo_reqwidth() // 2 - 8)
        lbl.place(x=x, y=y, anchor="n")
        lbl.lift()
        self.tip = lbl

    def hide_tip(self):
        if self.tip is not None:
            self.tip.destroy()
            self.tip = None

    def refresh_nav(self):
        for w in self.nav.winfo_children():
            w.destroy()
        self.hide_tip()
        self.close_menu()
        u = self.user
        self.unread = db.unread_count(u["id"]) if u and u["role"] != "admin" else 0
        self.pending = db.host_pending_count(u["id"]) if u and u["role"] == "host" else 0
        self.trip_alerts = db.unseen_trip_count(u["id"]) if u and u["role"] != "admin" else 0
        if u is None or u["role"] == "guest":
            link(self.nav, "Become a host", self.start_hosting, fg=INK, bold=True).pack(
                side="left", padx=(0, 14))
        elif u["role"] == "host":
            text = "Switch to hosting" + (f" ({self.pending})" if self.pending else "")
            link(self.nav, text, lambda: self._open("host", HostWindow), fg=INK, bold=True).pack(
                side="left", padx=(0, 14))
        if self.unread:
            link(self.nav, f"\u2709 {self.unread}", self.open_messages, fg=CLAY, bold=True).pack(
                side="left", padx=(0, 12))
        avatar = self.circle(self.nav, u["name"][:1].upper() if u else "\u263A", PILL_BG, CLAY_DEEP,
                             ("Arial", 13, "bold") if u else ("Segoe UI Symbol", 14),
                             self.open_profile if u else self.open_auth,
                             photo=avatar_photo(u, 38), tip=u["name"] if u else "Log in")
        avatar.pack(side="left", padx=(0, 8))
        burger = self.circle(self.nav, "\u2261", "#EDE6D6", INK, ("Arial", 16, "bold"), self.toggle_menu)
        burger.pack(side="left")
        self.toggles = [burger]
        if self.trip_alerts:  # a red number on the menu button: a host confirmed one of your trips
            n = self.trip_alerts
            burger.create_oval(19, 1, 37, 19, fill=RED, outline=PAPER, width=2)
            burger.create_text(28, 10, text=str(n) if n < 10 else "9+", fill="white",
                               font=("Arial", 8 if n < 10 else 7, "bold"))
            burger.bind("<Enter>", lambda e: self.show_tip(
                burger, f"{n} confirmed trip{'s' if n != 1 else ''} to look at"))
            burger.bind("<Leave>", lambda e: self.hide_tip())

    def _trip_poll(self):
        """Every few seconds: has a host confirmed a booking since the last look? Then show the red number."""
        try:
            u = self.user
            if u and u["role"] != "admin" and self.menu is None:
                if db.unseen_trip_count(u["id"]) != self.trip_alerts:
                    self.refresh_nav()
                    self.refresh_trips()
        except Exception:  # never let a hiccup stop the check
            pass
        self.root.after(4000, self._trip_poll)

    # ----- the dropdown menu
    def toggle_menu(self):
        if self.menu is not None:
            self.close_menu()
        else:
            self.open_menu()

    def close_menu(self):
        if self.menu is not None:
            self.menu.destroy()
            self.menu = None

    def menu_outside_click(self, e):
        if self.menu is None:
            return
        w, m = str(e.widget), str(self.menu)
        if w == m or w.startswith(m + ".") or any(w == str(t) for t in self.toggles):
            return
        self.close_menu()

    def soon(self, name):
        messagebox.showinfo("Coming soon", f"{name} isn't available in this version yet.", parent=front_window() or self.root)

    def open_menu(self):
        u = self.user
        WHITE = "#FFFFFF"
        m = self.menu = tk.Frame(self.root, bg=WHITE, highlightbackground=LINE, highlightthickness=1)
        tk.Frame(m, bg=WHITE, width=300, height=1).pack()

        def hookup(widgets, row, run):
            def paint(color):
                for w in widgets:
                    w.config(bg=color)
            for w in widgets:
                w.bind("<Button-1>", lambda e: (self.close_menu(), run()))
                w.bind("<Enter>", lambda e: paint(PAPER2))
                w.bind("<Leave>", lambda e: paint(WHITE))

        def item(icon, text, cmd, bold=False, badge=0):
            row = tk.Frame(m, bg=WHITE, cursor="hand2", padx=16, pady=8)
            row.pack(fill="x")
            ic = tk.Label(row, text=icon, width=2, font=("Segoe UI Symbol", 12), bg=WHITE, fg=INK)
            tx = tk.Label(row, text=text, font=("Arial", 10, "bold" if bold else "normal"), bg=WHITE,
                          fg=INK, cursor="hand2")
            ic.pack(side="left")
            tx.pack(side="left", padx=(8, 0))
            hookup([row, ic, tx], row, cmd)
            if badge:  # a red number that keeps its colour when the row is hovered
                bd = tk.Label(row, text=str(badge) if badge < 10 else "9+", bg=RED, fg="white",
                              font=("Arial", 8, "bold"), padx=6, cursor="hand2")
                bd.pack(side="right")
                bd.bind("<Button-1>", lambda e: (self.close_menu(), cmd()))

        def rule():
            tk.Frame(m, bg=LINE, height=1).pack(fill="x", padx=14, pady=6)

        def host_card(cmd):
            row = tk.Frame(m, bg=WHITE, cursor="hand2", padx=16, pady=10)
            row.pack(fill="x")
            col = tk.Frame(row, bg=WHITE, cursor="hand2")
            col.pack(side="left")
            t1 = tk.Label(col, text="Become a host", font=("Arial", 10, "bold"), bg=WHITE, fg=INK,
                          cursor="hand2")
            t1.pack(anchor="w")
            t2 = tk.Label(col, text="It's easy to start hosting and\nearn extra income.", font=("Arial", 9),
                          bg=WHITE, fg=MUTED, justify="left", cursor="hand2")
            t2.pack(anchor="w")
            ic = tk.Label(row, text="\u2302", font=("Arial", 28), bg=WHITE, fg=CLAY, cursor="hand2")
            ic.pack(side="right")
            hookup([row, col, t1, t2, ic], row, cmd)

        lang = lambda: self._open("lang", CurrencyWindow)
        if u is None:
            item("\u263A", "Log in / Sign up", self.open_auth, True)
            rule()
            host_card(self.start_hosting)
            rule()
            item("?", "Help Center", lambda: self.goto("faq"))
            item("\u25CD", "Languages & currency", lang)
            item("\u2740", "Gift cards", lambda: self.soon("Gift cards"))
        else:
            item("\u2661", f"Wishlists ({len(self.favs)})", self.fav_click)
            item("\u2708", "Trips", lambda: self._open("trips", TripsWindow), badge=self.trip_alerts)
            if u["role"] != "admin":
                item("\u2709", "Messages" + (f" ({self.unread})" if self.unread else ""), self.open_messages)
            item("\u263A", "Profile", self.open_profile)
            if u["role"] != "admin":
                item("\u25A4", "Payments", lambda: self._open("payments", PaymentsWindow))
            rule()
            item("\u2699", "Account settings", lambda: self._open("account", AccountWindow))
            item("\u25CD", "Languages & currency", lang)
            item("?", "Help Center", lambda: self.goto("faq"))
            rule()
            if u["role"] == "guest":
                host_card(self.start_hosting)
            elif u["role"] == "host":
                item("\u2302", "Hosting" + (f" ({self.pending})" if self.pending else ""),
                     lambda: self._open("host", HostWindow), True)
                item("\u25A6", "Earnings & payouts", lambda: self._open("payouts", PayoutsWindow))
            else:
                item("\u2302", "Admin dashboard", lambda: self._open("admin", AdminWindow), True)
            item("\u2740", "Gift cards", lambda: self.soon("Gift cards"))
            rule()
            item("\u21AA", "Log out", self.logout)

        self.root.update_idletasks()
        y = self.bar.winfo_height() + self.rule_root.winfo_height() + 4
        m.place(relx=1.0, x=-24, y=y, anchor="ne")
        m.lift()