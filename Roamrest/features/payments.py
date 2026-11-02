"""payments.py - the screens for paying and getting paid on RoamRest.

Guests: saved payment methods (cards, PayPal, Apple Pay, Google Pay, GCash, Maya), a "Pay with" step on the
reservation card (pay in full or in two parts), and a payment breakdown for every trip.
Hosts: a payout method (bank, PayPal, Fast Pay, Payoneer, wire, GCash) and an earnings screen that shows what is in
escrow, what is held, and what has been paid out.

Escrow-style rules (all simulated, no real money moves):
  * a request only places a hold; the guest is charged when the host accepts
  * RoamRest keeps the money and pays the host about 24 hours after check-in, minus the flat 3% host fee
  * a brand-new host's first payout waits until 24 hours after check-out
  * stays of 28+ nights are paid out in monthly instalments
  * refunds go back to the original payment method and follow the listing's cancellation policy

Used by app.py through:  payments.install(globals())
"""
import tkinter as tk
from datetime import date, datetime
from tkinter import ttk, messagebox

import database as db

AppError = db.AppError

BADGES = {"Visa": ("VISA", "#1A1F71"), "MasterCard": ("MC", "#C8102E"), "Amex": ("AMEX", "#2E77BC"),
          "Discover": ("DISC", "#D9660B"), "paypal": ("PayPal", "#003087"), "apple_pay": ("Apple Pay", "#111111"),
          "google_pay": ("G Pay", "#4285F4"), "gcash": ("GCash", "#0A64DC"), "maya": ("maya", "#0FA24A"),
          "bank": ("BANK", "#4A5568"), "fast_pay": ("FAST PAY", "#B44A1E"), "payoneer": ("Payoneer", "#E8420A"),
          "wire": ("WIRE", "#4A5568")}

PLAN_NAMES = {"full": "Pay in full", "split": "Pay in 2 parts"}


class _UI:
    """Gives this module access to app.py's colours and helpers (L, button, money, ...)."""
    def __init__(self, ns):
        self.__dict__["_ns"] = ns

    def __getattr__(self, name):
        return self._ns[name]


def payment_status_text(ui, t, s):
    """One short line describing where a trip's money is right now."""
    if t["status"] == "pending":
        return "Authorized, not charged"
    if t["status"] == "cancelled":
        return "Not charged" if s["never_charged"] else f"Refunded {ui.money(s['refund'])}"
    if s["released"]:
        return "Paid \u00B7 released to host"
    if s["paid"] + 0.005 < s["total"]:
        return "Part paid \u00B7 in escrow"
    return "Paid \u00B7 in escrow"


def make_payment_details(ui):
    def payment_details(t):
        """Rows for the 'Payment' section of a trip: [('row', key, value, bold)] and [('note', text)]."""
        money, fmt_day = ui.money, ui.fmt_day
        s = db.payment_summary(t)
        out = []
        if not s["recorded"]:  # a booking made before payment methods existed
            if t["status"] == "confirmed":
                out.append(("row", "Payment status", "Paid in full (demo)", False))
            elif t["status"] == "pending":
                out.append(("row", "Payment status", "Temporary hold only, not charged yet", False))
            else:
                out.append(("row", "Payment status", "Refunded" if t["refund"] else "Not charged", False))
                if t["cancelled_at"]:
                    out.append(("row", "Refund amount", money(t["refund"]), True))
            out.append(("note", "This trip was booked before payment methods were added, so no card is on record."))
            return out
        out.append(("row", "Paid with", s["method"], True))
        out.append(("row", "Payment plan", PLAN_NAMES.get(s["plan"], "Pay in full"), False))
        for p in s["parts"]:
            label = f"Part {p['n']} of {len(s['parts'])}" if len(s["parts"]) > 1 else "Amount"
            if p["state"] == "authorized":
                what = "authorized, charged when the host accepts"
            elif p["state"] == "released":
                what = "hold released, never charged"
            elif p["state"] == "paid":
                what = "paid " + fmt_day(p["at"].strftime("%Y-%m-%d"))
            elif p["state"] == "cancelled":
                what = "cancelled, never charged"
            else:
                what = "charged automatically on " + fmt_day(p["due"].strftime("%Y-%m-%d")) if p["due"] else "scheduled"
            out.append(("row", label, f"{money(p['amount'])}  \u00B7  {what}", False))
        out.append(("row", "Payment status", payment_status_text(ui, t, s), True))
        if t["status"] == "confirmed":
            when = fmt_day(s["release_at"].strftime("%Y-%m-%d"))
            out.append(("note", "RoamRest holds your payment in escrow and releases it to the host about 24 hours "
                                f"after check-in ({when})." if not s["released"] else
                                f"Your payment was released to the host on {when}."))
        elif t["status"] == "cancelled" and not s["never_charged"]:
            out.append(("row", "Refund amount", money(s["refund"]), True))
            out.append(("row", "Refunded to", f"{s['method']} (arrives {s['refund_eta']})", False))
            if s["paid"] - s["refund"] > 0.005:
                out.append(("row", "Not refunded", money(s["paid"] - s["refund"]), False))
        elif t["status"] == "cancelled":
            out.append(("note", "The hold on your payment method was released. You were not charged."))
        policy = db.refund_policy_of(t)
        out.append(("row", "Cancellation policy", policy, False))
        out.append(("note", db.POLICY_TEXT[policy]))
        return out
    return payment_details


