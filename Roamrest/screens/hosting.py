"""Hosting: the host's listings, reservations and the listing form, plus the photo manager."""

import tkinter as tk
from tkinter import filedialog
from tkinter import messagebox
from tkinter import ttk

import database as db
from helpers import L, _cur, button, clear, fmt_night, make_tree, money, selected_id, to_usd
from images import Image, delete_photo_file, photo_thumb, save_listing_photo
from navigation import Page
from theme import CARD, CLAY, INK, LINE, MUTED, PAPER, STATUS_STYLE


class HostWindow(Page):
    def __init__(self, app):
        super().__init__(app.root)
        self.app = app
        self.editing = None
        self.draft_photos = []  # photos picked for a listing that isn't saved yet: {"id", "filename", "caption"}
        self.draft_seq = 0
        self.bind("<Destroy>", lambda e: e.widget is self and self.drop_draft_files(), add="+")
        self.bookings = {}
        self.listings = {}
        self.title("Hosting")
        self.geometry("1200x760")
        self.minsize(1040, 700)
        self.configure(bg=PAPER)

        head = tk.Frame(self, bg=PAPER)
        head.pack(fill="x", padx=24, pady=(20, 0))
        L(head, "Hosting", 22, "bold", family="Georgia").pack(anchor="w")
        L(head, "Manage your listings and answer guest requests in one place.", 10, fg=MUTED).pack(
            anchor="w", pady=(2, 0))

        body = tk.Frame(self, bg=PAPER)
        body.pack(fill="both", expand=True, padx=24, pady=(14, 22))
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, minsize=380)
        body.rowconfigure(0, weight=1)

        # ---------- left: listings + reservations
        left = tk.Frame(body, bg=PAPER)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 20))
        left.columnconfigure(0, weight=1)
        left.rowconfigure(1, weight=2)
        left.rowconfigure(3, weight=3)

        top = tk.Frame(left, bg=PAPER)
        top.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        L(top, "My listings", 13, "bold", family="Georgia").pack(side="left")
        self.count_lbl = L(top, "", 9, fg=MUTED)
        self.count_lbl.pack(side="right")

        box, self.tree = self._table(left, [("title", "Title"), ("cat", "Category"), ("loc", "Location"),
                                            ("guests", "Guests"), ("price", "Price/night"),
                                            ("photos", "Photos"), ("status", "Status")],
                                     [150, 120, 110, 60, 100, 60, 80], 6)
        box.grid(row=1, column=0, sticky="nsew")
        self.tree.column("title", stretch=True)
        self.tree.column("loc", stretch=True)
        for cid in ("cat", "guests", "price", "photos", "status"):
            self.tree.column(cid, stretch=False)
        self.tree.column("guests", anchor="center")
        self.tree.heading("guests", anchor="center")
        self.tree.column("price", anchor="e")
        self.tree.heading("price", anchor="e")
        self.tree.column("photos", anchor="center")
        self.tree.heading("photos", anchor="center")
        self.tree.bind("<<TreeviewSelect>>", self.load_selected)
        self.tree.tag_configure("approved", foreground=STATUS_STYLE["confirmed"][1])
        self.tree.tag_configure("pending", foreground=STATUS_STYLE["pending"][1])
        self.tree.tag_configure("rejected", foreground=STATUS_STYLE["cancelled"][1])
        self.empty_listings = L(box, "No listings yet \u2014 fill in the form to add your first one.",
                                10, fg=MUTED, bg=CARD)

        mid = tk.Frame(left, bg=PAPER)
        mid.grid(row=2, column=0, sticky="ew", pady=(20, 8))
        L(mid, "Reservations at my places", 13, "bold", family="Georgia").pack(side="left")
        self.pending_lbl = tk.Label(mid, text="", font=("Arial", 9, "bold"), padx=10, pady=3)
        self.pending_lbl.pack(side="right")

        box2, self.btree = self._table(left, [("title", "Place"), ("guest", "Guest"), ("phone", "Phone"),
                                              ("in", "Check-in"), ("out", "Check-out"), ("total", "Total"),
                                              ("status", "Status")],
                                       [140, 110, 110, 90, 90, 100, 90], 6)
        box2.grid(row=3, column=0, sticky="nsew")
        for cid in ("title", "guest", "phone"):
            self.btree.column(cid, stretch=True)
        for cid in ("in", "out", "total", "status"):
            self.btree.column(cid, stretch=False)
        self.btree.column("total", anchor="e")
        self.btree.heading("total", anchor="e")
        self.btree.tag_configure("pending", foreground=STATUS_STYLE["pending"][1])
        self.btree.tag_configure("confirmed", foreground=STATUS_STYLE["confirmed"][1])
        self.btree.tag_configure("cancelled", foreground="#9A9080")
        self.empty_bookings = L(box2, "No reservations yet.", 10, fg=MUTED, bg=CARD)

        acts = tk.Frame(left, bg=PAPER)
        acts.grid(row=4, column=0, sticky="w", pady=(12, 0))
        button(acts, "Approve", lambda: self.decide("approve")).pack(side="left")
        button(acts, "Decline", lambda: self.decide("decline"), False).pack(side="left", padx=8)
        button(acts, "Cancel booking", lambda: self.decide("cancel"), False).pack(side="left")
        button(acts, "Message guest", self.message_guest, False).pack(side="left", padx=8)
        L(left, f"A request must be approved to be confirmed. It expires after "
                f"{db.PENDING_HOURS} hours without a reply.", 9, fg=MUTED, wraplength=700,
          justify="left").grid(row=5, column=0, sticky="w", pady=(8, 0))

        # ---------- right: listing form card
        form = tk.Frame(body, bg=CARD, highlightbackground=LINE, highlightthickness=1, padx=22, pady=18,
                        width=380)
        form.grid(row=0, column=1, sticky="nsew")
        form.grid_propagate(False)  # fixed width, so the tables on the left get all the spare room
        form.columnconfigure(0, weight=1)
        form.columnconfigure(1, weight=1)
        form.rowconfigure(13, weight=1)

        self.form_title = L(form, "New listing", 13, "bold", family="Georgia")
        self.form_title.grid(row=0, column=0, columnspan=2, sticky="w")
        self.form_sub = L(form, "", 9, fg=MUTED)
        self.form_sub.grid(row=1, column=0, columnspan=2, sticky="w", pady=(2, 6))

        self.v = {k: tk.StringVar() for k in ("title", "location", "price", "guests", "amenities")}
        self.v["category"] = tk.StringVar(value=db.CATEGORIES[0])
        font = ("Arial", 10)

        def label(text, row, col=0, span=2):
            lb = L(form, text, 9, "bold", fg=MUTED)
            lb.grid(row=row, column=col, columnspan=span, sticky="w", pady=(8, 3),
                    padx=(0, 6) if col == 0 and span == 1 else 0)
            return lb

        def entry(key, row, col=0, span=2):
            e = ttk.Entry(form, textvariable=self.v[key], font=font)
            e.grid(row=row, column=col, columnspan=span, sticky="ew",
                   padx=((0, 6) if col == 0 else (6, 0)) if span == 1 else 0)
            return e

        label("Title", 2)
        entry("title", 3)
        label("Category", 4)
        ttk.Combobox(form, textvariable=self.v["category"], values=db.CATEGORIES, state="readonly",
                     font=font).grid(row=5, column=0, columnspan=2, sticky="ew")
        label("Location", 6)
        entry("location", 7)
        self.price_lab = label("Price/night", 8, 0, 1)
        label("Max guests", 8, 1, 1)
        entry("price", 9, 0, 1)
        entry("guests", 9, 1, 1)
        label("Amenities", 10)
        entry("amenities", 11)
        label("Description", 12)
        self.desc = tk.Text(form, width=1, height=5, wrap="word", font=font, relief="flat", bg="white", fg=INK,
                            padx=8, pady=6, highlightthickness=1, highlightbackground=LINE,
                            highlightcolor=CLAY, insertbackground=INK)
        self.desc.grid(row=13, column=0, columnspan=2, sticky="nsew")

        bar = tk.Frame(form, bg=CARD)
        bar.grid(row=14, column=0, columnspan=2, sticky="w", pady=(16, 0))
        button(bar, "Save", self.save).pack(side="left")
        button(bar, "New", self.clear_form, False).pack(side="left", padx=8)
        button(bar, "Remove", self.remove, False).pack(side="left")
        button(bar, "Photos", self.open_photos, False).pack(side="left", padx=(8, 0))
        L(form, "Location: City, Country   \u00B7   Amenities: separate with commas\n"
                "Enter the price in your currency (see Languages & currency).\n"
                "New listings go live after admin approval.", 9, fg=MUTED, justify="left",
          wraplength=340).grid(row=15, column=0, columnspan=2, sticky="w", pady=(14, 0))

        self._mode()
        self.refresh()

    def _table(self, parent, columns, widths, height):
        """A table sitting inside a white bordered card. Returns (card, tree)."""
        box = tk.Frame(parent, bg=CARD, highlightbackground=LINE, highlightthickness=1)
        f, tree = make_tree(box, columns, widths, height)
        f.pack(fill="both", expand=True)
        return box, tree

    def _mode(self):
        """Form heading follows whether a listing is being edited or a new one is being written."""
        if self.editing:
            self.form_title.config(text="Edit listing")
            self.form_sub.config(text="Update the details, then press Save.")
        else:
            self.form_title.config(text="New listing")
            self.form_sub.config(text="Fill in the details, then press Save.")

    # ----- photos picked before the listing exists
    def stage_photo(self, filename):
        self.draft_seq += 1
        self.draft_photos.append({"id": self.draft_seq, "filename": filename, "caption": ""})
        return self.draft_seq

    def drop_draft_files(self):
        """Throw away the photo files of an unsaved listing."""
        for p in self.draft_photos:
            delete_photo_file(p["filename"])
        self.draft_photos = []

    def discard_draft(self, close_window=True):
        self.drop_draft_files()
        w = getattr(self, "photo_win", None)
        if close_window and w is not None and w.winfo_exists() and w.lid is None:
            w.destroy()

    def open_photos(self, lid=None):
        if lid is None:
            lid = self.editing  # None = a brand-new listing that hasn't been saved yet
        if lid is not None and lid not in self.listings:
            return messagebox.showinfo("Photos", "Select one of your listings first.", parent=self)
        if Image is None:
            return messagebox.showinfo("Photos", "Listing photos need Pillow.\nRun: pip install pillow",
                                       parent=self)
        w = getattr(self, "photo_win", None)
        if w is not None and w.winfo_exists():
            if w.lid == lid:
                w.deiconify()
                w.lift()
                w.focus_force()
                return
            w.destroy()
        self.photo_win = PhotosWindow(self, self.listings[lid] if lid is not None else None)

    def photos_changed(self, lid):
        """Called by the photo manager: update the count here and the pictures on the other pages."""
        n = len(db.photo_files(lid))
        if str(lid) in self.tree.get_children():
            self.tree.set(str(lid), "photos", n or "\u2014")
        self.app.run_search()
        self.app.refresh_trips()

    def on_currency(self):
        if self.draft_photos:  # keep the unsaved photos; only the typed price is in the old currency
            self.v["price"].set("")
        else:
            self.clear_form()
        self.refresh()

    def refresh(self):
        self.price_lab.config(text=f"Price/night ({_cur()[0]})")
        clear(self.tree)
        self.listings = {r["id"]: r for r in db.host_listings(self.app.user["id"])}
        counts = db.photo_counts(self.app.user["id"])
        for r in self.listings.values():
            self.tree.insert("", "end", iid=str(r["id"]), tags=(r["status"],), values=(
                r["title"], r["category"], r["location"], r["max_guests"], fmt_night(r["price_per_night"]),
                counts.get(r["id"]) or "\u2014", r["status"].capitalize()))
        n = len(self.listings)
        self.count_lbl.config(text=f"{n} listing{'s' if n != 1 else ''}")
        self._toggle_empty(self.empty_listings, not self.listings)
        clear(self.btree)
        self.bookings = {}
        waiting = 0
        for b in db.host_bookings(self.app.user["id"]):
            self.bookings[b["id"]] = b
            waiting += b["status"] == "pending"
            self.btree.insert("", "end", iid=str(b["id"]), tags=(b["status"],), values=(
                b["title"], b["guest_name"], b["guest_phone"] or "\u2014", b["check_in"],
                b["check_out"], money(b["total_price"]), b["status"].capitalize()))
        self._toggle_empty(self.empty_bookings, not self.bookings)
        if waiting:
            _, fg, bg = STATUS_STYLE["pending"]
            self.pending_lbl.config(
                text=f"\u25CF {waiting} request{'s' if waiting != 1 else ''} waiting for your approval",
                fg=fg, bg=bg)
        else:
            self.pending_lbl.config(text="No requests waiting", fg=MUTED, bg=PAPER)

    @staticmethod
    def _toggle_empty(label, show):
        if show:
            label.place(relx=0.5, rely=0.5, anchor="center")
        else:
            label.place_forget()

    def decide(self, action):
        bid = selected_id(self.btree)
        if bid is None:
            return messagebox.showinfo("Reservations", "Select a reservation first.", parent=self)
        if action == "decline" and not messagebox.askyesno(
                "Decline request", "Decline this request? The guest is refunded in full.", parent=self):
            return
        if action == "cancel" and not messagebox.askyesno(
                "Cancel booking", "Cancel this confirmed booking? The guest is refunded in full.", parent=self):
            return
        try:
            db.host_decide(bid, self.app.user["id"], action)
        except db.AppError as e:
            return messagebox.showerror("Reservations", str(e), parent=self)
        self.refresh()
        self.app.run_search()
        self.app.refresh_trips()
        self.app.refresh_nav()

    def message_guest(self):
        bid = selected_id(self.btree)
        if bid is None:
            return messagebox.showinfo("Messages", "Select a reservation first.", parent=self)
        b = self.bookings[bid]
        self.app.open_messages(b["listing_id"], b["guest_id"])

    def clear_form(self, keep_photo_window=False):
        self.editing = None
        self.discard_draft(close_window=not keep_photo_window)
        for k, var in self.v.items():
            var.set(db.CATEGORIES[0] if k == "category" else "")
        self.desc.delete("1.0", "end")
        self.tree.selection_remove(self.tree.selection())
        self._mode()

    def load_selected(self, _e=None):
        lid = selected_id(self.tree)
        if lid is None:
            return
        r = self.listings[lid]
        self.editing = lid
        if self.draft_photos:  # the form is being replaced, so the unsaved photos go too
            self.discard_draft()
        self.v["title"].set(r["title"])
        self.v["category"].set(r["category"])
        self.v["location"].set(r["location"])
        self.v["price"].set(f"{round(r['price_per_night'] * _cur()[1], 2):g}")
        self.v["guests"].set(r["max_guests"])
        self.v["amenities"].set(r["amenities"] or "")
        self.desc.delete("1.0", "end")
        self.desc.insert("1.0", r["description"] or "")
        self._mode()

    def save(self, parent=None, from_photos=False):
        """Saves the form. Returns True on success. `parent` is the window error/info boxes belong to
        (the Photos page passes itself, because this window is hidden while it is open)."""
        parent = parent or self
        uid = self.app.user["id"]
        args = (self.v["title"].get(), self.v["category"].get(), self.v["location"].get(),
                to_usd(self.v["price"].get()), self.v["guests"].get(), self.desc.get("1.0", "end"),
                self.v["amenities"].get())
        new_id = None
        try:
            if self.editing:
                db.update_listing(self.editing, uid, *args)
                note = "Listing updated."
            else:
                new_id = db.add_listing(uid, *args)
                note = ("Listing submitted. It shows under 'My listings' as pending, and appears on "
                        "the main page once an admin approves it.")
        except db.AppError as e:
            messagebox.showerror("Listing", str(e), parent=parent)
            return False
        except Exception as e:  # anything unexpected is shown instead of silently failing
            import traceback
            traceback.print_exc()
            messagebox.showerror("Listing", f"Couldn't save the listing:\n{e}", parent=parent)
            return False
        attached = 0
        if new_id and self.draft_photos:  # attach the photos picked before the listing existed
            for p in self.draft_photos:
                try:
                    db.add_listing_photo(new_id, uid, p["filename"], p["caption"])
                    attached += 1
                except db.AppError:
                    delete_photo_file(p["filename"])
            self.draft_photos = []  # the files now belong to the listing, so don't delete them
            note += f"\n\n{attached} photo{'s' if attached != 1 else ''} added."
        self.clear_form(keep_photo_window=True)
        self.refresh()
        self.app.run_search()
        if new_id:
            self.tree.selection_set(str(new_id))
        if new_id and not attached and not from_photos:
            if messagebox.askyesno("Listing", note + "\n\nAdd photos now?", parent=parent):
                self.open_photos(new_id)
        else:
            messagebox.showinfo("Listing", note, parent=parent)
        return True

    def remove(self):
        if not self.editing:
            return messagebox.showinfo("Remove", "Select a listing first.", parent=self)
        if not messagebox.askyesno("Remove", "Remove this listing?", parent=self):
            return
        try:
            names = db.delete_listing(self.editing, self.app.user["id"])
        except db.AppError as e:
            return messagebox.showerror("Remove", str(e), parent=self)
        for name in names:
            delete_photo_file(name)
        self.clear_form()
        self.refresh()
        self.app.run_search()


