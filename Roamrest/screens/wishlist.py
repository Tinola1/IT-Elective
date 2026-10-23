"""The wishlist (saved stays) page."""

import tkinter as tk
from tkinter import messagebox
from tkinter import ttk

import database as db
from helpers import L, button, fmt_night
from images import cover_file
from navigation import Page
from theme import CARD, CLAY, CLAY_DEEP, INK, LINE, MUTED, PAPER


class FavoritesWindow(Page):
    """Wishlist: the stays a guest saved, shown as the same kind of cards as the home page
    (photo, category tag, heart, rating, price) in a grid that re-flows with the window width."""
    PHOTO_W, PHOTO_H, GAP, SIDE = 220, 148, 18, 30

    def __init__(self, app):
        super().__init__(app.root)
        self.app = app
        self.title("Wishlist")
        self.geometry("860x680")
        self.minsize(560, 460)
        self.configure(bg=PAPER)
        self.rows = []
        self.cols = 0
        self.bind("<Escape>", lambda e: self.destroy())

        # ----- header: eyebrow, serif title with an italic clay accent, count, clear-all
        head = tk.Frame(self, bg=PAPER, padx=self.SIDE)
        head.pack(fill="x", pady=(24, 16))
        left = tk.Frame(head, bg=PAPER)
        left.pack(side="left")
        L(left, "YOUR WISHLIST", 9, "bold", fg=CLAY).pack(anchor="w")
        title = tk.Frame(left, bg=PAPER)
        title.pack(anchor="w", pady=(4, 0))
        L(title, "Saved for ", 24, "bold", family="Georgia").pack(side="left")
        L(title, "someday.", 24, "bold", "italic", family="Georgia", fg=CLAY).pack(side="left")
        self.count_lbl = L(left, "", 10, fg=MUTED)
        self.count_lbl.pack(anchor="w", pady=(4, 0))
        self.clear_btn = button(head, "Clear all", self.clear_all, False, small=True)
        self.clear_btn.pack(side="right", anchor="s")
        tk.Frame(self, bg=LINE, height=1).pack(fill="x")

        # ----- scrolling body
        body = tk.Frame(self, bg=PAPER)
        body.pack(fill="both", expand=True)
        self.cv = tk.Canvas(body, bg=PAPER, highlightthickness=0)
        sb = ttk.Scrollbar(body, orient="vertical", command=self.cv.yview)
        self.cv.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.cv.pack(side="left", fill="both", expand=True)
        self.list = tk.Frame(self.cv, bg=PAPER)
        self.win = self.cv.create_window((0, 0), window=self.list, anchor="nw")
        self.list.bind("<Configure>", lambda e: self.cv.configure(scrollregion=self.cv.bbox("all")))
        self.cv.bind("<Configure>", self.on_resize)
        self.bind("<MouseWheel>", lambda e: self.cv.yview_scroll(int(-e.delta / 120), "units"))
        self.bind("<Button-4>", lambda e: self.cv.yview_scroll(-3, "units"))
        self.bind("<Button-5>", lambda e: self.cv.yview_scroll(3, "units"))

        self.refresh()

    # ----- data
    def refresh(self):
        if not self.app.user:
            return
        by_id = {r["id"]: r for r in db.search_listings()}
        self.rows = [by_id[i] for i in db.favorite_ids(self.app.user["id"]) if i in by_id]
        n = len(self.rows)
        self.count_lbl.config(text=(f"{n} saved stay{'s' if n != 1 else ''}  \u00B7  "
                                    "tap one to see details and book") if n else
                              "Nothing saved yet")
        if n:
            self.clear_btn.pack(side="right", anchor="s")
        else:
            self.clear_btn.pack_forget()
        self.render()

    def on_resize(self, e):
        self.cv.itemconfig(self.win, width=e.width)
        cols = max(1, (e.width - 2 * self.SIDE + self.GAP) // (self.PHOTO_W + 22 + self.GAP))
        if cols != self.cols:
            self.render(cols)

    def render(self, cols=None):
        self.cols = cols or self.cols or 3
        y = self.cv.yview()[0]
        for w in self.list.winfo_children():
            w.destroy()
        if not self.rows:
            return self.build_empty()
        for i, r in enumerate(self.rows):
            card = self.build_card(r)
            card.grid(row=i // self.cols, column=i % self.cols, sticky="nsew",
                      padx=(self.SIDE if i % self.cols == 0 else self.GAP, 0), pady=(22, 0))
        tk.Frame(self.list, bg=PAPER, height=28).grid(row=len(self.rows) // self.cols + 1, column=0)
        self.cv.yview_moveto(y)

    # ----- empty state
    def build_empty(self):
        box = tk.Frame(self.list, bg=PAPER)
        box.pack(pady=(90, 0), padx=60, fill="x")
        ring = tk.Canvas(box, width=86, height=86, bg=PAPER, highlightthickness=0)
        ring.pack()
        ring.create_oval(2, 2, 84, 84, fill=CARD, outline=LINE, width=1)
        ring.create_text(43, 45, text="\u2661", fill=CLAY, font=("Arial", 30))
        L(box, "Nothing saved yet.", 18, "bold", family="Georgia").pack(pady=(20, 4))
        L(box, "Tap the heart on any stay you like and it will wait for you here.", 11, slant="italic",
          family="Georgia", fg=MUTED).pack()
        button(box, "Explore stays", self.explore).pack(pady=(22, 0))

    def explore(self):
        self.destroy()
        self.app.root.lift()
        self.app.goto("explore")

    # ----- one card
    def build_card(self, r):
        lid = r["id"]
        card = tk.Frame(self.list, bg=CARD, highlightbackground=LINE, highlightcolor=LINE,
                        highlightthickness=1, cursor="hand2")
        pad = tk.Frame(card, bg=CARD, padx=10, pady=10)
        pad.pack()
        img = tk.Label(pad, bg=CARD, bd=0)
        img.pack()
        self.app.photos.attach(img, r["image_seed"], self.PHOTO_W, self.PHOTO_H, 14, CARD, r["title"],
                               local=cover_file(r["id"]))
        tag = tk.Label(img, text=r["category"], bg="#FFFFFF", fg=INK, font=("Arial", 8, "bold"), padx=9, pady=3)
        tag.place(x=10, y=10)
        heart = tk.Button(img, text="\u2665", command=lambda i=lid: self.app.toggle_fav(i), relief="flat",
                          bd=0, bg="#FFFFFF", activebackground="#FFFFFF", fg=CLAY, activeforeground=CLAY_DEEP,
                          font=("Arial", 12), padx=7, pady=0, highlightthickness=0, cursor="hand2")
        heart.place(relx=1.0, x=-10, y=10, anchor="ne")

        body = tk.Frame(card, bg=CARD, padx=14)
        body.pack(fill="both", expand=True, pady=(0, 14))
        L(body, r["title"], 12, "bold", family="Georgia", anchor="w", justify="left",
          wraplength=self.PHOTO_W).pack(fill="x")
        L(body, "\u25CF " + r["location"], 9, fg=MUTED, anchor="w", justify="left",
          wraplength=self.PHOTO_W).pack(fill="x", pady=(3, 0))
        foot = tk.Frame(body, bg=CARD)
        foot.pack(side="bottom", fill="x")
        tk.Frame(body, bg=LINE, height=1).pack(side="bottom", fill="x", pady=(10, 8))
        L(foot, fmt_night(r["price_per_night"]), 12, "bold").pack(side="left")
        L(foot, " / night", 9, fg=MUTED).pack(side="left", pady=(2, 0))
        rating = f"\u2605 {r['rating']:.2f}" if r["rating"] else "New"
        rate_lbl = L(foot, rating, 9, "bold", fg=INK)
        rate_lbl.pack(side="right", pady=(2, 0))
        view = L(foot, "View stay \u2192", 9, "bold", fg=CARD)  # swaps in for the rating on hover
        view.pack_forget()

        def inside():
            w = card.winfo_containing(*card.winfo_pointerxy())
            while w is not None and w is not card:
                w = w.master
            return w is card

        def hover(on):
            card.config(highlightbackground=INK if on else LINE, highlightcolor=INK if on else LINE)
            if on:
                rate_lbl.pack_forget()
                view.config(fg=CLAY)
                view.pack(side="right")
            else:
                view.pack_forget()
                rate_lbl.pack(side="right", pady=(2, 0))

        def widgets(w):
            yield w
            for c in w.winfo_children():
                yield from widgets(c)

        for w in widgets(card):
            w.bind("<Enter>", lambda e: hover(True), add="+")
            w.bind("<Leave>", lambda e: self.after(15, lambda: hover(inside()) if card.winfo_exists() else None),
                   add="+")
            if w is not heart:
                w.bind("<Button-1>", lambda e, i=lid: self.app.open_stay(i), add="+")
        return card

    def clear_all(self):
        if not messagebox.askyesno("Wishlist", "Remove all saved stays from your wishlist?", parent=self):
            return
        db.clear_favorites(self.app.user["id"])
        self.app.reload_favs()
