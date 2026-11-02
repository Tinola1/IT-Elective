"""The scrolling landing page: hero + search, stays rows, sections and footer (a mixin of RoamRestApp)."""

import tkinter as tk
from datetime import date
from tkinter import messagebox
from tkinter import ttk

import database as db
from content import FAQ, FOOT_COLS, PILLARS, POLICIES, REVIEWS, STATS, STEPS, TAGS
from helpers import L, button, heading, link, money0
from images import cover_file
from navigation import front_window
from theme import APRICOT, CARD, CARD_W, CLAY, CLAY_DEEP, FOOT, GREEN, IMG_H, INK, LINE, MUTED, PAPER, PAPER2, PILL_BG, ROW_W
from toolkit import DatePopup


class LandingPage:
    """Page scaffolding, search and every landing-page section."""

    # ----- layout helpers
    def sec(self, bg, pady=(60, 60), key=None, width=990):
        """A full-width band with a centered content frame. Always pack children into `inner`."""
        outer = tk.Frame(self.page, bg=bg)
        outer.pack(fill="x")
        inner = tk.Frame(outer, bg=bg)
        inner.pack(pady=pady)
        tk.Frame(inner, bg=bg, width=width, height=1).pack()
        if key:
            self.anchors[key] = outer
        return outer, inner

    def rule(self):
        tk.Frame(self.page, bg=LINE, height=1).pack(fill="x")

    def _wheel(self, e):
        try:
            if str(e.widget.winfo_toplevel()) != str(self.root):
                return
        except Exception:
            return
        self.canvas.yview_scroll(int(-e.delta / 120), "units")

    def goto(self, key):
        self.root.update_idletasks()
        if key == "top":
            return self.canvas.yview_moveto(0)
        total = max(self.page.winfo_height(), 1)
        self.canvas.yview_moveto(max(0, self.anchors[key].winfo_y() / total))

    def focus_search(self):
        self.goto("top")
        self.e_where.focus_set()

    # ----- hero
    def build_hero(self):
        _, inner = self.sec(PAPER, (46, 46))
        content = tk.Frame(inner, bg=PAPER)
        content.pack(anchor="w")
        left = tk.Frame(content, bg=PAPER)
        left.grid(row=0, column=0, sticky="n", padx=(0, 50))
        right = tk.Frame(content, bg=PAPER)
        right.grid(row=0, column=1, sticky="n")

        L(left, "VERIFIED STAYS  \u00B7  190 CITIES  \u00B7  ZERO HIDDEN FEES", 9, "bold", fg=CLAY).pack(anchor="w")
        L(left, "Wherever you roam,", 34, "bold", family="Georgia").pack(anchor="w", pady=(12, 0))
        L(left, "rest like you belong.", 34, "bold", "italic", family="Georgia", fg=CLAY).pack(anchor="w")
        L(left, "Verified homes, cabins and lofts with everything a hotel forgets \u2014 full kitchens, "
                "fast Wi-Fi, space to actually live \u2014 at prices hotels can't touch.",
          12, fg=MUTED, wraplength=540, justify="left").pack(anchor="w", pady=(16, 0))
        L(left, "The price you see is the price you pay.", 12, "bold").pack(anchor="w")

        sf = tk.Frame(left, bg=CARD, highlightbackground=LINE, highlightthickness=1, padx=12, pady=10)
        sf.pack(anchor="w", pady=(22, 0))
        self.v_where, self.v_in, self.v_out = tk.StringVar(), tk.StringVar(), tk.StringVar()
        self.v_guests = tk.StringVar(value="")  # blank = any number of guests (a default of 2 hid 1-guest rooms)
        self.e_where = ttk.Entry(sf, textvariable=self.v_where, width=17)
        fields = [("WHERE", self.e_where),
                  ("CHECK-IN", ttk.Entry(sf, textvariable=self.v_in, width=12)),
                  ("CHECK-OUT", ttk.Entry(sf, textvariable=self.v_out, width=12)),
                  ("GUESTS", ttk.Spinbox(sf, from_=1, to=16, textvariable=self.v_guests, width=4))]
        for i, (lbl, w) in enumerate(fields):
            L(sf, lbl, 7, "bold", fg=MUTED, bg=CARD).grid(row=0, column=i, sticky="w", padx=6)
            w.grid(row=1, column=i, padx=6, pady=(2, 0))
            w.bind("<Return>", lambda e: self.run_search(True))
        e_in, e_out = fields[1][1], fields[2][1]
        for entry, which in ((e_in, "in"), (e_out, "out")):  # click a date field -> calendar (typing still works)
            entry.bind("<Button-1>", lambda ev, e=entry, w=which: DatePopup.open(
                e, [e_in, e_out], self.v_in, self.v_out, w, align="left"), add="+")
        button(sf, "Search", lambda: self.run_search(True)).grid(row=1, column=4, padx=(10, 2))
        button(sf, "Reset", self.reset, False).grid(row=1, column=5, padx=2)
        L(left, "Dates and guests are optional. Fill them in to see only stays free on those dates and big enough for your group.",
          8, fg=MUTED).pack(anchor="w", pady=(5, 0))
        L(left, "4.9 \u2605 from 12,400+ verified travelers \u2014 and 10,000+ stays booked this year alone.",
          9, fg=MUTED, wraplength=540, justify="left").pack(anchor="w", pady=(16, 0))

        card = tk.Frame(right, bg=CARD, highlightbackground=LINE, highlightthickness=1, padx=10, pady=10)
        card.pack()
        hero_img = tk.Label(card, bg=CARD, bd=0)
        hero_img.pack()
        self.photos.attach(hero_img, "roamrest-hero", 340, 290, 150, CARD, "Sayulita, Mexico")
        L(card, "\u201CFelt like borrowing a friend's home.\u201D", 11, slant="italic", family="Georgia",
          fg=MUTED, bg=CARD).pack(pady=(10, 0))
        L(card, "\u2014 Elena P., verified guest \u00B7 Sayulita, Mexico", 9, "bold", fg=MUTED, bg=CARD).pack(pady=(2, 4))

    # ----- stats + press
    def build_trust(self):
        self.rule()
        _, inner = self.sec(PAPER, (22, 12))
        row = tk.Frame(inner, bg=PAPER)
        row.pack()
        for i, (num, text) in enumerate(STATS):
            if i:
                tk.Frame(row, bg=LINE, width=1).grid(row=0, column=2 * i - 1, sticky="ns")
            col = tk.Frame(row, bg=PAPER, padx=44)
            col.grid(row=0, column=2 * i)
            L(col, num, 28, "bold", family="Georgia").pack()
            L(col, text, 10, fg=MUTED).pack()
        self.rule()
        L(self.page, "AS FEATURED IN      VOYAGE      The Weekend Edit      NOMAD&CO      Stayfolio      wanderlist.",
          9, fg="#A79878").pack(pady=14)

    # ----- how it works
    def build_how(self):
        _, inner = self.sec(PAPER, (56, 60), "how")
        L(inner, "HOW IT WORKS", 9, "bold", fg=CLAY).pack(anchor="w")
        heading(inner, "Three taps from search", "to sofa.").pack(anchor="w", pady=(10, 6))
        L(inner, "No account gymnastics, no fine print \u2014 the whole journey takes about four minutes.",
          11, fg=MUTED).pack(anchor="w")
        row = tk.Frame(inner, bg=PAPER)
        row.pack(anchor="w", pady=(26, 0))
        for i, (num, title, text) in enumerate(STEPS):
            col = tk.Frame(row, bg=PAPER)
            col.grid(row=0, column=i, sticky="n", padx=(0, 36))
            L(col, num, 34, "bold", "italic", family="Georgia", fg=CLAY).pack(anchor="w")
            L(col, title, 14, "bold", family="Georgia").pack(anchor="w", pady=(4, 4))
            L(col, text, 10, fg=MUTED, wraplength=270, justify="left").pack(anchor="w")

    # ----- stays (Airbnb-style rows)
    def build_stays(self):
        self.rule()
        _, inner = self.sec(PAPER2, (56, 60), "explore", width=ROW_W)
        self.rule()
        L(inner, "BROWSE BY MOOD", 9, "bold", fg=CLAY).pack(anchor="w")
        heading(inner, "What does \u201Caway\u201D", "look like to you?").pack(anchor="w", pady=(10, 6))
        self.result_lbl = L(inner, "", 11, slant="italic", family="Georgia", fg=MUTED)
        self.result_lbl.pack(anchor="w")
        chips = tk.Frame(inner, bg=PAPER2)
        chips.pack(anchor="w", pady=(14, 8))
        for cat in ["All"] + db.CATEGORIES:
            b = tk.Button(chips, text=cat, command=lambda c=cat: self.set_cat(c), relief="flat",
                          font=("Arial", 9, "bold"), padx=12, pady=5, cursor="hand2", bd=0)
            b.pack(side="left", padx=(0, 6))
            self.chips[cat] = b
        self.paint_chips()
        self.rows_frame = tk.Frame(inner, bg=PAPER2)
        self.rows_frame.pack(anchor="w", pady=(18, 0))

    def paint_chips(self):
        for cat, b in self.chips.items():
            on = cat == self.cat
            b.config(bg=INK if on else CARD, fg=PAPER if on else MUTED,
                     activebackground=INK if on else LINE)

    def set_cat(self, cat):
        self.cat = cat
        self.paint_chips()
        self.run_search()

    def reset(self):
        self.v_where.set("")
        self.v_in.set("")
        self.v_out.set("")
        self.v_guests.set("")
        self.cat = "All"
        self.paint_chips()
        self.run_search()

    def stay_nights(self):
        try:
            ci, co = db._check_range(self.v_in.get(), self.v_out.get())
            return (co - ci).days
        except db.AppError:
            return 2

    def run_search(self, scroll=False):
        d_in, d_out, guests = self.v_in.get(), self.v_out.get(), self.v_guests.get()
        try:
            rows = db.search_listings(self.v_where.get(), self.cat, d_in, d_out, guests)
        except db.AppError as e:
            if scroll:  # the user pressed Search: tell them what is wrong with the form
                return messagebox.showerror("Search", str(e), parent=front_window() or self.root)
            # a background refresh (saving, login, currency, chips...): ignore the bad dates quietly
            d_in = d_out = ""
            try:
                rows = db.search_listings(self.v_where.get(), self.cat, "", "", guests)
            except db.AppError:
                guests = ""
                rows = db.search_listings(self.v_where.get(), self.cat)
        self.current = rows
        n = len(rows)
        label = f"{n} stay{'s' if n != 1 else ''} found"
        if self.v_where.get().strip():
            label += f" for \u201C{self.v_where.get().strip()}\u201D"
        if self.cat != "All":
            label += f" in {self.cat}"
        if guests.strip():
            label += f" \u00B7 sleeps {guests.strip()}+"
        if d_in.strip() or d_out.strip():
            label += f" \u00B7 free {d_in.strip() or '?'} \u2192 {d_out.strip() or '?'}"
        self.result_lbl.config(text=label)
        self.render_cards()
        if scroll:
            self.goto("explore")

    def render_cards(self):
        for w in self.rows_frame.winfo_children():
            w.destroy()
        self.hearts = {}
        if not self.current:
            L(self.rows_frame, "Nothing here yet \u2014 try another destination, category or dates.",
              12, slant="italic", family="Georgia", fg=MUTED).pack(pady=30)
            return
        self.nights = self.stay_nights()
        for cat in db.CATEGORIES:
            rows = sorted((r for r in self.current if r["category"] == cat), key=lambda r: r["id"], reverse=True)
            if rows:
                self.build_row(self.rows_frame, "Popular " + cat.lower(), TAGS.get(cat, ""), rows)

    def build_row(self, parent, title, subtitle, rows):
        box = tk.Frame(parent, bg=PAPER2)
        box.pack(fill="x", pady=(0, 26), anchor="w")
        head = tk.Frame(box, bg=PAPER2)
        head.pack(fill="x", pady=(0, 10))
        txt = tk.Frame(head, bg=PAPER2)
        txt.pack(side="left")
        L(txt, title, 16, "bold").pack(anchor="w")
        L(txt, subtitle, 10, fg=MUTED).pack(anchor="w")
        nav = tk.Frame(head, bg=PAPER2)
        nav.pack(side="right")
        cv = tk.Canvas(box, bg=PAPER2, height=IMG_H + 78, width=ROW_W, highlightthickness=0,
                       xscrollincrement=40)
        inner = tk.Frame(cv, bg=PAPER2)
        cv.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda e: cv.configure(scrollregion=cv.bbox("all")))
        for i, sign in enumerate(("\u2039", "\u203A")):
            tk.Button(nav, text=sign, command=lambda d=(-1, 1)[i]: cv.xview_scroll(d * 6, "units"),
                      relief="flat", bg=CARD, activebackground=LINE, fg=INK, bd=0, width=3,
                      font=("Arial", 14, "bold"), cursor="hand2").pack(side="left", padx=3)
        cv.pack(fill="x")
        for r in rows:
            self.build_card(inner, r).pack(side="left", padx=(0, 16), anchor="n")

    def build_card(self, parent, r):
        card = tk.Frame(parent, bg=PAPER2, cursor="hand2")
        img = tk.Label(card, bg=PAPER2, bd=0)
        img.pack()
        self.photos.attach(img, r["image_seed"], CARD_W, IMG_H, 14, PAPER2, r["title"], local=cover_file(r["id"]))
        widgets = [card, img]
        if r["rating"] and r["rating"] >= 4.9:
            badge = tk.Label(img, text="Guest favorite", bg="#FFFFFF", fg=INK, font=("Arial", 9, "bold"),
                             padx=8, pady=3)
            badge.place(x=10, y=10)
            widgets.append(badge)
        heart = tk.Button(img, command=lambda i=r["id"]: self.toggle_fav(i), relief="flat", bd=0,
                          bg="#FFFFFF", activebackground="#FFFFFF", fg=INK, font=("Arial", 12),
                          width=2, cursor="hand2")
        heart.place(relx=1.0, x=-10, y=10, anchor="ne")
        self.hearts[r["id"]] = heart
        self.paint_heart(r["id"])

        total = r["price_per_night"] * self.nights
        rating = f"\u2605 {r['rating']:.2f}" if r["rating"] else "New"
        s = "s" if self.nights != 1 else ""
        for text, size, weight, fg in [(r["title"], 10, "bold", INK), (r["location"], 9, "normal", MUTED),
                                       (f"{money0(total)} for {self.nights} night{s} \u00B7 {rating}", 9, "normal", MUTED)]:
            lb = L(card, text, size, weight, fg=fg, anchor="w", justify="left", wraplength=CARD_W)
            lb.pack(fill="x", pady=(8, 0) if weight == "bold" else (1, 0))
            widgets.append(lb)
        for w in widgets:
            w.bind("<Button-1>", lambda e, i=r["id"]: self.open_stay(i))
        return card

    # ----- why us
    def build_why(self):
        _, inner = self.sec(PAPER, (60, 60), "why")
        content = tk.Frame(inner, bg=PAPER)
        content.pack(anchor="w")
        left = tk.Frame(content, bg=PAPER)
        left.grid(row=0, column=0, sticky="n", padx=(0, 50))
        L(left, "WHY ROAMREST", 9, "bold", fg=CLAY).pack(anchor="w")
        heading(left, "Peace of mind,", "baked in \u2014 not bolted on.", wrap=330).pack(anchor="w", pady=(10, 10))
        L(left, "Most marketplaces treat trust as a checkbox. We built the whole platform around it "
                "\u2014 here's what that means for your next trip.",
          11, fg=MUTED, wraplength=330, justify="left").pack(anchor="w")
        right = tk.Frame(content, bg=PAPER)
        right.grid(row=0, column=1, sticky="n")
        for title, text, proof in PILLARS:
            tk.Frame(right, bg=LINE, height=1).pack(fill="x")
            box = tk.Frame(right, bg=PAPER, pady=18)
            box.pack(fill="x")
            L(box, title, 14, "bold", family="Georgia").pack(anchor="w")
            L(box, text, 10, fg=MUTED, wraplength=520, justify="left").pack(anchor="w", pady=(4, 8))
            L(box, " \u2713 " + proof + " ", 9, "bold", fg="#8F3A13", bg=PILL_BG).pack(anchor="w")
        tk.Frame(right, bg=LINE, height=1).pack(fill="x")

    # ----- reviews
    def build_reviews(self):
        self.rule()
        _, inner = self.sec(PAPER2, (56, 60), "reviews")
        self.rule()
        L(inner, "TRAVELERS TALKING", 9, "bold", fg=CLAY).pack(anchor="w")
        heading(inner, "Don't take", "our word for it.").pack(anchor="w", pady=(10, 6))
        L(inner, "Three guests, three trips, zero scripts \u2014 every review is from a verified, completed stay.",
          11, fg=MUTED).pack(anchor="w")
        row = tk.Frame(inner, bg=PAPER2)
        row.pack(anchor="w", pady=(24, 0))
        for i, (name, meta, quote) in enumerate(REVIEWS):
            card = tk.Frame(row, bg=CARD, highlightbackground=LINE, highlightthickness=1, padx=18, pady=16)
            card.grid(row=0, column=i, sticky="nsew", padx=(0, 16))
            L(card, "\u2605\u2605\u2605\u2605\u2605", 12, fg=CLAY, bg=CARD).pack(anchor="w")
            L(card, "\u201C" + quote + "\u201D", 11, family="Georgia", bg=CARD, wraplength=265,
              justify="left").pack(anchor="w", pady=(8, 10))
            L(card, name, 10, "bold", bg=CARD).pack(anchor="w")
            L(card, meta, 9, fg=MUTED, bg=CARD).pack(anchor="w")

    # ----- host + earnings calculator
    def build_host(self):
        _, inner = self.sec(GREEN, (70, 70), "host")
        content = tk.Frame(inner, bg=GREEN)
        content.pack(anchor="w")
        left = tk.Frame(content, bg=GREEN)
        left.grid(row=0, column=0, sticky="n", padx=(0, 50))
        L(left, "FOR HOSTS", 9, "bold", fg=APRICOT).pack(anchor="w")
        heading(left, "Your space could be", "paying for itself.", fg=PAPER, accent_fg=APRICOT,
                wrap=480).pack(anchor="w", pady=(10, 10))
        L(left, "List a spare room, the whole place, or just the weekends you're away. You set the price, "
                "the calendar and the house rules \u2014 we bring verified guests, escrow payments and "
                "$1M damage coverage.", 11, fg="#CFC9B6", wraplength=470, justify="left").pack(anchor="w")
        for t in ("Free to list \u2014 a flat 3% host fee, and that's it",
                  "Free professional photography in 40+ cities",
                  "You approve every guest before they book"):
            L(left, "\u2713  " + t, 10, fg="#E5E0CD").pack(anchor="w", pady=(8, 0))
        tk.Button(left, text="Start hosting \u2014 it's free", command=self.start_hosting, bg=PAPER, fg=INK,
                  activebackground="#FFFFFF", relief="flat", font=("Arial", 11, "bold"),
                  padx=20, pady=8, cursor="hand2").pack(anchor="w", pady=(22, 0))

        calc = tk.Frame(content, bg=PAPER, padx=26, pady=22)
        calc.grid(row=0, column=1, sticky="n")
        L(calc, "What could you earn?", 16, "bold", family="Georgia").pack(anchor="w")
        L(calc, "Drag the sliders \u2014 the maths is honest, like everything else here.", 9, fg=MUTED).pack(
            anchor="w", pady=(2, 12))

        def slider(label, lo, hi, step):
            top = tk.Frame(calc, bg=PAPER)
            top.pack(fill="x")
            L(top, label, 10, "bold").pack(side="left")
            val = L(top, "", 11, "bold", fg=CLAY_DEEP)
            val.pack(side="right")
            sc = tk.Scale(calc, from_=lo, to=hi, resolution=step, orient="horizontal", showvalue=0,
                          length=300, bg=PAPER, troughcolor=LINE, highlightthickness=0, bd=0,
                          activebackground=CLAY, command=lambda v: self.calc())
            sc.pack(fill="x", pady=(2, 12))
            return sc, val

        self.sc_rate, self.rate_lbl = slider("Your nightly rate", 40, 400, 5)
        self.sc_nights, self.nights_lbl = slider("Nights hosted per month", 1, 30, 1)
        tk.Frame(calc, bg=LINE, height=1).pack(fill="x", pady=(2, 10))
        L(calc, "ESTIMATED MONTHLY", 8, "bold", fg=MUTED).pack(anchor="w")
        self.out_month = L(calc, "", 26, "bold", family="Georgia")
        self.out_month.pack(anchor="w")
        self.out_year = L(calc, "", 10, "bold", fg=MUTED)
        self.out_year.pack(anchor="w")
        self.out_flavor = L(calc, "", 11, slant="italic", family="Georgia", fg=CLAY_DEEP)
        self.out_flavor.pack(anchor="w", pady=(8, 0))
        L(calc, "Estimate after RoamRest's flat 3% host fee. Actual earnings vary by city and season.",
          8, fg="#A79D85", wraplength=300, justify="left").pack(anchor="w", pady=(10, 0))
        self.sc_rate.set(120)
        self.sc_nights.set(15)
        self.calc()

    def calc(self):
        r, n = int(self.sc_rate.get()), int(self.sc_nights.get())
        m = round(r * n * 0.97)  # in US dollars
        self.rate_lbl.config(text=money0(r))
        self.nights_lbl.config(text=str(n))
        self.out_month.config(text=f"{money0(m)}  / month")
        self.out_year.config(text=f"\u2248 {money0(m * 12)} a year")
        self.out_flavor.config(text=(
            "That's utilities and groceries sorted." if m < 500 else
            "A serious second income." if m < 1200 else
            "That's rent covered, in most cities." if m < 2500 else
            "Hello, sabbatical fund."))

    # ----- FAQ
    def build_faq(self):
        _, inner = self.sec(PAPER, (60, 60), "faq")
        content = tk.Frame(inner, bg=PAPER)
        content.pack(anchor="w")
        left = tk.Frame(content, bg=PAPER)
        left.grid(row=0, column=0, sticky="n", padx=(0, 50))
        L(left, "GOOD QUESTIONS", 9, "bold", fg=CLAY).pack(anchor="w")
        heading(left, "Ask us anything \u2014", "before you book.", wrap=330).pack(anchor="w", pady=(10, 10))
        L(left, "The five things nearly everyone asks, answered in plain English.", 11, fg=MUTED,
          wraplength=330, justify="left").pack(anchor="w")
        L(left, "support@roamrest.com", 11, "bold", fg=CLAY).pack(anchor="w", pady=(12, 0))
        right = tk.Frame(content, bg=PAPER)
        right.grid(row=0, column=1, sticky="n")
        for i, (q, a) in enumerate(FAQ):
            row = tk.Frame(right, bg=PAPER)
            row.pack(fill="x")
            tk.Frame(row, bg=LINE, height=1).pack(fill="x")
            b = tk.Button(row, text=q + "    +", command=lambda i=i: self.toggle_faq(i), bg=PAPER,
                          activebackground=PAPER, fg=INK, relief="flat", bd=0, anchor="w",
                          justify="left", wraplength=520, font=("Georgia", 12, "bold"),
                          cursor="hand2", pady=12)
            b.pack(fill="x")
            ans = L(row, a, 10, fg=MUTED, wraplength=520, justify="left")
            self.faq_items.append((b, ans, q))
        tk.Frame(right, bg=LINE, height=1).pack(fill="x")

    def toggle_faq(self, idx):
        for j, (b, ans, q) in enumerate(self.faq_items):
            if j == idx and not ans.winfo_ismapped():
                ans.pack(fill="x", pady=(0, 14))
                b.config(text=q + "    \u2013")
            else:
                ans.pack_forget()
                b.config(text=q + "    +")

    # ----- closing CTA + footer
    def build_cta(self):
        _, inner = self.sec(CLAY, (64, 64))
        heading(inner, "Your next", "home away from home is one search away.", size=26, fg="#FFF6EC",
                accent_fg="#FFD6B4", wrap=720, anchor="center", justify="center").pack()
        tk.Button(inner, text="Start searching  \u2192", command=self.focus_search, bg=INK, fg=PAPER,
                  activebackground="#3B3524", activeforeground=PAPER, relief="flat",
                  font=("Arial", 11, "bold"), padx=24, pady=9, cursor="hand2").pack(pady=(24, 0))
        L(inner, "Free cancellation on most stays \u00B7 10,000+ bookings made this year", 9,
          fg="#F4C29F").pack(pady=(14, 0))

    def foot_action(self, act):
        if act is None:
            return
        if act[0] == "cat":
            self.set_cat(act[1])
            self.goto("explore")
        else:
            self.goto(act[1])

    def build_footer(self):
        _, inner = self.sec(FOOT, (46, 24))
        row = tk.Frame(inner, bg=FOOT)
        row.pack(anchor="w")
        brand = tk.Frame(row, bg=FOOT)
        brand.grid(row=0, column=0, sticky="n", padx=(0, 60))
        L(brand, "\u2229 RoamRest", 16, "bold", family="Georgia", fg=PAPER).pack(anchor="w")
        L(brand, "Home-like stays in 190+ cities,\nwithout the fine print.", 10, fg="#B8B09B",
          justify="left").pack(anchor="w", pady=(8, 0))
        for i, (title, items) in enumerate(FOOT_COLS, start=1):
            col = tk.Frame(row, bg=FOOT)
            col.grid(row=0, column=i, sticky="n", padx=(0, 40))
            L(col, title, 8, "bold", fg="#8F8670").pack(anchor="w", pady=(0, 8))
            for text, act in items:
                link(col, text, lambda a=act: self.foot_action(a), fg="#B8B09B", hover="#FFFFFF").pack(
                    anchor="w", pady=2)
        tk.Frame(inner, bg="#342F22", height=1).pack(fill="x", pady=(26, 14))
        base = tk.Frame(inner, bg=FOOT)
        base.pack(fill="x")
        L(base, f"\u00A9 {date.today().year} RoamRest, Inc. Made for wanderers.", 9, fg="#8F8670").pack(side="left")
        for name in reversed(list(POLICIES)):
            link(base, name, lambda n=name: messagebox.showinfo(n, POLICIES[n], parent=front_window() or self.root),
                 fg="#8F8670", size=9, hover="#FFFFFF").pack(side="right", padx=8)
