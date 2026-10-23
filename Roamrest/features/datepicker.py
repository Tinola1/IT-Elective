"""datepicker.py - a calendar pop-up for choosing check-in / check-out, and the dates + guests block.

Instead of typing 2026-11-06 into tiny boxes, the guest clicks a date and picks it on a two-month calendar:
  * past dates and nights already booked by someone else are greyed out (and can't be selected)
  * after the check-in is picked the calendar moves on to the check-out, previewing the range as you hover
  * a stay can never run across a night that is already taken
Guests are changed with - / + buttons.

Used by app.py through:  datepicker.install(globals())
The dates still live in the same StringVars as before (ISO "YYYY-MM-DD"), so the rest of the app is unchanged.
"""
import calendar
import tkinter as tk
from datetime import date, datetime, timedelta

import database as db

DAY = timedelta(days=1)


class _UI:
    """Gives this module access to app.py's colours and helpers (L, fmt_day, ...)."""
    def __init__(self, ns):
        self.__dict__["_ns"] = ns

    def __getattr__(self, name):
        return self._ns[name]


def parse_day(text):
    try:
        return datetime.strptime(str(text).strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def booked_nights(listing_id):
    """Every night of this listing that is taken by a confirmed or pending booking (a set of dates)."""
    nights = set()
    with db.session() as c:
        db.expire_pending(c)
        rows = c.execute("SELECT check_in, check_out FROM bookings WHERE listing_id=? AND status IN"
                         " ('confirmed','pending')", (listing_id,)).fetchall()
    for r in rows:
        d, end = parse_day(r["check_in"]), parse_day(r["check_out"])
        while d and end and d < end:
            nights.add(d)
            d += DAY
    return nights


def make(ui):
    L, button, link = ui.L, ui.button, ui.link
    PAPER, PAPER2, CARD, INK, MUTED = ui.PAPER, ui.PAPER2, ui.CARD, ui.INK, ui.MUTED
    CLAY, LINE, PILL_BG = ui.CLAY, ui.LINE, ui.PILL_BG
    FAINT, PREVIEW = "#C9BEA6", "#F3EAD9"

    def friendly(text):
        d = parse_day(text)
        return f"{d:%b} {d.day}, {d.year}" if d else ""

    # ============================================================ the calendar pop-up
    class DatePopup(tk.Toplevel):
        current = None
        CELL, PAD, GAP = 38, 22, 30

        @classmethod
        def open(cls, anchor, owners, v_in, v_out, which="in", blocked=None, align="right", on_mode=None):
            """Show the calendar under `anchor`. If it is already open for these dates, just switch to `which`."""
            top = anchor.winfo_toplevel()
            if not getattr(top, "_datepopup_wired", False):  # close it on an outside click, Esc, scroll, window move
                top._datepopup_wired = True
                top.bind("<Button-1>", cls._outside, add="+")
                top.bind("<Escape>", lambda e: cls.close_current(), add="+")
                top.bind("<MouseWheel>", lambda e: cls.close_current(), add="+")
                top.bind("<Configure>", lambda e: cls.close_current() if e.widget is top else None, add="+")
            p = cls.current
            if p is not None and p.winfo_exists() and p.v_in is v_in and p.v_out is v_out:
                p.set_mode(which)
                return p
            cls.close_current()
            cls.current = cls(anchor, owners, v_in, v_out, which, blocked or set(), align, on_mode)
            return cls.current

        @classmethod
        def close_current(cls):
            p = cls.current
            cls.current = None
            if p is not None and p.winfo_exists():
                p.destroy()

        @classmethod
        def _outside(cls, e):
            p = cls.current
            if p is None or not p.winfo_exists():
                return
            w = str(e.widget)
            if any(w == str(o) or w.startswith(str(o) + ".") for o in p.owners):
                return  # a click on the field itself is handled by the field
            cls.close_current()

        def __init__(self, anchor, owners, v_in, v_out, which, blocked, align, on_mode):
            super().__init__(anchor.winfo_toplevel())
            self.overrideredirect(True)
            self.attributes("-topmost", True)
            self.configure(bg=LINE, padx=1, pady=1)
            self.anchor, self.owners, self.v_in, self.v_out = anchor, owners, v_in, v_out
            self.blocked, self.align, self.on_mode = blocked, align, on_mode
            self.today = date.today()
            self.which = which
            self.hover = None
            self.cells = []
            ci = parse_day(v_in.get())
            start = ci if (ci and ci >= self.today) else self.today
            self.base = date(start.year, start.month, 1)

            body = tk.Frame(self, bg=CARD)
            body.pack()
            head = tk.Frame(body, bg=CARD, padx=self.PAD + 2, pady=0)
            head.pack(fill="x", pady=(18, 0))
            self.heading_lbl = L(head, "", 15, "bold", family="Georgia", bg=CARD)
            self.heading_lbl.pack(anchor="w")
            self.sub = L(head, "", 9, fg=MUTED, bg=CARD)
            self.sub.pack(anchor="w", pady=(2, 0))
            width = self.PAD * 2 + self.CELL * 14 + self.GAP
            self.canvas = tk.Canvas(body, width=width, height=self.CELL * 6 + 82, bg=CARD, highlightthickness=0)
            self.canvas.pack(padx=0, pady=(6, 0))
            foot = tk.Frame(body, bg=CARD, padx=self.PAD + 2)
            foot.pack(fill="x", pady=(0, 16))
            self.count = L(foot, "", 10, "bold", bg=CARD)
            self.count.pack(side="left")
            button(foot, "Close", self.close, False, small=True).pack(side="right")
            link(foot, "Clear dates", self.clear, fg=MUTED, size=9, bold=True).pack(side="right", padx=14)
            self.canvas.bind("<Motion>", self.on_motion)
            self.canvas.bind("<Leave>", lambda e: self.set_hover(None))
            self.canvas.bind("<Button-1>", self.on_click)
            self.render()
            self.place_near()
            self.lift()
            if self.on_mode:
                self.on_mode(self.which)

        # ----- placing it next to the field
        def place_near(self):
            self.update_idletasks()
            w, h = self.winfo_reqwidth(), self.winfo_reqheight()
            a = self.anchor
            x = a.winfo_rootx() + (a.winfo_width() - w if self.align == "right" else 0)
            y = a.winfo_rooty() + a.winfo_height() + 6
            sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
            x = max(8, min(x, sw - w - 8))
            if y + h > sh - 48:  # not enough room below: open above the field instead
                y = max(8, a.winfo_rooty() - h - 6)
            self.geometry(f"+{x}+{y}")

        def close(self):
            DatePopup.close_current()
            if self.on_mode:
                self.on_mode(None)

        def destroy(self):
            if DatePopup.current is self:
                DatePopup.current = None
            super().destroy()

        # ----- the dates
        def ci(self):
            return parse_day(self.v_in.get())

        def co(self):
            return parse_day(self.v_out.get())

        def can_start(self, d):
            return d >= self.today and d not in self.blocked

        def can_end(self, d, ci):
            """Check-out `d` is fine when every night from check-in up to the day before is still free."""
            if ci is None or d <= ci:
                return False
            n = ci
            while n < d:
                if n in self.blocked:
                    return False
                n += DAY
            return True

        def set_mode(self, which):
            self.which = which
            if self.on_mode:
                self.on_mode(which)
            ci = self.ci()
            if ci and ci >= self.today:  # show the month of the date being edited
                self.base = date(ci.year, ci.month, 1)
            self.render()

        def clear(self):
            self.v_in.set("")
            self.v_out.set("")
            self.set_mode("in")

        def pick(self, d):
            ci, co = self.ci(), self.co()
            if self.which == "out" and ci and d > ci:  # choosing the check-out
                if self.can_end(d, ci):
                    self.v_out.set(d.isoformat())
                    self.close()
                return
            if not self.can_start(d):  # choosing (or re-choosing) the check-in
                return
            self.v_in.set(d.isoformat())
            if not (co and co > d and self.can_end(co, d)):
                self.v_out.set("")
            self.set_mode("out")

        # ----- mouse
        def day_at(self, x, y):
            for x0, y0, x1, y1, d in self.cells:
                if x0 <= x < x1 and y0 <= y < y1:
                    return d
            return None

        def selectable(self, d):
            ci = self.ci()
            if self.which == "out" and ci and d > ci:
                return self.can_end(d, ci)
            return self.can_start(d)

        def on_motion(self, e):
            d = self.day_at(e.x, e.y)
            if d is not None and not self.selectable(d):
                d = None
            self.canvas.config(cursor="hand2" if d else "")
            self.set_hover(d)

        def set_hover(self, d):
            if d != self.hover:
                self.hover = d
                self.render()

        def on_click(self, e):
            d = self.day_at(e.x, e.y)
            if d is not None:
                self.pick(d)

        def shift(self, months):
            y, m = self.base.year, self.base.month + months
            y, m = y + (m - 1) // 12, (m - 1) % 12 + 1
            new = date(y, m, 1)
            first = date(self.today.year, self.today.month, 1)
            last = first + timedelta(days=550)
            if first <= new <= last:
                self.base = new
                self.render()

        # ----- drawing
        def render(self):
            c, S = self.canvas, self.CELL
            c.delete("all")
            self.cells = []
            ci, co = self.ci(), self.co()
            prev_to = None
            if self.which == "out" and ci and self.hover and self.hover > ci and self.can_end(self.hover, ci) and not co:
                prev_to = self.hover
            elif self.which == "out" and ci and co and self.hover and self.hover > ci and self.can_end(self.hover, ci):
                prev_to = self.hover
            # header text
            self.heading_lbl.config(text="Select check-in date" if (self.which == "in" or not ci)
                                else "Select check-out date")
            if ci and co and co > ci:
                n = (co - ci).days
                self.sub.config(text=f"{friendly(ci.isoformat())}  \u2192  {friendly(co.isoformat())}")
                self.count.config(text=f"{n} night{'s' if n != 1 else ''}", fg=INK)
            else:
                self.sub.config(text="Greyed-out dates are in the past or already booked."
                                if self.blocked else "Past dates can't be selected.")
                self.count.config(text="Pick your check-out date" if (ci and self.which == "out")
                                  else "Pick your check-in date", fg=MUTED)
            first = date(self.today.year, self.today.month, 1)
            for idx in range(2):
                y, m = self.base.year, self.base.month + idx
                y, m = y + (m - 1) // 12, (m - 1) % 12 + 1
                ox = self.PAD + idx * (S * 7 + self.GAP)
                c.create_text(ox + S * 3.5, 24, text=f"{calendar.month_name[m]} {y}", font=("Georgia", 12, "bold"),
                              fill=INK)
                for k, name in enumerate(("Su", "Mo", "Tu", "We", "Th", "Fr", "Sa")):
                    c.create_text(ox + S * k + S / 2, 54, text=name, font=("Arial", 8, "bold"), fill=MUTED)
                for r, week in enumerate(calendar.Calendar(firstweekday=6).monthdayscalendar(y, m)):
                    for k, num in enumerate(week):
                        if not num:
                            continue
                        d = date(y, m, num)
                        x0, y0 = ox + S * k, 70 + S * r
                        self.cells.append((x0, y0, x0 + S, y0 + S, d))
                        self.draw_day(d, x0, y0, ci, co, prev_to)
            # month arrows
            can_prev = self.base > first
            can_next = self.base < first + timedelta(days=520)
            for tag, x, glyph, on in (("prev", self.PAD + 6, "\u2039", can_prev),
                                      ("next", self.PAD + S * 14 + self.GAP - 6, "\u203A", can_next)):
                c.create_text(x, 23, text=glyph, font=("Arial", 20, "bold"), fill=INK if on else FAINT, tags=tag)
                if on:
                    c.tag_bind(tag, "<Button-1>", lambda e, s=(-1 if tag == "prev" else 1): self.shift(s))
                    c.tag_bind(tag, "<Enter>", lambda e: c.config(cursor="hand2"))
                    c.tag_bind(tag, "<Leave>", lambda e: c.config(cursor=""))

        def draw_day(self, d, x0, y0, ci, co, prev_to):
            c, S = self.canvas, self.CELL
            cx, cy = x0 + S / 2, y0 + S / 2
            past = d < self.today
            taken = d in self.blocked and not past
            ok = self.selectable(d)
            band = None
            if ci and co and ci < d < co:
                band = PILL_BG
            elif prev_to and ci < d < prev_to:
                band = PREVIEW
            if ci and co and co > ci and d in (ci, co):
                c.create_rectangle(cx if d == ci else x0, y0 + 2, x0 + S if d == ci else cx, y0 + S - 2,
                                   fill=PILL_BG, outline="")
            elif prev_to and d == prev_to and not (d == ci):
                c.create_rectangle(x0, y0 + 2, cx, y0 + S - 2, fill=PREVIEW, outline="")
            if band:
                c.create_rectangle(x0, y0 + 2, x0 + S, y0 + S - 2, fill=band, outline="")
            chosen = d == ci or (co and d == co)
            if chosen:
                c.create_oval(cx - 17, cy - 17, cx + 17, cy + 17, fill=INK, outline="")
            elif self.hover == d and ok:
                c.create_oval(cx - 17, cy - 17, cx + 17, cy + 17, fill=CARD, outline=INK, width=1)
            if chosen:
                color = PAPER
            elif past or (not ok and not (ci and d <= ci)):
                color = FAINT
            else:
                color = INK
            c.create_text(cx, cy, text=str(d.day), font=("Arial", 10, "bold" if chosen else "normal"), fill=color)
            if taken:
                w = 9
                c.create_line(cx - w, cy + 1, cx + w, cy + 1, fill=FAINT)
            if d == self.today and not chosen:
                c.create_line(cx - 5, cy + 11, cx + 5, cy + 11, fill=CLAY, width=2)

    # ============================================================ the dates + guests block on the listing page
    def calendar_icon(parent, color, bg):
        cv = tk.Canvas(parent, width=18, height=18, bg=bg, highlightthickness=0)
        cv.create_rectangle(2, 4, 16, 16, outline=color, width=1.5)
        cv.create_line(2, 8, 16, 8, fill=color, width=1.5)
        cv.create_line(6, 2, 6, 6, fill=color, width=1.5)
        cv.create_line(12, 2, 12, 6, fill=color, width=1.5)
        return cv

    class DateGuestBlock(tk.Frame):
        """CHECK-IN | CHECKOUT (click to open the calendar) and GUESTS with - / + buttons."""

        def __init__(self, parent, v_in, v_out, v_guests, max_guests, blocked=None):
            super().__init__(parent, bg=INK, padx=1, pady=1)
            self.v_in, self.v_out, self.v_guests = v_in, v_out, v_guests
            self.max_guests, self.blocked = max_guests, blocked or set()
            self.active = None
            hair = tk.Frame(self, bg=LINE)  # the 1px gaps between the cells are this frame showing through
            hair.pack(fill="x")
            hair.columnconfigure(0, weight=1, uniform="dates")
            hair.columnconfigure(1, weight=1, uniform="dates")
            self.cells = {}
            for col, (key, label, var) in enumerate((("in", "CHECK-IN", v_in), ("out", "CHECKOUT", v_out))):
                cell = tk.Frame(hair, bg=CARD, padx=12, pady=9, cursor="hand2")
                cell.grid(row=0, column=col, sticky="nsew", padx=(0, 1) if col == 0 else 0, pady=(0, 1))
                lab = L(cell, label, 8, "bold", fg=MUTED, bg=CARD, cursor="hand2")
                lab.pack(anchor="w")
                row = tk.Frame(cell, bg=CARD, cursor="hand2")
                row.pack(fill="x", pady=(3, 0))
                val = L(row, "", 11, "bold", bg=CARD, cursor="hand2")
                val.pack(side="left")
                icon = calendar_icon(row, MUTED, CARD)
                icon.pack(side="right")
                icon.config(cursor="hand2")
                parts = [cell, lab, row, val, icon]
                self.cells[key] = {"parts": parts, "lab": lab, "val": val, "var": var}
                for w in parts:
                    w.bind("<Button-1>", lambda e, k=key: self.open(k))
                    w.bind("<Enter>", lambda e, k=key: self.tint(k, True))
                    w.bind("<Leave>", lambda e, k=key: self.tint(k, False))
                var.trace_add("write", lambda *a: self.refresh())

            g = tk.Frame(hair, bg=CARD, padx=12, pady=9)
            g.grid(row=1, column=0, columnspan=2, sticky="nsew")
            left = tk.Frame(g, bg=CARD)
            left.pack(side="left")
            L(left, "GUESTS", 8, "bold", fg=MUTED, bg=CARD).pack(anchor="w")
            self.g_val = L(left, "", 11, "bold", bg=CARD)
            self.g_val.pack(anchor="w", pady=(3, 0))
            self.g_note = L(left, f"Up to {max_guests} guests", 8, fg=MUTED, bg=CARD)
            self.g_note.pack(anchor="w")
            right = tk.Frame(g, bg=CARD)
            right.pack(side="right")
            opts = {"relief": "flat", "bd": 0, "font": ("Arial", 14, "bold"), "width": 2, "cursor": "hand2",
                    "bg": LINE, "activebackground": "#D3C7AA", "fg": INK, "disabledforeground": FAINT,
                    "highlightthickness": 0}
            self.minus = tk.Button(right, text="\u2212", command=lambda: self.step(-1), **opts)
            self.plus = tk.Button(right, text="+", command=lambda: self.step(1), **opts)
            self.minus.pack(side="left")
            self.plus.pack(side="left", padx=(8, 0))
            v_guests.trace_add("write", lambda *a: self.refresh())
            self.refresh()

        # ----- calendar
        def open(self, which):
            DatePopup.open(self, [self], self.v_in, self.v_out, which, blocked=self.blocked, align="right",
                           on_mode=self.set_active)

        def set_active(self, which):
            self.active = which
            for k in self.cells:
                self.tint(k, False)

        def tint(self, key, hovering):
            on = self.active == key
            bg = PAPER2 if (on or hovering) else CARD
            c = self.cells[key]
            for w in c["parts"]:
                w.config(bg=bg)
            c["lab"].config(fg=CLAY if on else MUTED)

        # ----- guests
        def count(self):
            try:
                return max(1, min(int(self.v_guests.get()), self.max_guests))
            except ValueError:
                return 1

        def step(self, d):
            self.v_guests.set(str(max(1, min(self.count() + d, self.max_guests))))

        def refresh(self):
            for key, c in self.cells.items():
                text = friendly(c["var"].get())
                c["val"].config(text=text or "Add date", fg=INK if text else MUTED)
            n = self.count()
            self.g_val.config(text=f"{n} guest{'s' if n != 1 else ''}")
            self.minus.config(state="normal" if n > 1 else "disabled")
            self.plus.config(state="normal" if n < self.max_guests else "disabled")

    return {"DatePopup": DatePopup, "DateGuestBlock": DateGuestBlock, "booked_nights": booked_nights}


def install(ns):
    """Called from app.py with globals(): adds the calendar pop-up and the new dates + guests block."""
    ns.update(make(_UI(ns)))