class PhotosWindow(Page):
    """Add, replace, caption, reorder and delete the photos of one listing. The first photo is the cover."""
    TW, TH = 176, 124  # thumbnail size

    def __init__(self, host, listing=None):
        """listing=None means the listing isn't saved yet: photos are kept in `host.draft_photos` and
        attached when the listing is saved."""
        super().__init__(host)
        self.host, self.listing = host, listing
        self.draft = listing is None
        self.uid = host.app.user["id"]
        self.lid = None if self.draft else listing["id"]
        self.photos, self.sel, self.cards, self.imgs = [], None, {}, []
        self.cols = 0
        name = host.v["title"].get().strip() if self.draft else listing["title"]
        name = name or "New listing"
        self.title("Photos \u2013 " + name)
        self.geometry("1040x700")
        self.minsize(900, 580)
        self.configure(bg=PAPER)

        head = tk.Frame(self, bg=PAPER)
        head.pack(fill="x", padx=24, pady=(20, 0))
        txt = tk.Frame(head, bg=PAPER)
        txt.pack(side="left")
        L(txt, "Photos", 22, "bold", family="Georgia").pack(anchor="w")
        sub = (f"{name}  \u00B7  Not saved yet \u2013 your photos are attached when you save the listing."
               if self.draft else
               f"{name}  \u00B7  The first photo is the cover guests see on search cards.")
        L(txt, sub, 10, fg=MUTED).pack(anchor="w", pady=(2, 0))
        button(head, "Save photos", self.save_photos).pack(side="right", anchor="s")

        body = tk.Frame(self, bg=PAPER)
        body.pack(fill="both", expand=True, padx=24, pady=(14, 22))
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, minsize=330)
        body.rowconfigure(0, weight=1)

        # ---------- left: toolbar + thumbnail grid
        left = tk.Frame(body, bg=PAPER)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 20))
        left.columnconfigure(0, weight=1)
        left.rowconfigure(1, weight=1)
        bar = tk.Frame(left, bg=PAPER)
        bar.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        button(bar, "+ Add photos", self.add_photos).pack(side="left")
        self.count_lbl = L(bar, "", 9, fg=MUTED)
        self.count_lbl.pack(side="right")

        box = tk.Frame(left, bg=CARD, highlightbackground=LINE, highlightthickness=1)
        box.grid(row=1, column=0, sticky="nsew")
        self.canvas = tk.Canvas(box, bg=CARD, highlightthickness=0)
        self.sb = ttk.Scrollbar(box, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.on_scroll)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.inner = tk.Frame(self.canvas, bg=CARD)
        self.win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", self.on_resize)
        self.bind("<MouseWheel>", lambda e: self.canvas.yview_scroll(int(-e.delta / 120), "units"))

        # ---------- right: the selected photo
        panel = tk.Frame(body, bg=CARD, highlightbackground=LINE, highlightthickness=1, padx=20, pady=18,
                         width=330)
        panel.grid(row=0, column=1, sticky="nsew")
        panel.grid_propagate(False)
        panel.columnconfigure(0, weight=1)
        panel.columnconfigure(1, weight=1)
        L(panel, "Selected photo", 13, "bold", family="Georgia").grid(row=0, column=0, columnspan=2, sticky="w")
        self.pos_lbl = L(panel, "", 9, fg=MUTED)
        self.pos_lbl.grid(row=1, column=0, columnspan=2, sticky="w", pady=(2, 10))
        self.preview = tk.Label(panel, bg=CARD, bd=0, fg=MUTED, font=("Arial", 10), width=34, height=10)
        self.preview.grid(row=2, column=0, columnspan=2)
        L(panel, "Caption", 9, "bold", fg=MUTED).grid(row=3, column=0, columnspan=2, sticky="w", pady=(14, 3))
        self.cap = tk.StringVar()
        self.cap_entry = ttk.Entry(panel, textvariable=self.cap, font=("Arial", 10))
        self.cap_entry.grid(row=4, column=0, columnspan=2, sticky="ew")
        self.cap_entry.bind("<Return>", lambda e: self.save_caption())
        self.cap_btn = button(panel, "Save caption", self.save_caption, small=True)
        self.cap_btn.grid(row=5, column=0, columnspan=2, sticky="w", pady=(8, 0))

        tk.Frame(panel, bg=LINE, height=1).grid(row=6, column=0, columnspan=2, sticky="ew", pady=14)
        self.actions = [
            button(panel, "\u25C0  Move earlier", lambda: self.move(-1), False, small=True),
            button(panel, "Move later  \u25B6", lambda: self.move(1), False, small=True),
            button(panel, "Set as cover", self.make_cover, False, small=True),
            button(panel, "Replace photo", self.replace_photo, False, small=True),
            button(panel, "Delete photo", self.delete_photo, False, small=True)]
        self.actions[0].grid(row=7, column=0, sticky="ew", padx=(0, 4))
        self.actions[1].grid(row=7, column=1, sticky="ew", padx=(4, 0))
        self.actions[2].grid(row=8, column=0, sticky="ew", padx=(0, 4), pady=(8, 0))
        self.actions[3].grid(row=8, column=1, sticky="ew", padx=(4, 0), pady=(8, 0))
        self.actions[4].grid(row=9, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        self.actions[4].config(fg="#9B2C2C")
        for b in self.actions + [self.cap_btn]:
            b.config(disabledforeground="#B5AA92")

        self.reload()

    # ----- layout
    def on_scroll(self, lo, hi):  # only show the scrollbar when the photos don't all fit
        if float(lo) <= 0 and float(hi) >= 1:
            self.sb.pack_forget()
        elif not self.sb.winfo_ismapped():
            self.sb.pack(side="right", fill="y")
        self.sb.set(lo, hi)

    def on_resize(self, e):
        self.canvas.itemconfig(self.win, width=e.width)
        cols = max(2, e.width // (self.TW + 30))
        if cols != self.cols:
            self.cols = cols
            self.render()

    # ----- data + drawing
    def reload(self, select=None):
        self.photos = list(self.host.draft_photos) if self.draft else db.listing_photos(self.lid)
        ids = [p["id"] for p in self.photos]
        if select in ids:
            self.sel = select
        elif self.sel not in ids:
            self.sel = None
        y = self.canvas.yview()[0]
        self.render()
        self.canvas.update_idletasks()
        self.canvas.yview_moveto(y)

    def render(self):
        if not self.cols:
            return
        for w in self.inner.winfo_children():
            w.destroy()
        self.cards, self.imgs = {}, []
        n = len(self.photos)
        self.count_lbl.config(text=f"{n} of {db.MAX_PHOTOS} photos")
        if not self.photos:
            L(self.inner, "No photos yet", 14, "bold", family="Georgia", bg=CARD).pack(pady=(90, 4), padx=60)
            L(self.inner, "Add pictures of your place. The first one becomes the cover.", 10, fg=MUTED,
              bg=CARD, wraplength=360, justify="center").pack(padx=60)
            button(self.inner, "+ Add photos", self.add_photos).pack(pady=16)
        for i, p in enumerate(self.photos):
            self.build_thumb(p, i).grid(row=i // self.cols, column=i % self.cols, padx=8, pady=8, sticky="n")
        self.paint_selection()
        self.show_selected()

    def build_thumb(self, p, i):
        card = tk.Frame(self.inner, bg=CARD, highlightthickness=2, highlightbackground=CARD, padx=4, pady=4,
                        cursor="hand2")
        ph = photo_thumb(p["filename"], self.TW, self.TH, 10, CARD)
        self.imgs.append(ph)
        img = tk.Label(card, image=ph, bg=CARD, bd=0)
        img.pack()
        widgets = [card, img]
        if i == 0:
            tag = tk.Label(img, text="COVER", bg=CLAY, fg="white", font=("Arial", 8, "bold"), padx=7, pady=2)
            tag.place(x=8, y=8)
            widgets.append(tag)
        cap = p["caption"] or "No caption"
        if len(cap) > 28:
            cap = cap[:27] + "\u2026"
        lb = L(card, cap, 9, fg=INK if p["caption"] else MUTED, bg=CARD, anchor="w", width=24)
        lb.pack(anchor="w", pady=(4, 0))
        widgets.append(lb)
        for w in widgets:
            w.bind("<Button-1>", lambda e, pid=p["id"]: self.select(pid))
        self.cards[p["id"]] = card
        return card

    def select(self, pid):
        self.sel = pid
        self.paint_selection()
        self.show_selected()

    def paint_selection(self):
        for pid, card in self.cards.items():
            card.config(highlightbackground=CLAY if pid == self.sel else CARD)

    def current(self):
        for i, p in enumerate(self.photos):
            if p["id"] == self.sel:
                return i, p
        return None, None

    def show_selected(self):
        i, p = self.current()
        on = p is not None
        for b in self.actions + [self.cap_btn]:
            b.config(state="normal" if on else "disabled")
        self.cap_entry.config(state="normal" if on else "disabled")
        if not on:
            self.preview.config(image="", text="Click a photo\nto edit it", width=34, height=10)
            self.preview.image = None
            self.pos_lbl.config(text="Nothing selected")
            self.cap.set("")
            return
        ph = photo_thumb(p["filename"], 290, 200, 12, CARD)
        self.preview.config(image=ph, text="", width=290, height=200)
        self.preview.image = ph
        self.pos_lbl.config(text=f"Photo {i + 1} of {len(self.photos)}" + ("  \u00B7  Cover" if i == 0 else ""))
        self.cap.set(p["caption"] or "")
        self.actions[0].config(state="normal" if i > 0 else "disabled")
        self.actions[1].config(state="normal" if i < len(self.photos) - 1 else "disabled")
        self.actions[2].config(state="normal" if i > 0 else "disabled")

    # ----- actions
    def changed(self, select=None):
        self.reload(select)
        if not self.draft:
            self.host.photos_changed(self.lid)

    def _draft_item(self, pid):
        return next((p for p in self.host.draft_photos if p["id"] == pid), None)

    def save_photos(self):
        """Keeps the photos and goes back to Hosting. For a listing that isn't saved yet, the photos
        stay in the form and are attached when the listing itself is saved."""
        n = len(self.photos)
        if self.draft and n:
            messagebox.showinfo("Photos", f"{n} photo{'s' if n != 1 else ''} saved. "
                                          "They'll be attached when you save the listing.", parent=self)
        self.destroy()

    def add_photos(self):
        room = db.MAX_PHOTOS - len(self.photos)
        if room <= 0:
            return messagebox.showinfo("Photos", f"A listing can have up to {db.MAX_PHOTOS} photos. "
                                                 "Delete one to add another.", parent=self)
        paths = list(filedialog.askopenfilenames(
            parent=self, title="Choose photos (you can pick several)",
            filetypes=[("Pictures", "*.png *.jpg *.jpeg *.webp *.bmp *.gif"), ("All files", "*.*")]))
        if not paths:
            return
        skipped = max(0, len(paths) - room)
        added, last, problems = 0, None, []
        self.config(cursor="watch")
        self.update_idletasks()
        for path in paths[:room]:
            name = None
            try:
                name = save_listing_photo(path, "draft" if self.draft else self.lid)
                last = self.host.stage_photo(name) if self.draft else db.add_listing_photo(self.lid, self.uid, name)
                added += 1
            except db.AppError as e:
                if name:
                    delete_photo_file(name)
                problems.append(str(e))
        self.config(cursor="")
        if added:
            self.changed(last)
        if skipped:
            problems.append(f"{skipped} photo{'s' if skipped != 1 else ''} skipped \u2013 "
                            f"a listing can have up to {db.MAX_PHOTOS}.")
        if problems:
            messagebox.showwarning("Photos", "\n".join(problems), parent=self)

    def replace_photo(self):
        _, p = self.current()
        if p is None:
            return
        path = filedialog.askopenfilename(
            parent=self, title="Choose the new picture",
            filetypes=[("Pictures", "*.png *.jpg *.jpeg *.webp *.bmp *.gif"), ("All files", "*.*")])
        if not path:
            return
        name = None
        try:
            name = save_listing_photo(path, "draft" if self.draft else self.lid)
            if self.draft:
                item = self._draft_item(p["id"])
                old, item["filename"] = item["filename"], name
            else:
                old = db.update_listing_photo(p["id"], self.uid, filename=name)
        except db.AppError as e:
            if name:
                delete_photo_file(name)
            return messagebox.showerror("Photos", str(e), parent=self)
        if old:
            delete_photo_file(old)
        self.changed(p["id"])

    def save_caption(self):
        _, p = self.current()
        if p is None:
            return
        try:
            if self.draft:
                self._draft_item(p["id"])["caption"] = self.cap.get().strip()[:120]
            else:
                db.update_listing_photo(p["id"], self.uid, caption=self.cap.get())
        except db.AppError as e:
            return messagebox.showerror("Photos", str(e), parent=self)
        self.changed(p["id"])

    def move(self, step):
        _, p = self.current()
        if p is None:
            return
        try:
            if self.draft:
                lst = self.host.draft_photos
                i = lst.index(self._draft_item(p["id"]))
                j = i + (-1 if step < 0 else 1)
                if 0 <= j < len(lst):
                    lst[i], lst[j] = lst[j], lst[i]
            else:
                db.move_listing_photo(p["id"], self.uid, step)
        except db.AppError as e:
            return messagebox.showerror("Photos", str(e), parent=self)
        self.changed(p["id"])

    def make_cover(self):
        _, p = self.current()
        if p is None:
            return
        try:
            if self.draft:
                lst = self.host.draft_photos
                lst.insert(0, lst.pop(lst.index(self._draft_item(p["id"]))))
            else:
                db.set_cover_photo(p["id"], self.uid)
        except db.AppError as e:
            return messagebox.showerror("Photos", str(e), parent=self)
        self.changed(p["id"])

    def delete_photo(self):
        _, p = self.current()
        if p is None:
            return
        if not messagebox.askyesno("Delete photo", "Delete this photo? This can't be undone.", parent=self):
            return
        try:
            if self.draft:
                item = self._draft_item(p["id"])
                self.host.draft_photos.remove(item)
                name = item["filename"]
            else:
                name = db.delete_listing_photo(p["id"], self.uid)
        except db.AppError as e:
            return messagebox.showerror("Photos", str(e), parent=self)
        delete_photo_file(name)
        self.sel = None
        self.changed()
