"""Guest trips: the Trips page with its tabs, and the per-trip details page."""

import tkinter as tk
from datetime import date
from datetime import timedelta
from tkinter import messagebox
from tkinter import ttk

import database as db
from content import CANCELLED_BY, STATUS_BLURB
from helpers import L, booking_ref, button, fmt_day, fmt_range, fmt_when, money, trip_nights
from images import cover_file
from navigation import Page
from theme import CARD, INK, LINE, MUTED, PAPER, STATUS_STYLE
from toolkit import ReviewDialog, payment_details, review_for_booking

RED = "#D92D20"  # the notification badge colour


class TripsWindow(Page):
    TABS = ["confirmed", "pending", "cancelled"]
    EMPTY = {"confirmed": "No confirmed trips yet.\nOnce a host accepts your request, it shows up here.",
             "pending": "No pending requests.\nReserve a stay and it waits here for the host's reply.",
             "cancelled": "Nothing cancelled.\nWithdrawn, declined, expired and cancelled trips appear here."}

    def __init__(self, app):
        super().__init__(app.root)
        self.app = app
        self.title("My Trips")
        self.geometry("900x660")
        self.minsize(800, 480)
        self.configure(bg=PAPER)
        self.tab = "confirmed"
        self.trips = []
        self.unseen = set()   # confirmed trips the guest has not opened the Confirmed tab for yet
        self.new_ids = set()  # trips that get a NEW tag while this window is open

        head = tk.Frame(self, bg=PAPER, padx=26, pady=16)
        head.pack(fill="x")
        L(head, "Trips", 22, "bold", family="Georgia").pack(side="left")
        button(head, "Refresh", self.refresh, False, small=True).pack(side="right")

        bar = tk.Frame(self, bg=PAPER, padx=26)
        bar.pack(fill="x")
        self.tab_btns, self.tab_badges = {}, {}
        for key in self.TABS:
            slot = tk.Frame(bar, bg=PAPER)
            slot.pack(side="left", padx=(0, 6))
            b = tk.Button(slot, command=lambda k=key: self.select(k), relief="flat", bd=0,
                          font=("Arial", 10, "bold"), padx=18, pady=8, cursor="hand2")
            b.pack()
            self.tab_btns[key] = b
            self.tab_badges[key] = tk.Label(slot, bg=RED, fg="white", font=("Arial", 8, "bold"), padx=5,
                                            cursor="hand2")
            self.tab_badges[key].bind("<Button-1>", lambda e, k=key: self.select(k))
        tk.Frame(self, bg=LINE, height=1).pack(fill="x", pady=(10, 0))
        self.blurb = L(self, "", 9, fg=MUTED, wraplength=800, justify="left")
        self.blurb.pack(anchor="w", padx=26, pady=(10, 10))

        body = tk.Frame(self, bg=PAPER)
        body.pack(fill="both", expand=True)
        self.cv = tk.Canvas(body, bg=PAPER, highlightthickness=0)
        sb = ttk.Scrollbar(body, orient="vertical", command=self.cv.yview)
        self.cv.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.cv.pack(side="left", fill="both", expand=True)
        self.list = tk.Frame(self.cv, bg=PAPER)
        win = self.cv.create_window((0, 0), window=self.list, anchor="nw")
        self.list.bind("<Configure>", lambda e: self.cv.configure(scrollregion=self.cv.bbox("all")))
        self.cv.bind("<Configure>", lambda e: self.cv.itemconfig(win, width=e.width))
        self.bind("<MouseWheel>", lambda e: self.cv.yview_scroll(int(-e.delta / 120), "units"))

        self.refresh()
        counts = {k: sum(1 for t in self.trips if t["status"] == k) for k in self.TABS}
        first = next((k for k in self.TABS if counts[k]), "confirmed")
        self.select(first)

    # ----- data + tabs
    def refresh(self):
        fresh = set(db.unseen_trip_ids(self.app.user["id"]))  # a host confirmed these since the last look
        self.unseen |= fresh
        self.new_ids |= fresh
        self.trips = [dict(r) for r in db.guest_bookings(self.app.user["id"])]
        self.render()

    def select(self, key):
        self.tab = key
        self.render()

    def render(self):
        if self.tab == "confirmed" and self.unseen:  # looking at the Confirmed tab clears the red number
            db.mark_trips_seen(self.app.user["id"], self.unseen)
            self.unseen = set()
            self.app.refresh_nav()
        counts = {k: sum(1 for t in self.trips if t["status"] == k) for k in self.TABS}
        waiting = sum(1 for t in self.trips if t["status"] == "confirmed" and t["id"] in self.unseen)
        for key, badge in self.tab_badges.items():  # red number on the Confirmed tab until it is opened
            if key == "confirmed" and waiting:
                badge.config(text=str(waiting) if waiting < 10 else "9+")
                badge.place(relx=1.0, x=-2, y=2, anchor="ne")
                badge.lift()
            else:
                badge.place_forget()
        for key, b in self.tab_btns.items():
            on = key == self.tab
            b.config(text=f"{STATUS_STYLE[key][0]} ({counts[key]})", bg=INK if on else CARD,
                     fg=PAPER if on else MUTED, activebackground=INK if on else LINE,
                     activeforeground=PAPER if on else INK)
        self.blurb.config(text=STATUS_BLURB[self.tab])
        for w in self.list.winfo_children():
            w.destroy()
        rows = [t for t in self.trips if t["status"] == self.tab]
        if self.tab == "confirmed":
            rows.sort(key=lambda t: t["check_in"])
        elif self.tab == "pending":
            rows.sort(key=lambda t: t["created_at"], reverse=True)
        else:
            rows.sort(key=lambda t: t["cancelled_at"] or "", reverse=True)
        if not rows:
            L(self.list, self.EMPTY[self.tab], 12, slant="italic", family="Georgia", fg=MUTED,
              justify="center").pack(pady=70)
            return
        for t in rows:
            self.build_card(t)
        self.cv.yview_moveto(0)

    # ----- one trip card
    def build_card(self, t):
        label, fg, bg = STATUS_STYLE[t["status"]]
        n = trip_nights(t)
        c = tk.Frame(self.list, bg=CARD, highlightbackground=LINE, highlightthickness=1, padx=14, pady=14)
        c.pack(fill="x", padx=26, pady=(0, 12))
        c.columnconfigure(1, weight=1)

        img = tk.Label(c, bg=CARD, bd=0)
        img.grid(row=0, column=0, rowspan=2, sticky="n", padx=(0, 16))
        self.app.photos.attach(img, t["image_seed"], 150, 112, 12, CARD, t["title"],
                               local=cover_file(t["listing_id"]))

        info = tk.Frame(c, bg=CARD)
        info.grid(row=0, column=1, sticky="nw")
        L(info, t["title"], 14, "bold", family="Georgia", wraplength=340, justify="left").pack(anchor="w")
        L(info, "\u25CF " + t["location"], 9, fg=MUTED).pack(anchor="w", pady=(2, 0))
        L(info, f"{fmt_range(t['check_in'], t['check_out'])}  \u00B7  {n} night{'s' if n != 1 else ''}"
                f"  \u00B7  {t['guests']} guest{'s' if t['guests'] != 1 else ''}", 10).pack(anchor="w", pady=(8, 0))
        L(info, f"Total {money(t['total_price'])}  \u00B7  Ref {booking_ref(t)}", 9, fg=MUTED).pack(anchor="w", pady=(2, 0))

        if t["status"] == "pending":
            created = db._parse_ts(t["created_at"])
            if created:
                due = created + timedelta(hours=db.PENDING_HOURS)
                L(info, f"Host replies by {fmt_when(due.isoformat(timespec='seconds'))}", 9, "bold",
                  fg=STATUS_STYLE["pending"][1]).pack(anchor="w", pady=(6, 0))
        elif t["status"] == "confirmed":
            L(info, f"Hosted by {t['host_name']}", 9, "bold", fg=STATUS_STYLE["confirmed"][1]).pack(
                anchor="w", pady=(6, 0))
        else:
            reason = t["cancel_reason"] or "Cancelled"
            L(info, reason, 9, "bold", fg=STATUS_STYLE["cancelled"][1], wraplength=340,
              justify="left").pack(anchor="w", pady=(6, 0))
            if t["cancelled_at"]:
                L(info, f"Refund {money(db.refunded_amount(t))}  \u00B7  {fmt_when(t['cancelled_at'])}", 9,
                  fg=MUTED).pack(anchor="w")

        side = tk.Frame(c, bg=CARD)
        side.grid(row=0, column=2, rowspan=2, sticky="ne", padx=(14, 0))
        if t["status"] == "confirmed" and t["id"] in self.new_ids:
            L(side, " NEW ", 8, "bold", fg="white", bg=RED).pack(anchor="e", pady=(0, 4))
        L(side, f" {label.upper()} ", 8, "bold", fg=fg, bg=bg).pack(anchor="e")
        button(side, "View details", lambda t=t: TripDetail(self.app, t, self.act), False,
               small=True).pack(anchor="e", pady=(14, 0))
        button(side, "Message host", lambda t=t: self.app.open_messages(t["listing_id"], t["guest_id"]),
               False, small=True).pack(anchor="e", pady=(6, 0))
        if t["status"] == "pending":
            button(side, "Withdraw request", lambda t=t: self.act(t), small=True).pack(anchor="e", pady=(6, 0))
        elif t["status"] == "confirmed":
            if t["check_out"] <= date.today().isoformat():  # the stay is over: the guest can review it
                done = review_for_booking(t["id"])
                button(side, "Edit review" if done is not None else "Write a review",
                       lambda t=t: ReviewDialog(self.app, t, self.refresh), small=True).pack(anchor="e", pady=(6, 0))
            elif t["check_in"] > date.today().isoformat():  # once the stay has started it can no longer be cancelled
                button(side, "Cancel booking", lambda t=t: self.act(t), small=True).pack(anchor="e", pady=(6, 0))

    # ----- withdraw / cancel
    def act(self, t):
        if t["status"] == "pending":
            ok = messagebox.askyesno(
                "Withdraw request",
                f"Withdraw your request for {t['title']}?\n\nNothing has been charged, so there's no penalty.",
                parent=self)
        else:
            refund, note = db.guest_refund(t)
            ok = messagebox.askyesno(
                "Cancel booking",
                f"Cancel {t['title']} ({fmt_range(t['check_in'], t['check_out'])})?\n\n{note}\n"
                f"You'll get back {money(refund)} of {money(t['total_price'])}.", parent=self)
        if not ok:
            return
        try:
            refund = db.cancel_booking(t["id"], self.app.user["id"])
        except db.AppError as e:
            return messagebox.showerror("Cancel", str(e), parent=self)
        self.refresh()
        self.select("cancelled")
        self.app.run_search()
        if t["status"] == "pending":  # nothing was charged for a request, so there is nothing to refund
            messagebox.showinfo("Withdrawn", "Request withdrawn. You were not charged.", parent=self)
        else:
            messagebox.showinfo("Cancelled", f"Done. Your refund: {money(refund)}.", parent=self)


