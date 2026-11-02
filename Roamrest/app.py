"""RoamRest - 100% tkinter app. Run:  python app.py   (needs: pip install pillow  - for photos)

This file holds the main window (RoamRestApp). The rest lives in:
  core/      theme / content / helpers / images / navigation / toolkit
  screens/   navbar / landing / stay_page / wishlist / trips / messages / hosting / account
  features/  extras / payments / datepicker
  database.py  data layer"""

import os
import sys

# Make the sub-folders importable by plain module name (e.g. `import theme`).
_BASE = os.path.dirname(os.path.abspath(__file__))
for _folder in ("core", "features", "screens"):
    _path = os.path.join(_BASE, _folder)
    if _path not in sys.path:
        sys.path.insert(0, _path)
if _BASE not in sys.path:
    sys.path.insert(0, _BASE)

import tkinter as tk
from tkinter import messagebox
from tkinter import ttk

import database as db
import extras
import navigation
import toolkit  # noqa: F401  (loads the admin, payment and calendar screens)
from account import AuthDialog, ProfileWindow
from helpers import CUR
from hosting import HostWindow
from images import Photos
from landing import LandingPage
from messages import MessagesWindow
from navbar import NavBar
from notifications import AdminNotifications
from navigation import Nav, Page, front_window
from stay_page import StayPage
from theme import CLAY, INK, PAPER, apply_theme
from wishlist import FavoritesWindow


