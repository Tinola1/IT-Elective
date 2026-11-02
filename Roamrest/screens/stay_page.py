"""The full listing page with its photo grid, reservation card and reviews."""

import tkinter as tk
from datetime import date
from datetime import timedelta
from tkinter import messagebox
from tkinter import ttk

import database as db
import payments
from helpers import L, button, fmt_night, link, money, money0
from navigation import Page
from theme import CARD, CLAY, CLAY_DEEP, INK, LINE, MUTED
from toolkit import DateGuestBlock, PaymentPicker, booked_nights, reviews_section
from trips import TripsWindow


class StayPage(Page):
    def __init__(self, app, listing, check_in="", check_out="", guests="2"):
        super().__init__(app.root)
        self.app, self.r = app, listing
        r = listing
        self.title(r["title"])
        self.geometry("1100x820")
        self.minsize(900, 600)
        self.configure(bg=CARD)

        cv = tk.Canvas(self, bg=CARD, highlightthickness=0)
        sb = ttk.Scrollbar(self, orient="vertical", command=cv.yview)
        cv.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        cv.pack(side="left", fill="both", expand=True)
        page = tk.Frame(cv, bg=CARD)
        win = cv.create_window((0, 0), window=page, anchor="nw")
        page.bind("<Configure>", lambda e: cv.configure(scrollregion=cv.bbox("all")))
        cv.bind("<Configure>", lambda e: cv.itemconfig(win, width=e.width))
        self.bind("<MouseWheel>", lambda e: cv.yview_scroll(int(-e.delta / 120), "units"))
        wrap = tk.Frame(page, bg=CARD)
        wrap.pack(padx=40, pady=22)

        # ---- title + save
        top = tk.Frame(wrap, bg=CARD)
        top.pack(fill="x")
        L(top, r["title"], 20, "bold", wraplength=760, justify="left").pack(side="left")
        self.save_lbl = link(top, "", self.toggle_save, fg=INK, size=10, bold=True)
        self.save_lbl.pack(side="right")
        self.refresh_heart()

        # ---- photo grid (one big photo + four small)
        seed = r["image_seed"]
        seeds = [seed] + [f"{seed}-{i}" for i in range(2, 6)]
        mine = db.photo_files(r["id"])  # the host's own pictures, cover first
        grid = tk.Frame(wrap, bg=CARD)
        grid.pack(pady=(14, 0))
        big = tk.Label(grid, bg=CARD, bd=0)
        big.grid(row=0, column=0, rowspan=2, padx=(0, 4))
        app.photos.attach(big, seeds[0], 474, 340, 14, CARD, r["title"], local=mine[0] if mine else None)
        for i, s in enumerate(seeds[1:]):
            lb = tk.Label(grid, bg=CARD, bd=0)
            lb.grid(row=i // 2, column=1 + i % 2, padx=(0, 4) if i % 2 == 0 else 0,
                    pady=(0, 4) if i < 2 else 0)
            if not mine:
                app.photos.attach(lb, s, 237, 168, 14, CARD, "")
            elif i + 1 < len(mine):
                app.photos.attach(lb, s, 237, 168, 14, CARD, "", local=mine[i + 1])
            else:
                app.photos.blank(lb, 237, 168, 14, CARD)

        # ---- details (left) + reservation card (right)
        body = tk.Frame(wrap, bg=CARD)
        body.pack(fill="x", pady=(22, 0))
        left = tk.Frame(body, bg=CARD)
        left.grid(row=0, column=0, sticky="n", padx=(0, 44))
        right = tk.Frame(body, bg=CARD)
        right.grid(row=0, column=1, sticky="n")
        tk.Frame(left, bg=CARD, width=570, height=1).pack()
        tk.Frame(right, bg=CARD, width=330, height=1).pack()

        L(left, f"{r['category']} in {r['location']}", 16, "bold").pack(anchor="w")
        L(left, f"Sleeps {r['max_guests']}  \u00B7  Prices include all fees", 10, fg=MUTED).pack(anchor="w", pady=(2, 14))

        rating, reviews = r["rating"], r["review_count"]
        box = tk.Frame(left, bg=CARD, highlightbackground=LINE, highlightthickness=1, padx=16, pady=12)
        box.pack(fill="x")
        if rating and rating >= 4.9:
            L(box, "Guest\nfavorite", 12, "bold", justify="center").grid(row=0, column=0, padx=(0, 14))
            L(box, "One of the most loved homes on RoamRest, according to guests", 10,
              wraplength=230, justify="left").grid(row=0, column=1, padx=(0, 14))
        elif rating:
            L(box, "Loved by guests", 12, "bold").grid(row=0, column=0, padx=(0, 30))
        else:
            L(box, "New listing", 12, "bold").grid(row=0, column=0)
        if rating:
            stat = tk.Frame(box, bg=CARD)
            stat.grid(row=0, column=2, padx=(10, 0))
            L(stat, f"{rating:.2f}", 16, "bold").pack()
            L(stat, "\u2605" * 5, 8, fg=INK).pack()
            L(stat, f"{reviews} reviews", 8, fg=MUTED).pack()

        host = tk.Frame(left, bg=CARD)
        host.pack(fill="x", pady=(18, 0))
        av = tk.Canvas(host, width=44, height=44, bg=CARD, highlightthickness=0)
        av.create_oval(2, 2, 42, 42, fill=CLAY, outline="")
        av.create_text(22, 22, text=(r["host_name"] or "?")[:1].upper(), fill="white", font=("Arial", 14, "bold"))
        av.pack(side="left")
        info = tk.Frame(host, bg=CARD)
        info.pack(side="left", padx=12)
        L(info, f"Hosted by {r['host_name']}", 11, "bold").pack(anchor="w")
        L(info, "Verified RoamRest host", 9, fg=MUTED).pack(anchor="w")
        button(host, "Contact host", self.contact_host, False, small=True).pack(side="right")

        tk.Frame(left, bg=LINE, height=1).pack(fill="x", pady=18)
        amen = [a.strip() for a in (r["amenities"] or "").split(",") if a.strip()]
        if amen:
            L(left, "What this place offers", 14, "bold").pack(anchor="w")
            for a in amen:
                L(left, "\u2713  " + a, 10).pack(anchor="w", pady=(6, 0))
            tk.Frame(left, bg=LINE, height=1).pack(fill="x", pady=18)

        desc = r["description"] or "No description provided."
        self.full_desc = desc
        self.short_desc = desc if len(desc) <= 240 else desc[:240].rsplit(" ", 1)[0] + "\u2026"
        self.desc_lbl = L(left, self.short_desc, 10, wraplength=570, justify="left")
        self.desc_lbl.pack(anchor="w")
        self.more_btn = None
        if len(desc) > 240:
            self.more_btn = tk.Button(left, text="Show more", command=self.toggle_desc, bg=LINE, fg=INK,
                                      relief="flat", font=("Arial", 10, "bold"), padx=14, pady=6,
                                      cursor="hand2")
            self.more_btn.pack(anchor="w", pady=(10, 0))

        reviews_section(left, self.r["id"])

        # ---- reservation card
        L(right, "\u25CF  Prices include all fees", 10, "bold", fg=CLAY).pack(anchor="w", pady=(0, 12))
        rc = tk.Frame(right, bg=CARD, highlightbackground=LINE, highlightthickness=1, padx=20, pady=18)
        rc.pack(fill="x")
        prow = tk.Frame(rc, bg=CARD)
        prow.pack(anchor="w")
        self.price_lbl = L(prow, "", 20, "bold")
        self.price_lbl.pack(side="left")
        self.nights_lbl = L(prow, "", 10, fg=MUTED)
        self.nights_lbl.pack(side="left", padx=8)

        today = date.today()
        self.v_in = tk.StringVar(value=check_in or (today + timedelta(days=7)).isoformat())
        self.v_out = tk.StringVar(value=check_out or (today + timedelta(days=10)).isoformat())
        try:
            g = max(1, min(int(guests or 2), r["max_guests"]))
        except ValueError:
            g = 2
        self.v_guests = tk.StringVar(value=str(g))

        # dates are picked on a calendar (taken nights are greyed out); guests use - / + buttons
        DateGuestBlock(rc, self.v_in, self.v_out, self.v_guests, r["max_guests"],
                       blocked=booked_nights(r["id"])).pack(fill="x", pady=(12, 0))
        self.picker = PaymentPicker(rc, self)  # "Pay with" + payment plan
        self.picker.pack(fill="x", pady=(14, 0))

        tk.Button(rc, text="Request to book", command=self.reserve, bg=CLAY, fg="white",
                  activebackground=CLAY_DEEP, activeforeground="white", relief="flat",
                  font=("Arial", 12, "bold"), pady=10, cursor="hand2").pack(fill="x", pady=(12, 6))
        L(rc, "The host must approve before it's confirmed.\nYou won't be charged until they do.", 9,
          fg=MUTED, justify="center").pack()
        tk.Frame(rc, bg=LINE, height=1).pack(fill="x", pady=12)
        sums = tk.Frame(rc, bg=CARD)
        sums.pack(fill="x")
        self.line_l = L(sums, "", 10)
        self.line_l.grid(row=0, column=0, sticky="w")
        self.line_r = L(sums, "", 10)
        self.line_r.grid(row=0, column=1, sticky="e")
        L(sums, "Total", 11, "bold").grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.total_r = L(sums, "", 11, "bold")
        self.total_r.grid(row=1, column=1, sticky="e", pady=(6, 0))
        sums.columnconfigure(0, weight=1)

        for v in (self.v_in, self.v_out):
            v.trace_add("write", self.update_quote)
        self.update_quote()

    def on_currency(self):
        self.update_quote()

    def contact_host(self):
        self.app.open_messages(self.r["id"])

    def toggle_desc(self):
        full = self.desc_lbl.cget("text") != self.full_desc
        self.desc_lbl.config(text=self.full_desc if full else self.short_desc)
        self.more_btn.config(text="Show less" if full else "Show more")

    def refresh_heart(self):
        self.save_lbl.config(text="\u2665 Saved" if self.r["id"] in self.app.favs else "\u2661 Save")

    def toggle_save(self):
        self.app.toggle_fav(self.r["id"])

    def update_quote(self, *_):
        nightly = self.r["price_per_night"]
        try:
            n, total = db.quote(nightly, self.v_in.get(), self.v_out.get())
        except db.AppError:
            self.price_lbl.config(text=fmt_night(nightly))
            self.nights_lbl.config(text="per night \u2014 enter valid dates")
            self.line_l.config(text="")
            self.line_r.config(text="")
            self.total_r.config(text="\u2014")
            self.picker.set_quote(None)
            return
        s = "s" if n != 1 else ""
        self.price_lbl.config(text=money0(total))
        self.nights_lbl.config(text=f"for {n} night{s}")
        self.line_l.config(text=f"{fmt_night(nightly)} x {n} night{s}")
        self.line_r.config(text=money0(total))
        self.total_r.config(text=money0(total))
        self.picker.set_quote(total, self.v_in.get())

    def reserve(self):
        if not self.app.user:
            messagebox.showinfo("Log in", "Please log in or sign up to reserve.", parent=self)
            return self.app.open_auth()
        fresh = db.get_user(self.app.user["id"]) or self.app.user
        missing = db.profile_missing(fresh)
        if missing:
            messagebox.showinfo(
                "Complete your profile",
                "Before booking, we need a few details from you:\n\n  \u2022 " + "\n  \u2022 ".join(missing) +
                "\n\nThe Profile window will open now.", parent=self)
            return self.app.open_profile()
        self.picker.refresh()
        if not self.picker.methods:
            messagebox.showinfo("Add a payment method",
                                "Add a way to pay first. You won't be charged until the host accepts your request.",
                                parent=self)
            return self.picker.add_method()
        try:
            nights, total = db.quote(self.r["price_per_night"], self.v_in.get(), self.v_out.get())
            method_id, plan, method = self.picker.choice()
            if not messagebox.askyesno(
                    "Send reservation request",
                    f"{self.r['title']}\n{self.v_in.get()} \u2192 {self.v_out.get()}  ({nights} nights)\n"
                    f"Guests: {self.v_guests.get()}\nTotal: {money(total)}\n"
                    f"Pay with: {db.method_label(method)}  ({payments.PLAN_NAMES.get(plan, 'Pay in full')})\n\n"
                    f"The host has {db.PENDING_HOURS} hours to approve. You won't be charged until they do.\n\n"
                    "Send request?", parent=self):
                return
            db.create_booking(self.r["id"], self.app.user["id"], self.v_in.get(),
                              self.v_out.get(), self.v_guests.get(), method_id=method_id, plan=plan)
        except db.AppError as e:
            return messagebox.showerror("Reservation failed", str(e), parent=self)
        view = messagebox.askyesno(
            "Request sent",
            f"Your request was sent to {self.r['host_name']}. It's now Pending until they approve it.\n\n"
            "View it in My Trips?", parent=self)
        self.destroy()
        self.app.run_search()
        self.app.refresh_trips()
        if view:
            self.app._open("trips", TripsWindow)
            w = self.app.child.get("trips")
            if w is not None and w.winfo_exists():
                w.select("pending")