class TripDetail(Page):
    """Everything about one trip: status, stay, host contact, receipt, payment and cancellation."""

    def __init__(self, app, t, on_action):
        super().__init__(app.root)
        label, fg, bg = STATUS_STYLE[t["status"]]
        n = trip_nights(t)
        self.title(f"Trip {booking_ref(t)}")
        self.configure(bg=PAPER)
        self.resizable(True, True)
        # a centred, scrollable column (so the Back bar spans the window and nothing is ever cut off)
        cv = tk.Canvas(self, bg=PAPER, highlightthickness=0)
        sb = ttk.Scrollbar(self, orient="vertical", command=cv.yview)

        def on_scroll(lo, hi):
            if float(lo) <= 0 and float(hi) >= 1:
                sb.pack_forget()
            elif not sb.winfo_ismapped():
                sb.pack(side="right", fill="y", before=cv)
            sb.set(lo, hi)
        cv.configure(yscrollcommand=on_scroll)
        cv.pack(side="left", fill="both", expand=True)
        body = tk.Frame(cv, bg=PAPER, padx=14, pady=12)
        win = cv.create_window((0, 0), window=body, anchor="n")
        body.bind("<Configure>", lambda e: cv.configure(scrollregion=(0, 0, 1, body.winfo_reqheight())))
        cv.bind("<Configure>", lambda e: cv.coords(win, e.width / 2, 0))
        self.bind("<MouseWheel>", lambda e: cv.yview_scroll(int(-e.delta / 120), "units"))

        def section(title):
            tk.Frame(body, bg=LINE, height=1).pack(fill="x", pady=(14, 8))
            L(body, title, 11, "bold", family="Georgia").pack(anchor="w")

        def row(key, value, bold=False):
            f = tk.Frame(body, bg=PAPER)
            f.pack(fill="x", pady=1)
            L(f, key, 10, fg=MUTED).pack(side="left")
            L(f, value, 10, "bold" if bold else "normal", wraplength=300, justify="right").pack(side="right")

        L(body, t["title"], 18, "bold", family="Georgia", wraplength=470, justify="left").pack(anchor="w")
        L(body, t["location"], 10, fg=MUTED).pack(anchor="w")
        L(body, f" {label.upper()} ", 9, "bold", fg=fg, bg=bg).pack(anchor="w", pady=(10, 0))
        L(body, STATUS_BLURB[t["status"]], 10, wraplength=470, justify="left").pack(anchor="w", pady=(6, 0))

        section("Reservation")
        row("Reference", booking_ref(t))
        row("Requested on", fmt_when(t["created_at"]))
        row("Check-in", fmt_day(t["check_in"]))
        row("Check-out", fmt_day(t["check_out"]))
        row("Guests", str(t["guests"]))

        section("Your host")
        row("Host", t["host_name"])
        if t["status"] == "confirmed":
            row("Phone", t["host_phone"] or "Not provided")
            row("Email", t["host_email"] or "\u2014")
            L(body, "Message your host to arrange arrival and check-in.", 9, fg=MUTED).pack(anchor="w", pady=(4, 0))
        else:
            L(body, "Host contact details are shared once the reservation is confirmed.", 9,
              fg=MUTED).pack(anchor="w", pady=(4, 0))

        section("Receipt")
        nightly = t["total_price"] / n if n else t["total_price"]
        row(f"{money(nightly)} x {n} night{'s' if n != 1 else ''}", money(t["total_price"]))
        row("Service fee", money(0) + " (included)")
        row("Total", money(t["total_price"]), True)

        section("Payment")
        for kind, *rest in payment_details(t):
            if kind == "row":
                row(rest[0], rest[1], rest[2])
            else:
                L(body, rest[0], 9, fg=MUTED, wraplength=470, justify="left").pack(anchor="w", pady=(4, 0))

        if t["status"] == "cancelled":
            section("Cancellation")
            row("Cancelled by", CANCELLED_BY.get(t["cancelled_by"], "\u2014"))
            row("Date", fmt_when(t["cancelled_at"]))
            row("Reason", t["cancel_reason"] or "Cancelled")

        L(body, "RoamRest demo: no real payments are processed.", 8, fg=MUTED).pack(anchor="w", pady=(16, 0))
        btns = tk.Frame(body, bg=PAPER)
        btns.pack(anchor="w", pady=(10, 0))
        if t["status"] in ("pending", "confirmed"):
            text = "Withdraw request" if t["status"] == "pending" else "Cancel booking"
            button(btns, text, lambda: (self.destroy(), on_action(t))).pack(side="left", padx=(0, 8))
        button(btns, "Message host", lambda: app.open_messages(t["listing_id"], t["guest_id"]),
               False).pack(side="left", padx=(0, 8))
        button(btns, "Close", self.destroy, False).pack(side="left")