class RoamRestApp(AdminNotifications, NavBar, LandingPage):
    """The main window: state, accounts, favourites and opening the other pages."""

    def __init__(self, root):
        self.root = root
        self.user = None
        self.favs = set()
        self.child = {}
        self.current = []
        self.hearts = {}
        self.chips = {}
        self.anchors = {}
        self.faq_items = []
        self.cat = "All"
        self.nights = 2
        self.unread = 0
        self.pending = 0
        self.tip = None
        apply_theme(root)
        Nav(root)
        self.photos = Photos(root)
        root.title("RoamRest - Stay like you belong")
        root.geometry("1240x800")
        root.minsize(1150, 600)
        root.configure(bg=PAPER)

        self.build_nav()
        wrap = tk.Frame(root, bg=PAPER)
        wrap.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(wrap, bg=PAPER, highlightthickness=0)
        sb = ttk.Scrollbar(wrap, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.page = tk.Frame(self.canvas, bg=PAPER)
        self.win = self.canvas.create_window((0, 0), window=self.page, anchor="nw")
        self.page.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfig(self.win, width=e.width))
        root.bind_all("<MouseWheel>", self._wheel)

        self.build_hero()
        self.build_trust()
        self.build_how()
        self.build_stays()
        self.build_why()
        self.build_reviews()
        self.build_host()
        self.build_faq()
        self.build_cta()
        self.build_footer()

        self.refresh_nav()
        self.run_search()

    def start_hosting(self):
        u = self.user
        if u is None:
            messagebox.showinfo("Log in", "Please log in or sign up to start hosting.", parent=front_window() or self.root)
            return self.open_auth()
        self.reload_user()  # pick up a decision the admin made since the last login
        u = self.user
        if u["role"] == "admin":
            return messagebox.showinfo("Hosting", "Admin accounts can't host.", parent=front_window() or self.root)
        if u["role"] == "guest":
            return self.become_host()
        self._open("host", HostWindow)

    # ----- favorites
    def paint_heart(self, lid):
        b = self.hearts.get(lid)
        if b is not None and b.winfo_exists():
            on = lid in self.favs
            b.config(text="\u2665" if on else "\u2661", fg=CLAY if on else INK)

    def reload_favs(self):
        self.favs = set(db.favorite_ids(self.user["id"])) if self.user else set()
        for lid in list(self.hearts):
            self.paint_heart(lid)
        self.refresh_nav()
        for key, meth in (("favs", "refresh"), ("stay", "refresh_heart")):
            w = self.child.get(key)
            if w is not None and w.winfo_exists():
                getattr(w, meth)()

    def toggle_fav(self, lid):
        if not self.user:
            messagebox.showinfo("Log in", "Please log in or sign up to save favorites.", parent=front_window() or self.root)
            return self.open_auth()
        try:
            db.toggle_favorite(self.user["id"], lid)
        except db.AppError as e:
            return messagebox.showerror("Favorites", str(e), parent=front_window() or self.root)
        self.reload_favs()

    def fav_click(self):
        if not self.user:
            messagebox.showinfo("Log in", "Log in to see and save your favorites.", parent=front_window() or self.root)
            return self.open_auth()
        self._open("favs", FavoritesWindow)

    # ----- stays
    def open_stay(self, lid, typed=None):
        """`typed` = (check-in, check-out, guests) to keep what the reservation box already holds."""
        row = next((r for r in db.search_listings() if r["id"] == lid), None)
        if row is None:
            return messagebox.showinfo("Stay", "This place is no longer available.", parent=front_window() or self.root)
        if typed is not None:
            d_in, d_out, guests = typed
        else:
            d_in, d_out, guests = self.v_in.get().strip(), self.v_out.get().strip(), self.v_guests.get()
            if not (d_in and d_out):
                d_in = d_out = ""
        old = self.child.get("stay")
        if old is not None and old.winfo_exists():
            old.destroy()
        page = self.child["stay"] = StayPage(self, row, d_in, d_out, guests)
        page.lift()
        page.focus_force()

    # ----- trips
    def refresh_trips(self):
        w = self.child.get("trips")
        if w is not None and w.winfo_exists():
            w.refresh()

    # ----- messages
    def open_messages(self, listing_id=None, guest_id=None):
        """Open the inbox. With a listing, jump to (or start) the conversation about it."""
        if not self.user:
            messagebox.showinfo("Log in", "Please log in or sign up to send messages.", parent=front_window() or self.root)
            return self.open_auth()
        if self.user["role"] == "admin":
            return messagebox.showinfo("Messages", "Admin accounts don't have an inbox.", parent=front_window() or self.root)
        if listing_id is not None and guest_id is None:
            guest_id = self.user["id"]
        if listing_id is not None:  # check first, so a bad request doesn't open an empty window
            try:
                db.conversation_info(self.user["id"], listing_id, guest_id)
            except db.AppError as e:
                return messagebox.showinfo("Messages", str(e), parent=front_window() or self.root)
        self._open("messages", MessagesWindow)
        if listing_id is not None:
            w = self.child.get("messages")
            if w is not None and w.winfo_exists():
                w.open_thread(listing_id, guest_id)

    # ----- currency
    def set_currency(self, code):
        if code not in db.CURRENCIES:
            return
        CUR["code"] = code
        if self.user:
            try:
                db.set_currency(self.user["id"], code)
                self.user["currency"] = code
            except db.AppError as e:
                messagebox.showerror("Currency", str(e), parent=front_window() or self.root)
        self.redraw_prices()

    def redraw_prices(self):
        """Repaint every price on screen in the current currency."""
        self.run_search()
        self.calc()
        for w in list(self.child.values()):
            if not w.winfo_exists():
                continue
            fn = getattr(w, "on_currency", None) or getattr(w, "refresh", None)
            if fn:
                fn()

    # ----- accounts
    def open_auth(self):
        self._open("auth", AuthDialog)

    def open_profile(self):
        if not self.user:
            return self.open_auth()
        self._open("profile", ProfileWindow)

    def set_user(self, user):
        self.user = user
        CUR["code"] = user.get("currency") or "USD"
        self.reload_favs()
        self.redraw_prices()
        self.root.after(400, self.host_prompt)

    def host_prompt(self):
        u = self.user
        if not u or u["role"] != "host":
            return
        n = db.host_pending_count(u["id"])
        if n and messagebox.askyesno(
                "Requests waiting",
                f"You have {n} reservation request{'s' if n != 1 else ''} waiting for your approval.\n\n"
                "Open Hosting now?", parent=front_window() or self.root):
            self._open("host", HostWindow)

    def reload_user(self):
        """Re-read the logged-in user from the database (after a profile or photo change)."""
        fresh = db.get_user(self.user["id"])
        if fresh:
            self.user = fresh
        self.refresh_nav()

    def logout(self):
        self.user = None
        for w in self.child.values():
            if w.winfo_exists():
                w.destroy()
        self.child.clear()
        CUR["code"] = "USD"
        self.reload_favs()
        self.redraw_prices()

    def become_host(self):
        """A guest asks to host. The admin has to approve the request before the account becomes a host."""
        parent = front_window() or self.root
        was_declined = self.user.get("host_status") == "rejected"
        try:
            db.become_host(self.user["id"])
        except db.AppError as e:
            return messagebox.showinfo("Hosting", str(e), parent=parent)
        self.reload_user()
        note = ("Your earlier request was declined, so we've sent a new one.\n\n" if was_declined else "")
        messagebox.showinfo(
            "Host request sent",
            note + "Thanks! An admin needs to approve your request before you can start hosting.\n\n"
                   "Click 'Become a host' again later to check. Once you're approved, the Hosting page opens.",
            parent=parent)

    def _open(self, key, cls):
        if key == "host" and (not self.user or self.user["role"] != "host"):
            return self.start_hosting()  # only approved hosts get in: everyone else goes through the request
        w = self.child.get(key)
        if w is not None and w.winfo_exists():
            if hasattr(w, "refresh"):
                w.refresh()
            if isinstance(w, Page):
                navigation.NAV.goto(w)
            else:
                w.deiconify()
        else:
            w = self.child[key] = cls(self)
        w.lift()
        w.focus_force()


if __name__ == "__main__":
    db.init_db()
    extras.init()
    root = tk.Tk()
    RoamRestApp(root)
    root.mainloop()