def make_screens(ui):
    L, button, link, make_tree, clear = ui.L, ui.button, ui.link, ui.make_tree, ui.clear
    Page = ui.Page  # full-screen pages with a Back button (defined in app.py)
    PAPER, PAPER2, CARD, INK, MUTED = ui.PAPER, ui.PAPER2, ui.CARD, ui.INK, ui.MUTED
    CLAY, CLAY_DEEP, LINE, PILL_BG = ui.CLAY, ui.CLAY_DEEP, ui.LINE, ui.PILL_BG
    money, money0, fmt_day = ui.money, ui.money0, ui.fmt_day
    PENDING, CONFIRMED, CANCELLED = ui.STATUS_STYLE["pending"], ui.STATUS_STYLE["confirmed"], ui.STATUS_STYLE["cancelled"]
    SIDE = 30

    def badge(parent, key, bg=None):
        text, color = BADGES.get(key, ("PAY", "#4A5568"))
        return tk.Label(parent, text=text, bg=color, fg="white", font=("Arial", 8, "bold"), width=8, pady=5)

    def method_badge(m):
        return m["brand"] if m["kind"] == "card" else m["kind"]

    def scroller(win, bg=PAPER):
        body = tk.Frame(win, bg=bg)
        body.pack(fill="both", expand=True)
        cv = tk.Canvas(body, bg=bg, highlightthickness=0)
        sb = ttk.Scrollbar(body, orient="vertical", command=cv.yview)
        cv.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        cv.pack(side="left", fill="both", expand=True)
        inner = tk.Frame(cv, bg=bg)
        w = cv.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda e: cv.configure(scrollregion=cv.bbox("all")))
        cv.bind("<Configure>", lambda e: cv.itemconfig(w, width=e.width))

        def wheel(e, step):
            if str(e.widget).startswith(str(cv)):
                cv.yview_scroll(step, "units")
        win.bind("<MouseWheel>", lambda e: wheel(e, int(-e.delta / 120)))
        win.bind("<Button-4>", lambda e: wheel(e, -3))
        win.bind("<Button-5>", lambda e: wheel(e, 3))
        return cv, inner

    def header(win, eyebrow, plain, accent, sub):
        head = tk.Frame(win, bg=PAPER, padx=SIDE)
        head.pack(fill="x", pady=(22, 14))
        L(head, eyebrow, 9, "bold", fg=CLAY).pack(anchor="w")
        t = tk.Frame(head, bg=PAPER)
        t.pack(anchor="w", pady=(4, 0))
        L(t, plain + " ", 24, "bold", family="Georgia").pack(side="left")
        L(t, accent, 24, "bold", "italic", family="Georgia", fg=CLAY).pack(side="left")
        L(head, sub, 10, fg=MUTED, wraplength=720, justify="left").pack(anchor="w", pady=(4, 0))
        tk.Frame(win, bg=LINE, height=1).pack(fill="x")
        return head

    def section(parent, title, right=None, top=26):
        row = tk.Frame(parent, bg=PAPER)
        row.pack(fill="x", pady=(top, 10))
        L(row, title, 15, "bold", family="Georgia").pack(side="left")
        if right is not None:
            right(row).pack(side="right")
        return row

    def card(parent, **kw):
        return tk.Frame(parent, bg=CARD, highlightbackground=LINE, highlightthickness=1, **kw)

    def info_card(parent, lines):
        c = card(parent, padx=18, pady=14)
        c.pack(fill="x")
        for i, (head, text) in enumerate(lines):
            f = tk.Frame(c, bg=CARD)
            f.pack(fill="x", pady=(0 if i == 0 else 10, 0))
            L(f, "\u25CF", 8, fg=CLAY, bg=CARD).pack(side="left", anchor="n", pady=(3, 0))
            col = tk.Frame(f, bg=CARD)
            col.pack(side="left", padx=(10, 0))
            L(col, head, 10, "bold", bg=CARD).pack(anchor="w")
            L(col, text, 9, fg=MUTED, bg=CARD, wraplength=640, justify="left").pack(anchor="w")
        return c

    # ============================================================ add a payment method
    class AddPaymentDialog(tk.Toplevel):
        TEST = "Demo: try 4242 4242 4242 4242, any future date, any 3 digits."

        def __init__(self, app, on_done=None):
            super().__init__(app.root)
            self.app, self.on_done = app, on_done
            self.title("Add a payment method")
            self.configure(bg=PAPER, padx=30, pady=22)
            self.resizable(False, False)
            self.transient(ui.front_window() or app.root)
            self.kind = "card"
            L(self, "Add a payment method", 18, "bold", family="Georgia").pack(anchor="w")
            L(self, "Pay with a card, a digital wallet, PayPal or a local wallet. You're only charged after a host "
                    "accepts your request.", 9, fg=MUTED, wraplength=440, justify="left").pack(anchor="w", pady=(4, 12))
            chips = tk.Frame(self, bg=PAPER)
            chips.pack(anchor="w")
            self.chips = {}
            for i, (key, name) in enumerate(db.PAYMENT_KINDS):
                b = tk.Button(chips, text=name.replace("Credit or debit card", "Card"), relief="flat", bd=0,
                              font=("Arial", 9, "bold"), padx=12, pady=5, cursor="hand2",
                              command=lambda k=key: self.pick(k))
                b.grid(row=i // 3, column=i % 3, padx=(0, 6), pady=(0, 6), sticky="w")
                self.chips[key] = b
            self.form = tk.Frame(self, bg=PAPER)
            self.form.pack(fill="x", pady=(8, 0))
            self.v = {k: tk.StringVar() for k in ("holder", "number", "expiry", "cvv", "detail")}
            self.msg = L(self, "", 9, fg=MUTED, wraplength=440, justify="left")
            self.msg.pack(anchor="w", pady=(10, 0))
            bar = tk.Frame(self, bg=PAPER)
            bar.pack(anchor="w", pady=(14, 0))
            button(bar, "Save payment method", self.save).pack(side="left")
            button(bar, "Cancel", self.destroy, False).pack(side="left", padx=8)
            self.bind("<Escape>", lambda e: self.destroy())
            self.pick("card")

        def pick(self, kind):
            self.kind = kind
            for k, b in self.chips.items():
                on = k == kind
                b.config(bg=INK if on else CARD, fg=PAPER if on else MUTED, activebackground=INK if on else LINE,
                         activeforeground=PAPER if on else INK)
            for w in self.form.winfo_children():
                w.destroy()
            for var in self.v.values():
                var.set("")

            def field(label, key, width=44, show=""):
                L(self.form, label, 9, "bold", fg=MUTED).pack(anchor="w", pady=(8, 2))
                e = ttk.Entry(self.form, textvariable=self.v[key], width=width, show=show)
                e.pack(anchor="w")
                return e

            if kind == "card":
                field("NAME ON CARD", "holder")
                num = field("CARD NUMBER", "number")
                num.bind("<FocusOut>", lambda e: self.v["number"].set(
                    " ".join(__import__("re").findall(r".{1,4}", "".join(c for c in self.v["number"].get() if c.isdigit())))))
                row = tk.Frame(self.form, bg=PAPER)
                row.pack(anchor="w")
                for i, (lab, key, w, show) in enumerate((("EXPIRY (MM/YY)", "expiry", 14, ""), ("CVV", "cvv", 8, "\u2022"))):
                    col = tk.Frame(row, bg=PAPER)
                    col.grid(row=0, column=i, padx=(0, 14))
                    L(col, lab, 9, "bold", fg=MUTED).pack(anchor="w", pady=(8, 2))
                    ttk.Entry(col, textvariable=self.v[key], width=w, show=show).pack(anchor="w")
                self.msg.config(text=self.TEST + "\nWe only keep the card brand, last 4 digits and expiry. The full "
                                     "number and CVV are never stored.")
            elif kind == "paypal":
                field("PAYPAL EMAIL", "detail")
                self.msg.config(text="You'll approve each payment in PayPal (simulated in this demo).")
            elif kind in ("gcash", "maya"):
                field(f"{db.KIND_NAMES[kind].upper()} MOBILE NUMBER", "detail")
                self.msg.config(text="Use the Philippine mobile number registered to your wallet, e.g. 0917 123 4567.")
            else:
                name = db.KIND_NAMES[kind]
                device = "Face ID or fingerprint" if kind == "apple_pay" else "your screen lock"
                L(self.form, f"{name} uses the wallet already set up on this device.", 10).pack(anchor="w", pady=(8, 0))
                self.msg.config(text=f"You'll confirm each payment with {device} (simulated in this demo).")

        def save(self):
            v = {k: var.get() for k, var in self.v.items()}
            try:
                new_id = db.add_payment_method(self.app.user["id"], self.kind, v["holder"], v["number"],
                                               v["expiry"], v["cvv"], v["detail"])
            except AppError as e:
                return messagebox.showerror("Payment method", str(e), parent=self)
            self.destroy()
            if self.on_done:
                self.on_done(new_id)

    # ============================================================ the guest's payments window
    class PaymentsWindow(Page):
        def __init__(self, app):
            super().__init__(app.root)
            self.app = app
            self.title("Payments")
            self.geometry("840x740")
            self.minsize(660, 520)
            self.configure(bg=PAPER)
            self.bind("<Escape>", lambda e: self.destroy())
            header(self, "PAYMENTS", "How you", "pay.", "Save a way to pay once and book in two taps. "
                   "You're only charged after a host accepts your request.")
            self.cv, inner = scroller(self)
            pad = tk.Frame(inner, bg=PAPER)
            pad.pack(fill="both", expand=True, padx=SIDE, pady=(0, 30))
            section(pad, "Payment methods",
                    lambda p: button(p, "+ Add a payment method", self.add), top=22)
            self.list_box = tk.Frame(pad, bg=PAPER)
            self.list_box.pack(fill="x")
            section(pad, "How payments work")
            info_card(pad, [
                ("You pay RoamRest, not the host", "When a host accepts, you pay RoamRest directly in full, or in two "
                 "parts if your trip is 15+ days away. Cards, wallets, PayPal, GCash and Maya are accepted."),
                ("Your money is held in escrow", "RoamRest keeps your payment and releases it to the host about "
                 "24 hours after you check in."),
                ("Refunds go back to where they came from", "If a stay is cancelled, the refund follows the host's "
                 "cancellation policy (Flexible, Moderate or Strict) and returns to your original payment method."),
                ("Pay in your own currency", "Prices show in the currency chosen under Languages & currency.")])
            section(pad, "Recent payments")
            self.pay_box = tk.Frame(pad, bg=PAPER)
            self.pay_box.pack(fill="x")
            self.refresh()

        def refresh(self):
            for box in (self.list_box, self.pay_box):
                for w in box.winfo_children():
                    w.destroy()
            uid = self.app.user["id"]
            methods = db.payment_methods(uid)
            if not methods:
                c = card(self.list_box, padx=18, pady=22)
                c.pack(fill="x")
                L(c, "No payment methods yet", 13, "bold", family="Georgia", bg=CARD).pack()
                L(c, "Add a card or wallet so you can request your first stay.", 10, fg=MUTED, bg=CARD).pack(pady=(4, 12))
                button(c, "+ Add a payment method", self.add).pack()
            for m in methods:
                self.build_method(m)
            self.build_recent(uid)

        def build_method(self, m):
            c = card(self.list_box, padx=16, pady=12)
            c.pack(fill="x", pady=(0, 10))
            c.columnconfigure(1, weight=1)
            badge(c, method_badge(m)).grid(row=0, column=0, rowspan=2, padx=(0, 14))
            L(c, db.method_label(m), 12, "bold", bg=CARD).grid(row=0, column=1, sticky="w")
            L(c, db.method_sub(m), 9, fg=MUTED, bg=CARD).grid(row=1, column=1, sticky="w")
            side = tk.Frame(c, bg=CARD)
            side.grid(row=0, column=2, rowspan=2, sticky="e")
            if m["is_default"]:
                L(side, " DEFAULT ", 8, "bold", fg=CONFIRMED[1], bg=CONFIRMED[2]).pack(side="left", padx=(0, 12))
            else:
                link(side, "Make default", lambda i=m["id"]: self.make_default(i), fg=CLAY, size=9, bold=True).pack(
                    side="left", padx=(0, 12))
            link(side, "Remove", lambda i=m["id"]: self.remove(i), fg=MUTED, size=9).pack(side="left")

        def build_recent(self, uid):
            trips = [dict(t) for t in db.guest_bookings(uid)]
            if not trips:
                L(self.pay_box, "No payments yet. Once you request a stay it shows up here.", 11, slant="italic",
                  family="Georgia", fg=MUTED).pack(anchor="w", pady=(2, 8))
                return
            box = card(self.pay_box)
            box.pack(fill="x")
            f, tree = make_tree(box, [("ref", "Reference"), ("stay", "Stay"), ("method", "Paid with"),
                                      ("plan", "Plan"), ("amount", "Amount"), ("status", "Status")],
                                [90, 190, 150, 90, 90, 170], min(len(trips), 7))
            f.pack(fill="both", expand=True)
            tree.column("amount", anchor="e")
            tree.heading("amount", anchor="e")
            for t in trips:
                s = db.payment_summary(t)
                tree.insert("", "end", values=(
                    ui.booking_ref(t), t["title"], s["method"] or "\u2014",
                    PLAN_NAMES.get(s["plan"], "") if s["recorded"] else "\u2014", money(t["total_price"]),
                    payment_status_text(ui, t, s)))

        def add(self):
            AddPaymentDialog(self.app, on_done=lambda _id: self.refresh())

        def make_default(self, mid):
            try:
                db.set_default_method(self.app.user["id"], mid)
            except AppError as e:
                return messagebox.showerror("Payments", str(e), parent=self)
            self.refresh()

        def remove(self, mid):
            if not messagebox.askyesno("Remove", "Remove this payment method?", parent=self):
                return
            try:
                db.remove_payment_method(self.app.user["id"], mid)
            except AppError as e:
                return messagebox.showerror("Payments", str(e), parent=self)
            self.refresh()

    CONFIRMED = ui.STATUS_STYLE["confirmed"]

    # ============================================================ the "Pay with" step on a listing page
    class PaymentPicker(tk.Frame):
        ADD = "+  Add a payment method\u2026"

        def __init__(self, parent, page):
            super().__init__(parent, bg=CARD)
            self.page, self.app, self.listing = page, page.app, page.r
            self.methods, self.labels, self.total = [], [], None
            self.v_method, self.v_plan = tk.StringVar(), tk.StringVar(value="full")
            L(self, "PAY WITH", 7, "bold", bg=CARD).pack(anchor="w")
            self.combo = ttk.Combobox(self, textvariable=self.v_method, state="readonly", font=("Arial", 10))
            self.combo.pack(fill="x", pady=(3, 0))
            self.combo.bind("<<ComboboxSelected>>", self.on_pick)
            L(self, "PAYMENT PLAN", 7, "bold", bg=CARD).pack(anchor="w", pady=(10, 0))
            opts = {"bg": CARD, "activebackground": CARD, "anchor": "w", "justify": "left", "wraplength": 290,
                    "font": ("Arial", 9), "cursor": "hand2", "bd": 0, "highlightthickness": 0, "fg": INK,
                    "variable": self.v_plan}
            self.r_full = tk.Radiobutton(self, value="full", **opts)
            self.r_split = tk.Radiobutton(self, value="split", **opts)
            self.r_full.pack(fill="x", pady=(2, 0))
            self.r_split.pack(fill="x")
            self.policy = L(self, "", 8, fg=MUTED, bg=CARD, wraplength=290, justify="left")
            self.policy.pack(anchor="w", pady=(8, 0))
            pol = self.listing["cancellation_policy"] if "cancellation_policy" in self.listing.keys() else db.DEFAULT_POLICY
            self.policy.config(text=f"Cancellation: {pol}. {db.POLICY_TEXT.get(pol, '')}")
            self.refresh()

        def refresh(self, select=None):
            user = self.app.user
            self.methods = list(db.payment_methods(user["id"])) if user else []
            self.labels = [db.method_label(m) for m in self.methods]
            if not user:
                self.combo.config(values=[], state="disabled")
                self.v_method.set("Log in to choose how you'll pay")
                return
            self.combo.config(values=self.labels + [self.ADD], state="readonly")
            want = select
            if want is None:
                cur = self.v_method.get()
                want = next((m["id"] for m, lab in zip(self.methods, self.labels) if lab == cur), None)
            pick = next((m for m in self.methods if m["id"] == want), None) or \
                next((m for m in self.methods if m["is_default"]), None) or (self.methods[0] if self.methods else None)
            self.v_method.set(db.method_label(pick) if pick else "No payment method yet \u2014 add one")

        def on_pick(self, _e=None):
            if self.v_method.get() == self.ADD:
                self.add_method()

        def add_method(self):
            if not self.app.user:
                messagebox.showinfo("Log in", "Please log in or sign up to add a payment method.", parent=self.page)
                return self.app.open_auth()
            before = self.v_method.get()
            self.v_method.set(before if before != self.ADD else "")
            AddPaymentDialog(self.app, on_done=lambda mid: self.refresh(select=mid))
            self.refresh()

        def set_quote(self, total, check_in=""):
            """Re-label the two plans for the current dates and price. total=None means the dates are invalid."""
            self.total = total
            eligible = total is not None and db.split_eligible(check_in)
            if total is None:
                self.r_full.config(text="Pay in full")
                self.r_split.config(text="Pay in 2 parts", state="disabled")
            else:
                self.r_full.config(text=f"Pay in full \u2014 {money0(total)} after the host accepts")
                if eligible:
                    a, b = db.split_amounts(total)
                    self.r_split.config(
                        state="normal", text=f"Pay in 2 parts \u2014 {money0(a)} after the host accepts, "
                                             f"{money0(b)} on {fmt_day(db.split_due(check_in).isoformat())}")
                else:
                    self.r_split.config(state="disabled", text=f"Pay in 2 parts \u2014 only when check-in is "
                                                               f"{db.SPLIT_MIN_LEAD}+ days away")
            if not eligible and self.v_plan.get() == "split":
                self.v_plan.set("full")

        def choice(self):
            """(method_id, plan, method_row). Raises AppError with a friendly message."""
            label = self.v_method.get()
            if label in self.labels:
                m = self.methods[self.labels.index(label)]
                return m["id"], self.v_plan.get(), m
            raise AppError("Choose how you'd like to pay.")

    # ============================================================ host: payout method
    class PayoutMethodDialog(tk.Toplevel):
        def __init__(self, app, on_done=None):
            super().__init__(app.root)
            self.app, self.on_done = app, on_done
            self.title("Payout method")
            self.configure(bg=PAPER, padx=30, pady=22)
            self.resizable(False, False)
            self.transient(ui.front_window() or app.root)
            L(self, "How would you like to be paid?", 18, "bold", family="Georgia").pack(anchor="w")
            L(self, "You can change this any time. Payouts are sent about 24 hours after a guest checks in.", 9,
              fg=MUTED, wraplength=460, justify="left").pack(anchor="w", pady=(4, 12))
            self.kind = "bank"
            self.chips = {}
            chips = tk.Frame(self, bg=PAPER)
            chips.pack(anchor="w")
            for i, (key, (name, _eta, _lab)) in enumerate(db.PAYOUT_KINDS.items()):
                b = tk.Button(chips, text=name.split(" (")[0], relief="flat", bd=0, font=("Arial", 9, "bold"),
                              padx=12, pady=5, cursor="hand2", command=lambda k=key: self.pick(k))
                b.grid(row=i // 3, column=i % 3, padx=(0, 6), pady=(0, 6), sticky="w")
                self.chips[key] = b
            self.form = tk.Frame(self, bg=PAPER)
            self.form.pack(fill="x", pady=(6, 0))
            self.v = {"holder": tk.StringVar(), "detail": tk.StringVar()}
            self.note = L(self, "", 9, fg=MUTED, wraplength=460, justify="left")
            self.note.pack(anchor="w", pady=(10, 0))
            bar = tk.Frame(self, bg=PAPER)
            bar.pack(anchor="w", pady=(14, 0))
            button(bar, "Save payout method", self.save).pack(side="left")
            button(bar, "Cancel", self.destroy, False).pack(side="left", padx=8)
            self.bind("<Escape>", lambda e: self.destroy())
            cur = db.payout_method(app.user["id"])
            self.pick(cur["kind"] if cur else "bank")

        def pick(self, kind):
            self.kind = kind
            for k, b in self.chips.items():
                on = k == kind
                b.config(bg=INK if on else CARD, fg=PAPER if on else MUTED, activebackground=INK if on else LINE,
                         activeforeground=PAPER if on else INK)
            for w in self.form.winfo_children():
                w.destroy()
            for var in self.v.values():
                var.set("")
            name, eta, label = db.PAYOUT_KINDS[kind]
            if kind in ("bank", "fast_pay", "wire"):
                L(self.form, "ACCOUNT HOLDER NAME", 9, "bold", fg=MUTED).pack(anchor="w", pady=(8, 2))
                ttk.Entry(self.form, textvariable=self.v["holder"], width=44).pack(anchor="w")
            L(self.form, label.upper(), 9, "bold", fg=MUTED).pack(anchor="w", pady=(8, 2))
            ttk.Entry(self.form, textvariable=self.v["detail"], width=44).pack(anchor="w")
            extra = {"fast_pay": " Fast Pay needs a debit card (try 4242 4242 4242 4242 in this demo).",
                     "bank": " We keep only the last 4 digits.", "wire": " We keep only the last 4 characters."}.get(kind, "")
            self.note.config(text=f"{name}: money arrives {eta}.{extra}")

        def save(self):
            try:
                db.set_payout_method(self.app.user["id"], self.kind, self.v["holder"].get(), self.v["detail"].get())
            except AppError as e:
                return messagebox.showerror("Payout method", str(e), parent=self)
            self.destroy()
            if self.on_done:
                self.on_done()

    # ============================================================ host: earnings + payouts
    class PayoutsWindow(Page):
        STATE = {"escrow": ("In escrow", PENDING), "held": ("Held \u00B7 first payout", PENDING),
                 "paid": ("Paid out", CONFIRMED), "waiting": ("Add payout method", CANCELLED)}

        def __init__(self, app):
            super().__init__(app.root)
            self.app = app
            self.title("Earnings")
            self.geometry("1020x760")
            self.minsize(860, 560)
            self.configure(bg=PAPER)
            self.bind("<Escape>", lambda e: self.destroy())
            head = header(self, "EARNINGS", "Paid to", "you.",
                          "RoamRest holds each guest's payment in escrow and pays you about 24 hours after check-in, "
                          "minus the flat 3% host fee.")
            self.cv, inner = scroller(self)
            self.pad = tk.Frame(inner, bg=PAPER)
            self.pad.pack(fill="both", expand=True, padx=SIDE, pady=(0, 30))
            self.refresh()

        def refresh(self):
            for w in self.pad.winfo_children():
                w.destroy()
            uid = self.app.user["id"]
            rows, summ = db.host_payouts(uid)
            method = db.payout_method(uid)

            # ---- stat tiles
            tiles = tk.Frame(self.pad, bg=PAPER)
            tiles.pack(fill="x", pady=(22, 0))
            specs = [("In escrow", summ["escrow"], "Released ~24h after check-in"),
                     ("Held (first payout)", summ["held"], "Until 24h after check-out"),
                     ("Paid out", summ["paid"], "Sent to your payout method"),
                     ("Waiting for you", summ["waiting"], "Add a payout method")]
            for i, (label, amount, sub) in enumerate(specs):
                t = card(tiles, padx=16, pady=12)
                t.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 10, 0))
                tiles.columnconfigure(i, weight=1, uniform="tile")
                warn = label == "Waiting for you" and amount > 0
                L(t, label.upper(), 8, "bold", fg=CANCELLED[1] if warn else MUTED, bg=CARD).pack(anchor="w")
                L(t, money(amount), 18, "bold", family="Georgia", bg=CARD,
                  fg=CANCELLED[1] if warn else INK).pack(anchor="w", pady=(4, 0))
                L(t, sub, 8, fg=MUTED, bg=CARD).pack(anchor="w")
            if summ["next"]:
                L(self.pad, f"Next payout: {ui.fmt_when(summ['next'].isoformat(timespec='seconds'))}", 10, "bold",
                  fg=CLAY).pack(anchor="w", pady=(12, 0))

            # ---- payout method
            section(self.pad, "Payout method")
            c = card(self.pad, padx=18, pady=14)
            c.pack(fill="x")
            c.columnconfigure(1, weight=1)
            if method:
                badge(c, method["kind"]).grid(row=0, column=0, rowspan=2, padx=(0, 14))
                L(c, db.payout_label(method), 12, "bold", bg=CARD).grid(row=0, column=1, sticky="w")
                eta = db.PAYOUT_KINDS[method["kind"]][1]
                L(c, f"Payouts arrive {eta}" + (f"  \u00B7  {method['holder']}" if method["holder"] else ""), 9,
                  fg=MUTED, bg=CARD).grid(row=1, column=1, sticky="w")
                side = tk.Frame(c, bg=CARD)
                side.grid(row=0, column=2, rowspan=2)
                button(side, "Change", self.set_method, False, small=True).pack(side="left")
                button(side, "Remove", self.remove_method, False, small=True).pack(side="left", padx=(6, 0))
            else:
                L(c, "No payout method yet", 12, "bold", family="Georgia", bg=CARD).grid(row=0, column=1, sticky="w")
                L(c, "Add one so your earnings can be sent to you. Until then they wait here safely.", 9, fg=MUTED,
                  bg=CARD).grid(row=1, column=1, sticky="w")
                button(c, "Set up payouts", self.set_method).grid(row=0, column=2, rowspan=2)

            # ---- the rules
            section(self.pad, "How you get paid")
            info_card(self.pad, [
                ("When", "About 24 hours after the guest checks in. Stays of 28+ nights are paid in monthly instalments."),
                ("New hosts", "Your very first payout is held until 24 hours after check-out (never longer than 30 days) "
                              "as a security measure. After that, payouts follow the normal schedule."),
                ("Your payout", "The nightly rate plus any fees you charge, minus RoamRest's flat 3% host fee."),
                ("Cancellations", "If a stay is cancelled, the guest's refund and your payout are worked out from the "
                                  "listing's cancellation policy: Flexible, Moderate or Strict.")])

            # ---- payouts table
            section(self.pad, "Payouts")
            if not rows:
                L(self.pad, "No payouts yet. Confirmed reservations will appear here.", 11, slant="italic",
                  family="Georgia", fg=MUTED).pack(anchor="w", pady=(2, 8))
                return
            box = card(self.pad)
            box.pack(fill="x")
            f, tree = make_tree(box, [("title", "Place"), ("stay", "Stay"), ("gross", "Guest paid"), ("fee", "Fee (3%)"),
                                      ("amount", "You receive"), ("when", "Pays out"), ("status", "Status")],
                                [150, 150, 90, 80, 100, 130, 130], min(len(rows), 8))
            f.pack(fill="both", expand=True)
            for col in ("gross", "fee", "amount"):
                tree.column(col, anchor="e")
                tree.heading(col, anchor="e")
            for i, r in enumerate(rows):
                label = self.STATE[r["state"]][0]
                part = f" ({r['seq']}/{r['of']})" if r["of"] > 1 else ""
                tree.insert("", "end", iid=str(i), tags=(r["state"],), values=(
                    r["title"], ui.fmt_range(r["check_in"], r["check_out"]),
                    money(r["gross"]) if r["gross"] is not None else "\u2014",
                    f"\u2212{money(r['fee'])}" if r["fee"] is not None else "\u2014",
                    money(r["amount"]) + part, fmt_day(r["release_at"].strftime("%Y-%m-%d")), label))
            tree.tag_configure("escrow", foreground=PENDING[1])
            tree.tag_configure("held", foreground=PENDING[1])
            tree.tag_configure("paid", foreground=CONFIRMED[1])
            tree.tag_configure("waiting", foreground=CANCELLED[1])

        def set_method(self):
            PayoutMethodDialog(self.app, on_done=self.refresh)

        def remove_method(self):
            if messagebox.askyesno("Payout method", "Remove your payout method? Earnings will wait until you add "
                                                    "a new one.", parent=self):
                db.remove_payout_method(self.app.user["id"])
                self.refresh()

        on_currency = refresh

    return {"AddPaymentDialog": AddPaymentDialog, "PaymentsWindow": PaymentsWindow, "PaymentPicker": PaymentPicker,
            "PayoutMethodDialog": PayoutMethodDialog, "PayoutsWindow": PayoutsWindow}


def install(ns):
    """Called from app.py with globals(): adds the payment screens and the trip payment breakdown."""
    ui = _UI(ns)
    screens = make_screens(ui)
    ns.update(screens)
    ns["payment_details"] = make_payment_details(ui)
    # PayoutMethodDialog / AddPaymentDialog are referenced by the windows through these module-level names
    return screens