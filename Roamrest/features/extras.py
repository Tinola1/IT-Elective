"""extras.py - guest reviews + the admin dashboard for RoamRest.

Used by app.py through:  extras.install(globals())  and  extras.init()
"""
import csv
import os
import re
import secrets
import sqlite3
import tkinter as tk
from datetime import date, datetime
from tkinter import filedialog, messagebox, ttk

import database as db

AppError = db.AppError
PLATFORM_FEE = 0.03  # the flat 3% host fee promised on the site
PALETTE = ["#B44A1E", "#20362A", "#E9A170", "#5B6F8A", "#C9852B", "#7A5C86", "#2F8F9D", "#5E8B4F"]
STAR_WORDS = ["Poor", "Fair", "Good", "Very good", "Excellent"]


def stars_text(n):
    n = int(n or 0)
    return "\u2605" * n + "\u2606" * (5 - n)


# =========================================================== database part
def init():
    """Create the reviews table, remember each listing's original demo rating, add demo past stays."""
    with db.session() as c:
        c.executescript("""
            CREATE TABLE IF NOT EXISTS reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                booking_id INTEGER NOT NULL UNIQUE REFERENCES bookings(id),
                listing_id INTEGER NOT NULL REFERENCES listings(id),
                guest_id INTEGER NOT NULL REFERENCES users(id),
                rating INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
                comment TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                hidden INTEGER NOT NULL DEFAULT 0
            );""")
        have = {r["name"] for r in c.execute("PRAGMA table_info(listings)")}
        if "base_count" not in have:  # first run: keep the demo ratings as the starting point
            c.execute("ALTER TABLE listings ADD COLUMN base_rating REAL")
            c.execute("ALTER TABLE listings ADD COLUMN base_count INTEGER NOT NULL DEFAULT 0")
            c.execute("UPDATE listings SET base_rating=rating, base_count=review_count")
            _demo_past_stays(c)  # first run only, so stays the admin deletes don't come back


def _demo_past_stays(c):
    guest = c.execute("SELECT id FROM users WHERE email=?", (db.DEMO_GUEST_EMAIL,)).fetchone()
    if guest is None:
        return
    today = date.today()
    if c.execute("SELECT 1 FROM bookings WHERE guest_id=? AND check_out < ?",
                 (guest["id"], today.isoformat())).fetchone():
        return
    places = c.execute("SELECT id, price_per_night FROM listings WHERE active=1 AND status='approved'"
                       " AND host_id != ? ORDER BY id LIMIT 2", (guest["id"],)).fetchall()
    for i, p in enumerate(places):
        ci = date.fromordinal(today.toordinal() - 14 - i * 9)
        co = date.fromordinal(ci.toordinal() + 3)
        made = datetime.fromordinal(ci.toordinal() - 6).isoformat(timespec="seconds")
        c.execute("INSERT INTO bookings (listing_id,guest_id,check_in,check_out,guests,total_price,status,created_at)"
                  " VALUES (?,?,?,?,?,?, 'confirmed', ?)",
                  (p["id"], guest["id"], ci.isoformat(), co.isoformat(), 2, 3 * p["price_per_night"], made))


def _recompute(c, listing_id):
    """Listing rating = demo rating blended with the visible real reviews."""
    row = c.execute("SELECT base_rating, base_count FROM listings WHERE id=?", (listing_id,)).fetchone()
    base_r, base_n = (row["base_rating"] or 0.0), (row["base_count"] or 0)
    s = c.execute("SELECT COALESCE(SUM(rating),0), COUNT(*) FROM reviews WHERE listing_id=? AND hidden=0",
                  (listing_id,)).fetchone()
    n = base_n + s[1]
    rating = round((base_r * base_n + s[0]) / n, 2) if n else None
    c.execute("UPDATE listings SET rating=?, review_count=? WHERE id=?", (rating, n, listing_id))


def _check_review(rating, comment):
    try:
        rating = int(rating)
    except (TypeError, ValueError):
        rating = 0
    if not 1 <= rating <= 5:
        raise AppError("Choose a star rating from 1 to 5.")
    comment = (comment or "").strip()
    if len(comment) > 1000:
        raise AppError("Comments can be up to 1000 characters.")
    return rating, comment


def add_review(user_id, booking_id, rating, comment):
    rating, comment = _check_review(rating, comment)
    with db.session() as c:
        b = c.execute("SELECT * FROM bookings WHERE id=? AND guest_id=?", (booking_id, user_id)).fetchone()
        if b is None:
            raise AppError("Trip not found.")
        if b["status"] != "confirmed":
            raise AppError("Only confirmed trips can be reviewed.")
        if b["check_out"] > date.today().isoformat():
            raise AppError(f"You can review this stay after check-out ({b['check_out']}).")
        if c.execute("SELECT 1 FROM reviews WHERE booking_id=?", (booking_id,)).fetchone():
            raise AppError("You already reviewed this stay. Edit your review instead.")
        c.execute("INSERT INTO reviews (booking_id, listing_id, guest_id, rating, comment, created_at)"
                  " VALUES (?,?,?,?,?,?)",
                  (booking_id, b["listing_id"], user_id, rating, comment, db._now()))
        _recompute(c, b["listing_id"])


def update_review(user_id, review_id, rating, comment):
    rating, comment = _check_review(rating, comment)
    with db.session() as c:
        r = c.execute("SELECT * FROM reviews WHERE id=? AND guest_id=?", (review_id, user_id)).fetchone()
        if r is None:
            raise AppError("Review not found.")
        c.execute("UPDATE reviews SET rating=?, comment=? WHERE id=?", (rating, comment, review_id))
        _recompute(c, r["listing_id"])


def delete_review(review_id, user_id=None):
    """user_id=None means an admin deleting it."""
    with db.session() as c:
        sql, params = "SELECT * FROM reviews WHERE id=?", [review_id]
        if user_id is not None:
            sql += " AND guest_id=?"
            params.append(user_id)
        r = c.execute(sql, params).fetchone()
        if r is None:
            raise AppError("Review not found.")
        c.execute("DELETE FROM reviews WHERE id=?", (review_id,))
        _recompute(c, r["listing_id"])


def set_review_hidden(review_id, hidden):
    with db.session() as c:
        r = c.execute("SELECT * FROM reviews WHERE id=?", (review_id,)).fetchone()
        if r is None:
            raise AppError("Review not found.")
        c.execute("UPDATE reviews SET hidden=? WHERE id=?", (int(hidden), review_id))
        _recompute(c, r["listing_id"])


def review_for_booking(booking_id):
    with db.session() as c:
        return c.execute("SELECT * FROM reviews WHERE booking_id=?", (booking_id,)).fetchone()


def listing_reviews(listing_id):
    with db.session() as c:
        return c.execute("SELECT r.*, u.name AS guest_name FROM reviews r JOIN users u ON u.id=r.guest_id"
                         " WHERE r.listing_id=? AND r.hidden=0 ORDER BY r.id DESC", (listing_id,)).fetchall()


def all_reviews():
    with db.session() as c:
        return c.execute("SELECT r.*, u.name AS guest_name, l.title FROM reviews r"
                         " JOIN users u ON u.id=r.guest_id JOIN listings l ON l.id=r.listing_id"
                         " ORDER BY r.id DESC").fetchall()


# ---- admin numbers
def overview():
    today = date.today().isoformat()
    with db.session() as c:
        def one(sql, *p):
            return c.execute(sql, p).fetchone()[0]
        cancelled_rows = c.execute("SELECT * FROM bookings WHERE status='cancelled'").fetchall()
        out = {
            "guests": one("SELECT COUNT(*) FROM users WHERE role='guest'"),
            "hosts": one("SELECT COUNT(*) FROM users WHERE role='host'"),
            "inactive": one("SELECT COUNT(*) FROM users WHERE active=0"),
            "live": one("SELECT COUNT(*) FROM listings WHERE active=1 AND status='approved'"),
            "pending_listings": one("SELECT COUNT(*) FROM listings WHERE active=1 AND status='pending'"),
            "confirmed": one("SELECT COUNT(*) FROM bookings WHERE status='confirmed'"),
            "pending": one("SELECT COUNT(*) FROM bookings WHERE status='pending'"),
            "cancelled": one("SELECT COUNT(*) FROM bookings WHERE status='cancelled'"),
            "revenue": one("SELECT COALESCE(SUM(total_price),0) FROM bookings WHERE status='confirmed'"),
            "upcoming": one("SELECT COUNT(*) FROM bookings WHERE status='confirmed' AND check_in >= ?", today),
            "reviews": one("SELECT COUNT(*) FROM reviews WHERE hidden=0"),
            "hidden_reviews": one("SELECT COUNT(*) FROM reviews WHERE hidden=1"),
            "avg_rating": one("SELECT AVG(rating) FROM listings WHERE active=1 AND status='approved'"
                              " AND rating IS NOT NULL"),
        }
    # requests that were declined, withdrawn or expired were never charged, so they add nothing here
    out["refunds"] = round(sum(db.refunded_amount(b) for b in cancelled_rows), 2)
    return out


def counts(sql):
    with db.session() as c:
        return [(r[0], r[1]) for r in c.execute(sql).fetchall()]


def monthly_bookings(months=6):
    today = date.today()
    y, m, keys = today.year, today.month, []
    for _ in range(months):
        keys.append((y, m))
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    keys.reverse()
    with db.session() as c:
        rows = c.execute("SELECT substr(COALESCE(NULLIF(created_at,''), check_in), 1, 7) AS ym,"
                         " COUNT(*) AS n, COALESCE(SUM(total_price),0) AS v FROM bookings"
                         " WHERE status!='cancelled' GROUP BY ym").fetchall()
    data = {r["ym"]: (r["n"], r["v"]) for r in rows}
    return [(datetime(y, m, 1).strftime("%b"), *data.get(f"{y:04d}-{m:02d}", (0, 0))) for y, m in keys]


def top_listings(n=5):
    with db.session() as c:
        return c.execute("SELECT l.title, COUNT(b.id) AS n, COALESCE(SUM(b.total_price),0) AS rev"
                         " FROM listings l JOIN bookings b ON b.listing_id=l.id AND b.status='confirmed'"
                         " GROUP BY l.id ORDER BY rev DESC LIMIT ?", (n,)).fetchall()


def admin_users():
    with db.session() as c:
        return c.execute("SELECT u.*, (SELECT COUNT(*) FROM bookings b WHERE b.guest_id=u.id) AS trips,"
                         " (SELECT COUNT(*) FROM listings l WHERE l.host_id=u.id AND l.active=1) AS places"
                         " FROM users u ORDER BY u.id").fetchall()


def admin_bookings():
    with db.session() as c:
        db.expire_pending(c)
        return c.execute("SELECT b.*, l.title, gu.name AS guest_name, hu.name AS host_name FROM bookings b"
                         " JOIN listings l ON l.id=b.listing_id JOIN users gu ON gu.id=b.guest_id"
                         " JOIN users hu ON hu.id=l.host_id ORDER BY b.id DESC").fetchall()


def admin_cancel_booking(booking_id):
    with db.session() as c:
        b = c.execute("SELECT * FROM bookings WHERE id=?", (booking_id,)).fetchone()
        if b is None:
            raise AppError("Booking not found.")
        if b["status"] == "cancelled":
            raise AppError("That booking is already cancelled.")
        c.execute("UPDATE bookings SET status='cancelled', cancelled_by='admin', cancelled_at=?,"
                  " cancel_reason='Cancelled by RoamRest admin', refund=total_price WHERE id=?",
                  (db._now(), booking_id))


def reset_password(user_id):
    """Gives the user a new random password and returns it (the admin tells the user)."""
    with db.session() as c:
        u = c.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        if u is None:
            raise AppError("User not found.")
        if u["role"] == "admin":
            raise AppError("Admin passwords can't be reset from here.")
        letters = "abcdefghjkmnpqrstuvwxyz23456789"
        new = "".join(secrets.choice(letters) for _ in range(10))
        salt = os.urandom(16).hex()
        c.execute("UPDATE users SET password_hash=?, salt=? WHERE id=?", (db._hash(new, salt), salt, user_id))
    return new


# ---- admin create / edit / delete (users, listings, bookings, reviews)
def _user_fields(name, email, phone):
    name, email, phone = (name or "").strip(), (email or "").strip().lower(), (phone or "").strip()
    if not name or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise AppError("Please enter a name and a valid email.")
    if phone:
        db._check_phone(phone, "Phone number")
    return name, email, phone


def admin_add_user(name, email, password, role="guest", phone=""):
    if role not in ("guest", "host"):
        raise AppError("Role must be guest or host.")
    name, email, phone = _user_fields(name, email, phone)
    if len(password or "") < 6:
        raise AppError("Password must be at least 6 characters.")
    try:
        with db.session() as c:
            uid = db._insert_user(c, name, email, password, role)
            c.execute("UPDATE users SET phone=? WHERE id=?", (phone, uid))
    except sqlite3.IntegrityError:
        raise AppError("An account with that email already exists.")
    return uid


def admin_update_user(user_id, name, email, phone, role, active):
    if role not in ("guest", "host"):
        raise AppError("Role must be guest or host.")
    name, email, phone = _user_fields(name, email, phone)
    with db.session() as c:
        u = c.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        if u is None:
            raise AppError("User not found.")
        if u["role"] == "admin":
            raise AppError("Admin accounts can't be changed from here.")
        if c.execute("SELECT 1 FROM users WHERE email=? AND id!=?", (email, user_id)).fetchone():
            raise AppError("Another account already uses that email.")
        c.execute("UPDATE users SET name=?, email=?, phone=?, role=?, active=? WHERE id=?",
                  (name, email, phone, role, int(bool(active)), user_id))


def admin_delete_user(user_id):
    """Permanently deletes a user, but only one with no history. Otherwise they should be deactivated."""
    with db.session() as c:
        u = c.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        if u is None:
            raise AppError("User not found.")
        if u["role"] == "admin":
            raise AppError("Admin accounts can't be deleted from here.")

        def n(sql):
            return c.execute(sql, (user_id,)).fetchone()[0]
        trips = n("SELECT COUNT(*) FROM bookings WHERE guest_id=?")
        places = n("SELECT COUNT(*) FROM listings WHERE host_id=?")
        reviews = n("SELECT COUNT(*) FROM reviews WHERE guest_id=?")
        msgs = c.execute("SELECT COUNT(*) FROM messages WHERE guest_id=? OR sender_id=?",
                         (user_id, user_id)).fetchone()[0]
        if trips or places or reviews or msgs:
            raise AppError(f"{u['name']} has history ({trips} trips, {places} listings, {reviews} reviews, "
                           f"{msgs} messages), so they can't be deleted. Deactivate the account instead.")
        c.execute("DELETE FROM favorites WHERE user_id=?", (user_id,))
        c.execute("DELETE FROM payment_methods WHERE user_id=?", (user_id,))
        c.execute("DELETE FROM payout_methods WHERE host_id=?", (user_id,))
        c.execute("DELETE FROM users WHERE id=?", (user_id,))


def admin_save_listing(listing_id, host_id, title, category, location, price, max_guests, description,
                       amenities, policy, status):
    """Creates (listing_id=None) or updates a listing. `price` is in US dollars."""
    price, max_guests = db._validate_listing(title, category, location, price, max_guests)
    db._check_policy(policy)
    if status not in ("pending", "approved", "rejected"):
        raise AppError("Choose a status.")
    with db.session() as c:
        h = c.execute("SELECT * FROM users WHERE id=?", (host_id,)).fetchone()
        if h is None or h["role"] == "admin":
            raise AppError("Choose a host for this listing.")
        if h["role"] == "guest":  # owning a listing makes the user a host
            c.execute("UPDATE users SET role='host' WHERE id=?", (host_id,))
        if listing_id is None:
            seed = db._image_seed(title)
            cur = c.execute(
                "INSERT INTO listings (host_id,title,category,location,price_per_night,max_guests,description,"
                "blurb,amenities,image_seed,cancellation_policy,status) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (host_id, title.strip(), category, location.strip(), price, max_guests, description.strip(),
                 db._blurb(description), db._amenities(amenities), seed, policy, status))
            return cur.lastrowid
        cur = c.execute(
            "UPDATE listings SET host_id=?, title=?, category=?, location=?, price_per_night=?, max_guests=?,"
            " description=?, blurb=?, amenities=?, cancellation_policy=?, status=? WHERE id=? AND active=1",
            (host_id, title.strip(), category, location.strip(), price, max_guests, description.strip(),
             db._blurb(description), db._amenities(amenities), policy, status, listing_id))
        if cur.rowcount == 0:
            raise AppError("Listing not found.")
        return listing_id


def admin_save_booking(booking_id, listing_id, guest_id, check_in, check_out, guests, status):
    """Creates (booking_id=None) or edits a booking. The total is worked out from the nightly price."""
    ci, co = db.parse_date(check_in), db.parse_date(check_out)
    if co <= ci:
        raise AppError("Check-out must be after check-in.")
    if status not in ("pending", "confirmed", "cancelled"):
        raise AppError("Choose a status.")
    try:
        guests = int(str(guests).strip())
    except ValueError:
        raise AppError("Guests must be a whole number.")
    with db.session() as c:
        listing = c.execute("SELECT * FROM listings WHERE id=? AND active=1", (listing_id,)).fetchone()
        guest = c.execute("SELECT * FROM users WHERE id=? AND role!='admin'", (guest_id,)).fetchone()
        if listing is None:
            raise AppError("Choose a place.")
        if guest is None:
            raise AppError("Choose a guest.")
        if listing["host_id"] == guest_id:
            raise AppError("A host can't book their own listing.")
        if guests < 1 or guests > listing["max_guests"]:
            raise AppError(f"This place sleeps up to {listing['max_guests']} guests.")
        if status in ("pending", "confirmed") and c.execute(
                "SELECT 1 FROM bookings WHERE listing_id=? AND status IN ('confirmed','pending')"
                " AND check_in < ? AND check_out > ? AND id != ?",
                (listing_id, co.isoformat(), ci.isoformat(), booking_id or 0)).fetchone():
            raise AppError("Those dates clash with another confirmed or pending booking for this place.")
        total = (co - ci).days * listing["price_per_night"]
        now = db._now()
        if booking_id is None:
            cancelled = status == "cancelled"
            cur = c.execute(
                "INSERT INTO bookings (listing_id,guest_id,check_in,check_out,guests,total_price,status,created_at,"
                "policy,confirmed_at,cancelled_by,cancelled_at,cancel_reason,refund) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (listing_id, guest_id, ci.isoformat(), co.isoformat(), guests, total, status, now,
                 listing["cancellation_policy"] or db.DEFAULT_POLICY, now if status == "confirmed" else "",
                 "admin" if cancelled else "", now if cancelled else "",
                 "Created as cancelled by RoamRest admin" if cancelled else "", total if cancelled else 0))
            _admin_payment(c, cur.lastrowid, guest_id, total, now)
            return cur.lastrowid
        old = c.execute("SELECT * FROM bookings WHERE id=?", (booking_id,)).fetchone()
        if old is None:
            raise AppError("Booking not found.")
        confirmed_at = old["confirmed_at"] or (now if status == "confirmed" else "")
        if status == "cancelled" and old["status"] != "cancelled":
            cancel = ("admin", now, "Cancelled by RoamRest admin", total)
        elif status == "cancelled":
            # keep the same share of the total that was refunded before (full stays full, 50% stays 50%)
            old_total = float(old["total_price"] or 0)
            share = (float(old["refund"] or 0) / old_total) if old_total > 0 else 1.0
            cancel = (old["cancelled_by"], old["cancelled_at"], old["cancel_reason"],
                      round(min(share, 1.0) * total, 2))
        else:
            cancel = ("", "", "", 0)
        c.execute("UPDATE bookings SET listing_id=?, guest_id=?, check_in=?, check_out=?, guests=?, total_price=?,"
                  " status=?, confirmed_at=?, cancelled_by=?, cancelled_at=?, cancel_reason=?, refund=? WHERE id=?",
                  (listing_id, guest_id, ci.isoformat(), co.isoformat(), guests, total, status, confirmed_at,
                   *cancel, booking_id))
        _admin_payment(c, booking_id, guest_id, total, old["created_at"] or now)
        c.execute("UPDATE payments SET amount=?, user_id=? WHERE booking_id=?", (total, guest_id, booking_id))
        return booking_id


def _admin_payment(c, booking_id, guest_id, total, when):
    """Give a booking made by the admin a payment record (if it has none), so its Payment section is complete."""
    c.execute("INSERT OR IGNORE INTO payments (booking_id,user_id,method_id,method_kind,method_label,plan,amount,created_at)"
              " VALUES (?,?,?,?,?,?,?,?)",
              (booking_id, guest_id, None, "admin", "Recorded by RoamRest admin", "full", total, when))


def admin_delete_booking(booking_id):
    """Permanently removes a booking with its payment record and review."""
    with db.session() as c:
        b = c.execute("SELECT * FROM bookings WHERE id=?", (booking_id,)).fetchone()
        if b is None:
            raise AppError("Booking not found.")
        c.execute("DELETE FROM reviews WHERE booking_id=?", (booking_id,))
        _recompute(c, b["listing_id"])
        c.execute("DELETE FROM payments WHERE booking_id=?", (booking_id,))
        c.execute("DELETE FROM bookings WHERE id=?", (booking_id,))


def admin_save_review(review_id, booking_id, rating, comment, hidden=False):
    """Creates (review_id=None, for a confirmed booking) or edits a review."""
    rating, comment = _check_review(rating, comment)
    with db.session() as c:
        if review_id is None:
            b = c.execute("SELECT * FROM bookings WHERE id=?", (booking_id,)).fetchone()
            if b is None:
                raise AppError("Choose a booking to review.")
            if b["status"] != "confirmed":
                raise AppError("Only confirmed bookings can be reviewed.")
            if c.execute("SELECT 1 FROM reviews WHERE booking_id=?", (booking_id,)).fetchone():
                raise AppError("That booking already has a review.")
            c.execute("INSERT INTO reviews (booking_id, listing_id, guest_id, rating, comment, created_at, hidden)"
                      " VALUES (?,?,?,?,?,?,?)",
                      (booking_id, b["listing_id"], b["guest_id"], rating, comment, db._now(), int(hidden)))
            lid = b["listing_id"]
        else:
            r = c.execute("SELECT * FROM reviews WHERE id=?", (review_id,)).fetchone()
            if r is None:
                raise AppError("Review not found.")
            c.execute("UPDATE reviews SET rating=?, comment=?, hidden=? WHERE id=?",
                      (rating, comment, int(hidden), review_id))
            lid = r["listing_id"]
        _recompute(c, lid)


# =========================================================== screens
class _UI:
    """Gives extras.py access to app.py's colours and helpers (L, button, money, ...)."""
    def __init__(self, ns):
        self.__dict__["_ns"] = ns

    def __getattr__(self, name):
        return self._ns[name]


def pie_card(ui, parent, title, items):
    """items = [(label, value, colour)]. A donut chart drawn on a Canvas, with a legend."""
    card = tk.Frame(parent, bg=ui.CARD, highlightbackground=ui.LINE, highlightthickness=1, padx=16, pady=14)
    ui.L(card, title, 11, "bold", family="Georgia").pack(anchor="w")
    row = tk.Frame(card, bg=ui.CARD)
    row.pack(anchor="w", pady=(10, 0))
    size, pad = 124, 4
    cv = tk.Canvas(row, width=size, height=size, bg=ui.CARD, highlightthickness=0)
    cv.pack(side="left")
    total = sum(v for _, v, _ in items)
    live = [i for i in items if i[1] > 0]
    box = (pad, pad, size - pad, size - pad)
    if not total:
        cv.create_oval(*box, outline=ui.LINE, width=2)
        cv.create_text(size // 2, size // 2, text="No data\nyet", fill=ui.MUTED, font=("Arial", 9), justify="center")
    else:
        if len(live) == 1:
            cv.create_oval(*box, fill=live[0][2], outline="")
        else:
            start = 90
            for _, v, col in live:
                ext = -360 * v / total
                cv.create_arc(*box, start=start, extent=ext, fill=col, outline=ui.CARD, width=2)
                start += ext
        c, r = size // 2, size * 0.30
        cv.create_oval(c - r, c - r, c + r, c + r, fill=ui.CARD, outline="")
        cv.create_text(c, c - 6, text=str(total), font=("Georgia", 16, "bold"), fill=ui.INK)
        cv.create_text(c, c + 12, text="total", font=("Arial", 8), fill=ui.MUTED)
    legend = tk.Frame(row, bg=ui.CARD)
    legend.pack(side="left", padx=(16, 0))
    for label, v, col in items:
        r = tk.Frame(legend, bg=ui.CARD)
        r.pack(anchor="w", pady=2)
        tk.Frame(r, bg=col, width=10, height=10).pack(side="left")
        pct = f" ({v * 100 / total:.0f}%)" if total else ""
        ui.L(r, f"{label}: {v}{pct}", 9).pack(side="left", padx=(6, 0))
    return card


def bar_card(ui, parent, title, data):
    """data = [(label, count, value)] - a simple column chart."""
    card = tk.Frame(parent, bg=ui.CARD, highlightbackground=ui.LINE, highlightthickness=1, padx=16, pady=14)
    ui.L(card, title, 11, "bold", family="Georgia").pack(anchor="w")
    W, H = 440, 170
    cv = tk.Canvas(card, width=W, height=H, bg=ui.CARD, highlightthickness=0)
    cv.pack(pady=(10, 0))
    mx = max([n for _, n, _ in data] + [1])
    slot = W / len(data)
    bw = slot * 0.5
    base, top = H - 26, 24
    cv.create_line(6, base, W - 6, base, fill=ui.LINE)
    for i, (label, n, _) in enumerate(data):
        x0 = i * slot + (slot - bw) / 2
        h = (base - top) * n / mx
        if n:
            cv.create_rectangle(x0, base - h, x0 + bw, base, fill=ui.CLAY, outline="")
        cv.create_text(x0 + bw / 2, base - h - 10 if n else base - 10, text=str(n), fill=ui.INK,
                       font=("Arial", 9, "bold"))
        cv.create_text(x0 + bw / 2, base + 13, text=label, fill=ui.MUTED, font=("Arial", 9))
    ui.L(card, f"Booked value in this period: {ui.money0(sum(v for _, _, v in data))}", 9,
         fg=ui.MUTED).pack(anchor="w", pady=(6, 0))
    return card


def top_card(ui, parent, rows):
    card = tk.Frame(parent, bg=ui.CARD, highlightbackground=ui.LINE, highlightthickness=1, padx=16, pady=14)
    ui.L(card, "Top listings by revenue", 11, "bold", family="Georgia").pack(anchor="w")
    if not rows:
        ui.L(card, "No confirmed bookings yet.", 10, fg=ui.MUTED).pack(anchor="w", pady=(14, 0))
        return card
    mx = max(r["rev"] for r in rows) or 1
    grid = tk.Frame(card, bg=ui.CARD)
    grid.pack(anchor="w", pady=(10, 0))
    for i, r in enumerate(rows):
        t = r["title"] if len(r["title"]) <= 24 else r["title"][:23] + "\u2026"
        ui.L(grid, t, 9, "bold").grid(row=i, column=0, sticky="w", pady=4)
        bar = tk.Canvas(grid, width=150, height=12, bg=ui.CARD, highlightthickness=0)
        bar.create_rectangle(0, 0, 150, 12, fill=ui.PAPER2, outline="")
        bar.create_rectangle(0, 0, max(4, 150 * r["rev"] / mx), 12, fill=ui.CLAY, outline="")
        bar.grid(row=i, column=1, padx=10)
        ui.L(grid, f"{ui.money0(r['rev'])}  \u00B7  {r['n']} booking{'s' if r['n'] != 1 else ''}", 9,
             fg=ui.MUTED).grid(row=i, column=2, sticky="w")
    return card


def open_form(ui, parent, title, fields, initial, on_save, save_text="Save", note=""):
    """A small pop-up form. fields = [{"key", "label", "kind": entry|password|combo|text, "values", "wide",
    "disabled"}]. on_save(values) does the work (and may raise AppError); the form closes when it returns."""
    win = tk.Toplevel(parent)
    win.title(title)
    win.configure(bg=ui.PAPER, padx=26, pady=20)
    win.resizable(False, False)
    win.transient(parent.winfo_toplevel())
    ui.L(win, title, 16, "bold", family="Georgia").pack(anchor="w")
    if note:
        ui.L(win, note, 9, fg=ui.MUTED, wraplength=520, justify="left").pack(anchor="w", pady=(4, 0))
    form = tk.Frame(win, bg=ui.PAPER)
    form.pack(fill="x", pady=(8, 0))
    form.columnconfigure(0, weight=1, uniform="c")
    form.columnconfigure(1, weight=1, uniform="c")
    vars_, texts = {}, {}
    row = col = 0
    for f in fields:
        kind, key = f.get("kind", "entry"), f["key"]
        wide = f.get("wide") or kind == "text"
        if wide and col == 1:
            row, col = row + 1, 0
        cell = tk.Frame(form, bg=ui.PAPER)
        cell.grid(row=row, column=0 if wide or col == 0 else 1, columnspan=2 if wide else 1, sticky="ew", padx=6)
        ui.L(cell, f["label"].upper(), 8, "bold", fg=ui.MUTED).pack(anchor="w", pady=(8, 2))
        init = initial.get(key, "")
        if kind == "text":
            w = tk.Text(cell, width=1, height=4, wrap="word", font=("Arial", 10), relief="flat", bg="white",
                        fg=ui.INK, padx=8, pady=6, highlightthickness=1, highlightbackground=ui.LINE,
                        highlightcolor=ui.CLAY, insertbackground=ui.INK)
            w.insert("1.0", str(init))
            w.pack(fill="x")
            texts[key] = w
        else:
            var = tk.StringVar(value=str(init))
            vars_[key] = var
            width = 58 if wide else 26
            if kind == "combo":
                w = ttk.Combobox(cell, textvariable=var, values=f["values"], state="readonly", width=width)
            else:
                w = ttk.Entry(cell, textvariable=var, show="*" if kind == "password" else "", width=width)
            w.pack(fill="x")
            if f.get("disabled"):
                w.config(state="disabled")
        if wide:
            row, col = row + 1, 0
        else:
            col += 1
            if col == 2:
                row, col = row + 1, 0

    def submit():
        values = {k: v.get() for k, v in vars_.items()}
        values.update({k: w.get("1.0", "end").strip() for k, w in texts.items()})
        try:
            ok = on_save(values)
        except AppError as e:
            return messagebox.showerror(title, str(e), parent=win)
        if ok is not False:
            win.destroy()

    bar = tk.Frame(win, bg=ui.PAPER)
    bar.pack(anchor="w", pady=(16, 0))
    ui.button(bar, save_text, submit).pack(side="left")
    ui.button(bar, "Cancel", win.destroy, False).pack(side="left", padx=8)
    win.bind("<Escape>", lambda e: win.destroy())
    try:
        win.wait_visibility()
        win.grab_set()
    except tk.TclError:
        pass
    return win


def make_admin(ui):
    class AdminWindow(ui.Page):  # a full-screen page with a Back button (Page is defined in app.py)
        def __init__(self, app):
            super().__init__(app.root)
            self.app = app
            self.title("RoamRest Admin")
            self.geometry("1180x780")
            self.minsize(980, 640)
            self.configure(bg=ui.PAPER)
            self.filters = {}

            head = tk.Frame(self, bg=ui.PAPER)
            head.pack(fill="x", padx=24, pady=(18, 0))
            left = tk.Frame(head, bg=ui.PAPER)
            left.pack(side="left")
            ui.L(left, "Admin dashboard", 22, "bold", family="Georgia").pack(anchor="w")
            self.stamp = ui.L(left, "", 9, fg=ui.MUTED)
            self.stamp.pack(anchor="w", pady=(2, 0))
            ui.button(head, "Refresh", self.refresh, False, small=True).pack(side="right", anchor="s")

            self.nb = ttk.Notebook(self)
            self.nb.pack(fill="both", expand=True, padx=18, pady=(12, 18))
            self.tabs = {}
            for key, label in [("overview", "Overview"), ("listings", "Listings"), ("users", "Users"),
                               ("bookings", "Bookings"), ("reviews", "Reviews")]:
                f = tk.Frame(self.nb, bg=ui.PAPER)
                self.nb.add(f, text=label)
                self.tabs[key] = f
            self.build_overview(self.tabs["overview"])
            self.build_listings(self.tabs["listings"])
            self.build_users(self.tabs["users"])
            self.build_bookings(self.tabs["bookings"])
            self.build_reviews(self.tabs["reviews"])
            self.refresh()

        # ---------- shared helpers
        def toolbar(self, parent, key, choices, fill):
            """Search box + dropdown filter + Export. Returns (bar, tree-less)."""
            bar = tk.Frame(parent, bg=ui.PAPER)
            bar.pack(fill="x", padx=16, pady=(14, 8))
            q, f = tk.StringVar(), tk.StringVar(value=choices[0])
            self.filters[key] = (q, f)
            ui.L(bar, "Search", 9, "bold", fg=ui.MUTED).pack(side="left")
            ttk.Entry(bar, textvariable=q, width=26).pack(side="left", padx=(6, 14))
            cb = ttk.Combobox(bar, textvariable=f, values=choices, state="readonly", width=14)
            cb.pack(side="left")
            q.trace_add("write", lambda *a: fill())
            cb.bind("<<ComboboxSelected>>", lambda e: fill())
            return bar

        def table(self, parent, columns, widths, tags=None):
            box = tk.Frame(parent, bg=ui.CARD, highlightbackground=ui.LINE, highlightthickness=1)
            box.pack(fill="both", expand=True, padx=16)
            fr, tree = ui.make_tree(box, columns, widths, 14)
            fr.pack(fill="both", expand=True)
            for tag, color in (tags or {}).items():
                tree.tag_configure(tag, foreground=color)
            return tree

        def actions(self, parent):
            bar = tk.Frame(parent, bg=ui.PAPER)
            bar.pack(fill="x", padx=16, pady=12)
            return bar

        def export(self, tree, name):
            path = filedialog.asksaveasfilename(
                parent=self, defaultextension=".csv", initialfile=f"roamrest-{name}-{date.today()}.csv",
                filetypes=[("CSV (opens in Excel)", "*.csv")])
            if not path:
                return
            try:
                with open(path, "w", newline="", encoding="utf-8-sig") as fh:
                    w = csv.writer(fh)
                    w.writerow([tree.heading(c)["text"] for c in tree["columns"]])
                    for iid in tree.get_children():
                        w.writerow(tree.item(iid)["values"])
            except OSError as e:
                return messagebox.showerror("Export", f"Couldn't save the file:\n{e}", parent=self)
            messagebox.showinfo("Export", f"Saved {len(tree.get_children())} rows to:\n{path}", parent=self)

        def changed(self):
            """After any admin action: refresh here and everywhere else."""
            self.refresh()
            self.app.run_search()
            self.app.refresh_trips()
            self.app.refresh_nav()

        def go(self, tab, filt=None):
            self.nb.select(self.tabs[tab])
            if filt and tab in self.filters:
                self.filters[tab][1].set(filt)
                self.refresh()

        def need(self, tree, what):
            iid = ui.selected_id(tree)
            if iid is None:
                messagebox.showinfo("Admin", f"Select a {what} first.", parent=self)
            return iid

        def match(self, key, *texts):
            q = self.filters[key][0].get().strip().lower()
            return not q or q in " ".join(str(t) for t in texts).lower()

        # ---------- helpers for the add / edit forms
        @staticmethod
        def pick_id(label):
            m = re.search(r"#(\d+)\)\s*$", label or "")
            if not m:
                raise AppError("Choose an option from the list.")
            return int(m.group(1))

        @staticmethod
        def user_label(u):
            return f"{u['name']} · {u['email']}  (#{u['id']})"

        @staticmethod
        def listing_label(r):
            return f"{r['title']} · {r['location']}  (#{r['id']})"

        def people(self):
            return {u["id"]: self.user_label(u) for u in admin_users() if u["role"] != "admin"}

        def saved(self):
            """Close-out for every add / edit / delete: refresh here and on the other pages."""
            self.changed()
            return True

        # ---------- overview
        def build_overview(self, f):
            self.cv = tk.Canvas(f, bg=ui.PAPER, highlightthickness=0)
            sb = ttk.Scrollbar(f, orient="vertical", command=self.cv.yview)
            self.cv.configure(yscrollcommand=sb.set)
            sb.pack(side="right", fill="y")
            self.cv.pack(side="left", fill="both", expand=True)
            self.ov = tk.Frame(self.cv, bg=ui.PAPER)
            win = self.cv.create_window((0, 0), window=self.ov, anchor="nw")
            self.ov.bind("<Configure>", lambda e: self.cv.configure(scrollregion=self.cv.bbox("all")))
            self.cv.bind("<Configure>", lambda e: self.cv.itemconfig(win, width=e.width))
            self.bind("<MouseWheel>", lambda e: self.cv.yview_scroll(int(-e.delta / 120), "units")
                      if self.nb.index("current") == 0 else None)

        def kpi(self, parent, col, label, value, sub):
            c = tk.Frame(parent, bg=ui.CARD, highlightbackground=ui.LINE, highlightthickness=1, padx=16, pady=14)
            c.grid(row=col // 4, column=col % 4, sticky="nsew", padx=6, pady=6)
            ui.L(c, label.upper(), 8, "bold", fg=ui.MUTED).pack(anchor="w")
            ui.L(c, value, 22, "bold", family="Georgia").pack(anchor="w", pady=(4, 0))
            ui.L(c, sub, 9, fg=ui.MUTED).pack(anchor="w")

        def render_overview(self, o):
            for w in self.ov.winfo_children():
                w.destroy()
            body = tk.Frame(self.ov, bg=ui.PAPER)
            body.pack(fill="x", padx=14, pady=(14, 20))
            for i in range(4):
                body.columnconfigure(i, weight=1, uniform="k")

            kp = tk.Frame(body, bg=ui.PAPER)
            kp.grid(row=0, column=0, columnspan=4, sticky="ew")
            for i in range(4):
                kp.columnconfigure(i, weight=1, uniform="k")
            users = o["guests"] + o["hosts"]
            avg = f"{o['avg_rating']:.2f} \u2605" if o["avg_rating"] else "\u2014"
            for i, (a, b, c) in enumerate([
                    ("Revenue (confirmed)", ui.money0(o["revenue"]), f"{o['confirmed']} confirmed bookings"),
                    ("Platform earnings", ui.money0(o["revenue"] * PLATFORM_FEE), f"{PLATFORM_FEE * 100:.0f}% host fee (estimate)"),
                    ("Active users", str(users), f"{o['hosts']} hosts \u00B7 {o['guests']} guests"),
                    ("Live listings", str(o["live"]), f"{o['pending_listings']} awaiting approval"),
                    ("Pending requests", str(o["pending"]), "waiting for hosts to answer"),
                    ("Upcoming stays", str(o["upcoming"]), "confirmed, not started yet"),
                    ("Cancellations", str(o["cancelled"]), f"{ui.money0(o['refunds'])} refunded"),
                    ("Average rating", avg, f"{o['reviews']} reviews written on RoamRest")]):
                self.kpi(kp, i, a, b, c)

            # needs attention
            att = tk.Frame(body, bg=ui.CARD, highlightbackground=ui.LINE, highlightthickness=1, padx=18, pady=14)
            att.grid(row=1, column=0, columnspan=4, sticky="ew", padx=6, pady=(10, 6))
            ui.L(att, "Needs attention", 11, "bold", family="Georgia").pack(anchor="w")
            items = []
            if o["pending_listings"]:
                items.append((f"{o['pending_listings']} listing(s) waiting for your approval", "Review",
                              lambda: self.go("listings", "pending")))
            if o["pending"]:
                items.append((f"{o['pending']} reservation request(s) waiting for hosts "
                              "(they expire after 24 hours)", "View", lambda: self.go("bookings", "pending")))
            if o["hidden_reviews"]:
                items.append((f"{o['hidden_reviews']} review(s) are hidden", "Open",
                              lambda: self.go("reviews", "Hidden")))
            if o["inactive"]:
                items.append((f"{o['inactive']} deactivated account(s)", "Open", lambda: self.go("users")))
            if not items:
                ui.L(att, "\u2713  Nothing needs your attention right now.", 10, fg="#2F6B3A").pack(anchor="w", pady=(8, 0))
            for text, label, cmd in items:
                r = tk.Frame(att, bg=ui.CARD)
                r.pack(fill="x", pady=(8, 0))
                ui.L(r, "\u25CF  " + text, 10).pack(side="left")
                ui.button(r, label, cmd, small=True).pack(side="right")

            # pies
            status = dict(counts("SELECT status, COUNT(*) FROM bookings GROUP BY status"))
            pies = [
                ("Bookings by status", [("Confirmed", status.get("confirmed", 0), "#2F6B3A"),
                                        ("Pending", status.get("pending", 0), "#C9852B"),
                                        ("Cancelled", status.get("cancelled", 0), "#9B2C2C")]),
                ("Live listings by category",
                 [(k, v, ui.PAPER and PALETTE[i % len(PALETTE)]) for i, (k, v) in enumerate(counts(
                     "SELECT category, COUNT(*) FROM listings WHERE active=1 AND status='approved'"
                     " GROUP BY category ORDER BY COUNT(*) DESC"))]),
                ("Users by role", [("Guests", o["guests"], PALETTE[3]), ("Hosts", o["hosts"], PALETTE[0])])]
            for i, (title, items_) in enumerate(pies):
                body.columnconfigure(i, weight=1)
                card = pie_card(ui, body, title, items_)
                card.grid(row=2, column=i if i < 3 else 0, sticky="nsew", padx=6, pady=6, columnspan=1)
            body.grid_columnconfigure(3, weight=0)

            bar = bar_card(ui, body, "Bookings per month (not cancelled)", monthly_bookings())
            bar.grid(row=3, column=0, columnspan=2, sticky="nsew", padx=6, pady=6)
            top = top_card(ui, body, top_listings())
            top.grid(row=3, column=2, columnspan=2, sticky="nsew", padx=6, pady=6)

        # ---------- listings
        def build_listings(self, f):
            bar = self.toolbar(f, "listings", ["All", "pending", "approved", "rejected"], self.fill_listings)
            self.ltree = self.table(
                f, [("title", "Title"), ("host", "Host"), ("cat", "Category"), ("loc", "Location"),
                    ("price", "Price/night"), ("rating", "Rating"), ("status", "Status")],
                [200, 120, 130, 170, 90, 80, 90],
                {"pending": ui.STATUS_STYLE["pending"][1], "approved": ui.STATUS_STYLE["confirmed"][1],
                 "rejected": ui.STATUS_STYLE["cancelled"][1]})
            ui.button(bar, "Export CSV", lambda: self.export(self.ltree, "listings"), False, small=True).pack(side="right")
            a = self.actions(f)
            ui.button(a, "Add listing", lambda: self.listing_form()).pack(side="left")
            ui.button(a, "Edit listing", self.edit_listing, False).pack(side="left", padx=(8, 0))
            ui.button(a, "Approve", lambda: self.set_status("approved"), False).pack(side="left", padx=(8, 0))
            ui.button(a, "Reject", lambda: self.set_status("rejected"), False).pack(side="left", padx=(8, 0))
            ui.button(a, "View details", self.listing_details, False).pack(side="left", padx=(8, 0))
            ui.button(a, "Remove listing", self.remove_listing, False).pack(side="left", padx=(8, 0))

        def edit_listing(self):
            lid = self.need(self.ltree, "listing")
            if lid is not None:
                self.listing_form(lid)

        def listing_form(self, lid=None):
            r = self.rows_l.get(lid) if lid else None
            people = self.people()
            if not people:
                return messagebox.showinfo("Admin", "Add a user first. A listing needs a host.", parent=self)
            rate, sym = ui._cur()[1], ui._cur()[0]
            fields = [
                {"key": "host", "label": "Host", "kind": "combo", "values": list(people.values()), "wide": True},
                {"key": "title", "label": "Title", "kind": "entry", "wide": True},
                {"key": "category", "label": "Category", "kind": "combo", "values": db.CATEGORIES},
                {"key": "location", "label": "Location (City, Country)", "kind": "entry"},
                {"key": "price", "label": f"Price per night ({sym})", "kind": "entry"},
                {"key": "guests", "label": "Max guests", "kind": "entry"},
                {"key": "policy", "label": "Cancellation policy", "kind": "combo", "values": list(db.POLICIES)},
                {"key": "status", "label": "Status", "kind": "combo", "values": ["pending", "approved", "rejected"]},
                {"key": "amenities", "label": "Amenities (comma separated)", "kind": "entry", "wide": True},
                {"key": "description", "label": "Description", "kind": "text"}]
            if r:
                initial = {"host": people.get(r["host_id"], ""), "title": r["title"], "category": r["category"],
                           "location": r["location"], "price": f"{round(r['price_per_night'] * rate, 2):g}",
                           "guests": r["max_guests"], "policy": r["cancellation_policy"] or db.DEFAULT_POLICY,
                           "status": r["status"], "amenities": r["amenities"] or "",
                           "description": r["description"] or ""}
            else:
                initial = {"category": db.CATEGORIES[0], "policy": db.DEFAULT_POLICY, "status": "approved",
                           "guests": "2"}

            def save(v):
                admin_save_listing(lid, self.pick_id(v["host"]), v["title"], v["category"], v["location"],
                                   ui.to_usd(v["price"]), v["guests"], v["description"], v["amenities"],
                                   v["policy"], v["status"])
                return self.saved()
            open_form(ui, self, "Edit listing" if r else "Add listing", fields, initial, save,
                      "Save changes" if r else "Create listing",
                      "Admin listings can go live straight away. Set the status to approved." if not r else "")

        def fill_listings(self):
            ui.clear(self.ltree)
            want = self.filters["listings"][1].get()
            self.rows_l = {r["id"]: r for r in db.admin_listings()}
            for r in self.rows_l.values():
                if (want != "All" and r["status"] != want) or not self.match(
                        "listings", r["title"], r["host_name"], r["category"], r["location"]):
                    continue
                rating = f"\u2605 {r['rating']:.2f}" if r["rating"] else "New"
                self.ltree.insert("", "end", iid=str(r["id"]), tags=(r["status"],), values=(
                    r["title"], r["host_name"], r["category"], r["location"],
                    ui.fmt_night(r["price_per_night"]), rating, r["status"].capitalize()))

        def set_status(self, status):
            lid = self.need(self.ltree, "listing")
            if lid is None:
                return
            try:
                db.set_listing_status(lid, status)
            except AppError as e:
                return messagebox.showerror("Admin", str(e), parent=self)
            self.changed()

        def listing_details(self):
            lid = self.need(self.ltree, "listing")
            if lid is None:
                return
            r = self.rows_l[lid]
            messagebox.showinfo(r["title"], (
                f"{r['category']}  \u00B7  {r['location']}\nHost: {r['host_name']}\n"
                f"{ui.fmt_night(r['price_per_night'])} / night  \u00B7  sleeps {r['max_guests']}\n"
                f"Status: {r['status']}\n\n{r['description'] or 'No description.'}\n\n"
                f"Amenities: {r['amenities'] or 'none listed'}"), parent=self)

        def remove_listing(self):
            lid = self.need(self.ltree, "listing")
            if lid is None or not messagebox.askyesno(
                    "Remove", "Remove this listing from the platform?", parent=self):
                return
            try:
                names = db.delete_listing(lid)
            except AppError as e:
                return messagebox.showerror("Remove", str(e), parent=self)
            for name in names:
                ui.delete_photo_file(name)
            self.changed()

        # ---------- users
        def build_users(self, f):
            bar = self.toolbar(f, "users", ["All", "guest", "host", "admin"], self.fill_users)
            self.utree = self.table(
                f, [("name", "Name"), ("email", "Email"), ("phone", "Phone"), ("role", "Role"),
                    ("active", "Active"), ("trips", "Trips"), ("places", "Listings")],
                [160, 220, 130, 80, 70, 70, 80], {"off": "#9A9080"})
            ui.button(bar, "Export CSV", lambda: self.export(self.utree, "users"), False, small=True).pack(side="right")
            a = self.actions(f)
            ui.button(a, "Add user", lambda: self.user_form()).pack(side="left")
            ui.button(a, "Edit user", self.edit_user, False).pack(side="left", padx=(8, 0))
            ui.button(a, "Delete user", self.delete_user, False).pack(side="left", padx=(8, 0))
            ui.button(a, "Make host", lambda: self.user_do(db.set_role, "host"), False).pack(side="left", padx=(8, 0))
            ui.button(a, "Make guest", lambda: self.user_do(db.set_role, "guest"), False).pack(side="left", padx=(8, 0))
            ui.button(a, "Deactivate", self.deactivate, False).pack(side="left", padx=(8, 0))
            ui.button(a, "Reactivate", lambda: self.user_do(db.set_user_active, True), False).pack(side="left", padx=(8, 0))
            ui.button(a, "Reset password", self.reset_pw, False).pack(side="left", padx=(8, 0))

        def edit_user(self):
            uid = self.need(self.utree, "user")
            if uid is not None:
                self.user_form(uid)

        def user_form(self, uid=None):
            u = self.rows_u.get(uid) if uid else None
            if u is not None and u["role"] == "admin":
                return messagebox.showinfo("Admin", "Admin accounts can't be changed from here.", parent=self)
            fields = [{"key": "name", "label": "Full name", "kind": "entry"},
                      {"key": "email", "label": "Email", "kind": "entry"},
                      {"key": "phone", "label": "Phone (optional)", "kind": "entry"},
                      {"key": "role", "label": "Role", "kind": "combo", "values": ["guest", "host"]}]
            if u:
                fields.append({"key": "account", "label": "Account", "kind": "combo",
                               "values": ["active", "deactivated"]})
                initial = {"name": u["name"], "email": u["email"], "phone": u["phone"] or "", "role": u["role"],
                           "account": "active" if u["active"] else "deactivated"}
            else:
                fields.append({"key": "password", "label": "Password (6+ characters)", "kind": "password"})
                initial = {"role": "guest"}

            def save(v):
                if u:
                    admin_update_user(uid, v["name"], v["email"], v["phone"], v["role"], v["account"] == "active")
                else:
                    admin_add_user(v["name"], v["email"], v["password"], v["role"], v["phone"])
                return self.saved()
            open_form(ui, self, "Edit user" if u else "Add user", fields, initial, save,
                      "Save changes" if u else "Create user")

        def delete_user(self):
            uid = self.need(self.utree, "user")
            if uid is None or not messagebox.askyesno(
                    "Delete user", "Permanently delete this user? This only works for accounts with no trips, "
                                   "listings, reviews or messages. Otherwise use Deactivate.", parent=self):
                return
            try:
                admin_delete_user(uid)
            except AppError as e:
                return messagebox.showerror("Delete user", str(e), parent=self)
            self.changed()

        def fill_users(self):
            ui.clear(self.utree)
            want = self.filters["users"][1].get()
            self.rows_u = {u["id"]: u for u in admin_users()}
            for u in self.rows_u.values():
                if (want != "All" and u["role"] != want) or not self.match("users", u["name"], u["email"]):
                    continue
                self.utree.insert("", "end", iid=str(u["id"]), tags=("" if u["active"] else "off",), values=(
                    u["name"], u["email"], u["phone"] or "\u2014", u["role"],
                    "yes" if u["active"] else "no", u["trips"], u["places"]))

        def user_do(self, fn, *args):
            uid = self.need(self.utree, "user")
            if uid is None:
                return
            try:
                fn(uid, *args)
            except AppError as e:
                return messagebox.showerror("Admin", str(e), parent=self)
            self.changed()

        def deactivate(self):
            uid = ui.selected_id(self.utree)
            if uid is not None and not messagebox.askyesno(
                    "Deactivate", "This user will no longer be able to log in, and their listings "
                                  "disappear from search. Continue?", parent=self):
                return
            self.user_do(db.set_user_active, False)

        def reset_pw(self):
            uid = self.need(self.utree, "user")
            if uid is None or not messagebox.askyesno(
                    "Reset password", "Give this user a new temporary password?", parent=self):
                return
            try:
                new = reset_password(uid)
            except AppError as e:
                return messagebox.showerror("Admin", str(e), parent=self)
            self.clipboard_clear()
            self.clipboard_append(new)
            messagebox.showinfo("New password", f"Temporary password:\n\n{new}\n\nIt was copied to your "
                                                "clipboard. Tell the user to change it under Account settings.",
                                parent=self)

        # ---------- bookings
        def build_bookings(self, f):
            bar = self.toolbar(f, "bookings", ["All", "pending", "confirmed", "cancelled"], self.fill_bookings)
            self.btree = self.table(
                f, [("ref", "Ref"), ("title", "Place"), ("guest", "Guest"), ("host", "Host"), ("in", "Check-in"),
                    ("out", "Check-out"), ("total", "Total"), ("status", "Status")],
                [80, 170, 120, 120, 90, 90, 90, 90],
                {"pending": ui.STATUS_STYLE["pending"][1], "confirmed": ui.STATUS_STYLE["confirmed"][1],
                 "cancelled": "#9A9080"})
            ui.button(bar, "Export CSV", lambda: self.export(self.btree, "bookings"), False, small=True).pack(side="right")
            a = self.actions(f)
            ui.button(a, "Add booking", lambda: self.booking_form()).pack(side="left")
            ui.button(a, "Edit booking", self.edit_booking, False).pack(side="left", padx=(8, 0))
            ui.button(a, "Delete booking", self.delete_booking, False).pack(side="left", padx=(8, 0))
            ui.button(a, "Cancel booking", self.cancel_booking, False).pack(side="left", padx=(8, 0))
            ui.L(a, "Cancelling refunds the guest in full. Deleting removes the booking for good.", 9,
                 fg=ui.MUTED).pack(side="left", padx=10)

        def edit_booking(self):
            bid = self.need(self.btree, "booking")
            if bid is not None:
                self.booking_form(bid)

        def booking_form(self, bid=None):
            b = self.rows_b.get(bid) if bid else None
            places = {r["id"]: self.listing_label(r) for r in db.admin_listings()}
            if b is not None:
                places.setdefault(b["listing_id"], f"{b['title']}  (#{b['listing_id']})")
            people = self.people()
            if not places or not people:
                return messagebox.showinfo("Admin", "You need at least one listing and one user first.", parent=self)
            fields = [{"key": "place", "label": "Place", "kind": "combo", "values": list(places.values()), "wide": True},
                      {"key": "guest", "label": "Guest", "kind": "combo", "values": list(people.values()), "wide": True},
                      {"key": "check_in", "label": "Check-in (YYYY-MM-DD)", "kind": "entry"},
                      {"key": "check_out", "label": "Check-out (YYYY-MM-DD)", "kind": "entry"},
                      {"key": "guests", "label": "Guests", "kind": "entry"},
                      {"key": "status", "label": "Status", "kind": "combo",
                       "values": ["pending", "confirmed", "cancelled"]}]
            if b:
                initial = {"place": places.get(b["listing_id"], ""), "guest": people.get(b["guest_id"], ""),
                           "check_in": b["check_in"], "check_out": b["check_out"], "guests": b["guests"],
                           "status": b["status"]}
            else:
                today = date.today()
                initial = {"check_in": date.fromordinal(today.toordinal() + 7).isoformat(),
                           "check_out": date.fromordinal(today.toordinal() + 10).isoformat(),
                           "guests": "2", "status": "confirmed"}

            def save(v):
                admin_save_booking(bid, self.pick_id(v["place"]), self.pick_id(v["guest"]), v["check_in"],
                                   v["check_out"], v["guests"], v["status"])
                return self.saved()
            open_form(ui, self, "Edit booking" if b else "Add booking", fields, initial, save,
                      "Save changes" if b else "Create booking",
                      "The total is worked out from the place's nightly price and the dates.")

        def delete_booking(self):
            bid = self.need(self.btree, "booking")
            if bid is None or not messagebox.askyesno(
                    "Delete booking", "Permanently delete this booking, with its payment record and review? "
                                      "To refund a guest, use Cancel booking instead.", parent=self):
                return
            try:
                admin_delete_booking(bid)
            except AppError as e:
                return messagebox.showerror("Delete booking", str(e), parent=self)
            self.changed()

        def fill_bookings(self):
            ui.clear(self.btree)
            want = self.filters["bookings"][1].get()
            self.rows_b = {b["id"]: b for b in admin_bookings()}
            for b in self.rows_b.values():
                ref = f"RR-{b['id']:05d}"
                if (want != "All" and b["status"] != want) or not self.match(
                        "bookings", ref, b["title"], b["guest_name"], b["host_name"]):
                    continue
                self.btree.insert("", "end", iid=str(b["id"]), tags=(b["status"],), values=(
                    ref, b["title"], b["guest_name"], b["host_name"], b["check_in"], b["check_out"],
                    ui.money(b["total_price"]), b["status"].capitalize()))

        def cancel_booking(self):
            bid = self.need(self.btree, "booking")
            if bid is None or not messagebox.askyesno(
                    "Cancel booking", "Cancel this booking as admin? The guest gets a full refund.", parent=self):
                return
            try:
                admin_cancel_booking(bid)
            except AppError as e:
                return messagebox.showerror("Admin", str(e), parent=self)
            self.changed()

        # ---------- reviews
        def build_reviews(self, f):
            bar = self.toolbar(f, "reviews", ["All", "Visible", "Hidden"], self.fill_reviews)
            self.rtree = self.table(
                f, [("title", "Place"), ("guest", "Guest"), ("stars", "Rating"), ("comment", "Comment"),
                    ("date", "Date"), ("state", "Status")],
                [170, 120, 90, 330, 100, 80], {"hidden": "#9A9080"})
            ui.button(bar, "Export CSV", lambda: self.export(self.rtree, "reviews"), False, small=True).pack(side="right")
            a = self.actions(f)
            ui.button(a, "Add review", lambda: self.review_form()).pack(side="left")
            ui.button(a, "Edit review", self.edit_review, False).pack(side="left", padx=(8, 0))
            ui.button(a, "Hide / Show", self.toggle_review, False).pack(side="left", padx=(8, 0))
            ui.button(a, "Read full review", self.read_review, False).pack(side="left", padx=(8, 0))
            ui.button(a, "Delete", self.delete_review, False).pack(side="left", padx=(8, 0))
            ui.L(a, "Hidden reviews don't count toward a listing's rating.", 9, fg=ui.MUTED).pack(side="left", padx=10)

        def edit_review(self):
            rid = self.need(self.rtree, "review")
            if rid is not None:
                self.review_form(rid)

        def review_form(self, rid=None):
            r = self.rows_r.get(rid) if rid else None
            if r:
                books = {r["booking_id"]: f"RR-{r['booking_id']:05d} · {r['title']} · {r['guest_name']}"}
            else:
                books = {b["id"]: f"RR-{b['id']:05d} · {b['title']} · {b['guest_name']}  (#{b['id']})"
                         for b in admin_bookings()
                         if b["status"] == "confirmed" and review_for_booking(b["id"]) is None}
                if not books:
                    return messagebox.showinfo("Admin", "Every confirmed booking already has a review.", parent=self)
            fields = [{"key": "booking", "label": "Booking", "kind": "combo", "values": list(books.values()),
                       "wide": True, "disabled": bool(r)},
                      {"key": "rating", "label": "Rating (1-5 stars)", "kind": "combo",
                       "values": ["5", "4", "3", "2", "1"]},
                      {"key": "state", "label": "Visibility", "kind": "combo", "values": ["Visible", "Hidden"]},
                      {"key": "comment", "label": "Comment", "kind": "text"}]
            if r:
                initial = {"booking": books[r["booking_id"]], "rating": str(r["rating"]),
                           "state": "Hidden" if r["hidden"] else "Visible", "comment": r["comment"] or ""}
            else:
                initial = {"rating": "5", "state": "Visible"}

            def save(v):
                admin_save_review(rid, None if r else self.pick_id(v["booking"]), v["rating"], v["comment"],
                                  v["state"] == "Hidden")
                return self.saved()
            open_form(ui, self, "Edit review" if r else "Add review", fields, initial, save,
                      "Save changes" if r else "Create review")

        def fill_reviews(self):
            ui.clear(self.rtree)
            want = self.filters["reviews"][1].get()
            self.rows_r = {r["id"]: r for r in all_reviews()}
            for r in self.rows_r.values():
                if (want == "Visible" and r["hidden"]) or (want == "Hidden" and not r["hidden"]) or \
                        not self.match("reviews", r["title"], r["guest_name"], r["comment"]):
                    continue
                text = (r["comment"] or "\u2014").replace("\n", " ")
                self.rtree.insert("", "end", iid=str(r["id"]), tags=("hidden" if r["hidden"] else "",), values=(
                    r["title"], r["guest_name"], stars_text(r["rating"]),
                    text if len(text) < 60 else text[:59] + "\u2026", r["created_at"][:10],
                    "Hidden" if r["hidden"] else "Visible"))

        def toggle_review(self):
            rid = self.need(self.rtree, "review")
            if rid is None:
                return
            try:
                set_review_hidden(rid, not self.rows_r[rid]["hidden"])
            except AppError as e:
                return messagebox.showerror("Admin", str(e), parent=self)
            self.changed()

        def read_review(self):
            rid = self.need(self.rtree, "review")
            if rid is None:
                return
            r = self.rows_r[rid]
            messagebox.showinfo(f"{r['guest_name']} on {r['title']}",
                                f"{stars_text(r['rating'])}   {r['created_at'][:10]}\n\n{r['comment'] or '(no comment)'}",
                                parent=self)

        def delete_review(self):
            rid = self.need(self.rtree, "review")
            if rid is None or not messagebox.askyesno(
                    "Delete review", "Delete this review permanently?", parent=self):
                return
            try:
                delete_review(rid)
            except AppError as e:
                return messagebox.showerror("Admin", str(e), parent=self)
            self.changed()

        # ---------- refresh everything
        def refresh(self):
            self.stamp.config(text=f"Updated {datetime.now():%b %d, %I:%M %p}".replace(" 0", " "))
            o = overview()
            self.render_overview(o)
            self.fill_listings()
            self.fill_users()
            self.fill_bookings()
            self.fill_reviews()
            p = o["pending_listings"]
            self.nb.tab(self.tabs["listings"], text=f"Listings ({p})" if p else "Listings")
            self.nb.tab(self.tabs["bookings"], text=f"Bookings ({o['pending']})" if o["pending"] else "Bookings")

    return AdminWindow


def make_review_dialog(ui):
    class ReviewDialog(tk.Toplevel):
        def __init__(self, app, trip, on_done=None):
            super().__init__(app.root)
            self.app, self.trip, self.on_done = app, trip, on_done
            self.existing = review_for_booking(trip["id"])
            self.rating = self.existing["rating"] if self.existing is not None else 0
            self.title("Review your stay")
            self.configure(bg=ui.PAPER, padx=30, pady=24)
            self.resizable(False, False)

            ui.L(self, "Review your stay", 18, "bold", family="Georgia").pack(anchor="w")
            ui.L(self, f"{trip['title']}  \u00B7  {trip['location']}", 10, fg=ui.MUTED).pack(anchor="w", pady=(2, 0))
            ui.L(self, ui.fmt_range(trip["check_in"], trip["check_out"]), 9, fg=ui.MUTED).pack(anchor="w")
            tk.Frame(self, bg=ui.LINE, height=1).pack(fill="x", pady=14)

            ui.L(self, "How was your stay?", 11, "bold").pack(anchor="w")
            row = tk.Frame(self, bg=ui.PAPER)
            row.pack(anchor="w", pady=(6, 0))
            self.stars = []
            for i in range(5):
                lb = tk.Label(row, text="\u2605", font=("Arial", 26), bg=ui.PAPER, cursor="hand2")
                lb.pack(side="left", padx=2)
                lb.bind("<Button-1>", lambda e, n=i + 1: self.pick(n))
                lb.bind("<Enter>", lambda e, n=i + 1: self.paint(n))
                lb.bind("<Leave>", lambda e: self.paint(self.rating))
                self.stars.append(lb)
            self.word = ui.L(row, "", 11, "bold", fg=ui.CLAY)
            self.word.pack(side="left", padx=(12, 0))
            self.paint(self.rating)

            ui.L(self, "Tell future guests about it (optional)", 11, "bold").pack(anchor="w", pady=(16, 4))
            self.text = tk.Text(self, width=56, height=6, wrap="word", font=("Arial", 10), relief="flat",
                                bg="white", fg=ui.INK, padx=8, pady=6, highlightthickness=1,
                                highlightbackground=ui.LINE, highlightcolor=ui.CLAY, insertbackground=ui.INK)
            self.text.pack(anchor="w")
            if self.existing is not None:
                self.text.insert("1.0", self.existing["comment"])
            self.count = ui.L(self, "", 8, fg=ui.MUTED)
            self.count.pack(anchor="e")
            self.text.bind("<KeyRelease>", lambda e: self.counter())
            self.counter()

            bar = tk.Frame(self, bg=ui.PAPER)
            bar.pack(anchor="w", pady=(10, 0))
            ui.button(bar, "Update review" if self.existing is not None else "Submit review", self.submit).pack(side="left")
            ui.button(bar, "Cancel", self.destroy, False).pack(side="left", padx=8)
            if self.existing is not None:
                ui.button(bar, "Delete my review", self.remove, False).pack(side="left")

        def paint(self, n):
            for i, lb in enumerate(self.stars):
                lb.config(fg=ui.CLAY if i < n else "#CDBF9F")
            self.word.config(text=STAR_WORDS[n - 1] if n else "Tap a star")

        def pick(self, n):
            self.rating = n
            self.paint(n)

        def counter(self):
            self.count.config(text=f"{len(self.text.get('1.0', 'end').strip())}/1000")

        def finish(self, msg):
            messagebox.showinfo("Reviews", msg, parent=self)
            self.destroy()
            self.app.run_search()
            if self.on_done:
                self.on_done()
            refresh_open_stay(self.app)

        def submit(self):
            if not self.rating:
                return messagebox.showinfo("Reviews", "Tap a star rating first.", parent=self)
            comment = self.text.get("1.0", "end")
            uid = self.app.user["id"]
            try:
                if self.existing is not None:
                    update_review(uid, self.existing["id"], self.rating, comment)
                    msg = "Your review was updated."
                else:
                    add_review(uid, self.trip["id"], self.rating, comment)
                    msg = "Thanks! Your review is now on the listing page."
            except AppError as e:
                return messagebox.showerror("Reviews", str(e), parent=self)
            self.finish(msg)

        def remove(self):
            if not messagebox.askyesno("Reviews", "Delete your review?", parent=self):
                return
            try:
                delete_review(self.existing["id"], self.app.user["id"])
            except AppError as e:
                return messagebox.showerror("Reviews", str(e), parent=self)
            self.finish("Your review was deleted.")

    return ReviewDialog


def refresh_open_stay(app):
    """Rebuild the listing page that is open right now, so a new, edited or deleted review shows at once
    (same window position and scroll position)."""
    page = app.child.get("stay")
    if page is None or not page.winfo_exists():
        return
    try:
        geo, lid = page.geometry(), page.r["id"]
        typed = (page.v_in.get(), page.v_out.get(), page.v_guests.get())
        frac = next(c for c in page.winfo_children() if isinstance(c, tk.Canvas)).yview()[0]
    except Exception:
        return
    app.open_stay(lid, typed)
    new = app.child.get("stay")
    if new is None or not new.winfo_exists():
        return
    new.geometry(geo)

    def restore():
        try:
            next(c for c in new.winfo_children() if isinstance(c, tk.Canvas)).yview_moveto(frac)
        except Exception:
            pass

    new.after(150, restore)


def make_reviews_section(ui):
    def reviews_section(parent, listing_id):
        """The 'Guest reviews' block on a listing page: the reviews, plus a way for a guest who stayed
        here to write (or edit) theirs right on this page."""
        bg = parent.cget("bg")
        page = parent.winfo_toplevel()
        app = getattr(page, "app", None)
        user = getattr(app, "user", None) if app is not None else None
        rows = listing_reviews(listing_id)
        today = date.today().isoformat()

        trips = []
        if user:
            trips = [t for t in db.guest_bookings(user["id"])
                     if t["listing_id"] == listing_id and t["status"] == "confirmed"]
        done = sorted((t for t in trips if t["check_out"] <= today), key=lambda t: t["check_out"], reverse=True)
        upcoming = sorted((t for t in trips if t["check_out"] > today), key=lambda t: t["check_out"])
        trip_of = {t["id"]: t for t in done}
        to_review = next((t for t in done if review_for_booking(t["id"]) is None), None)

        def open_dialog(trip):
            ui.ReviewDialog(app, trip)  # its finish() refreshes this page

        tk.Frame(parent, bg=ui.LINE, height=1).pack(fill="x", pady=18)
        top = tk.Frame(parent, bg=bg)
        top.pack(fill="x")
        ui.L(top, "Guest reviews", 14, "bold", bg=bg).pack(side="left")
        if rows:
            avg = sum(r["rating"] for r in rows) / len(rows)
            ui.L(top, f"   \u2605 {avg:.2f}  \u00B7  {len(rows)} written review{'s' if len(rows) != 1 else ''}",
                 10, fg=ui.MUTED, bg=bg).pack(side="left")
        ui.L(parent, "Every review comes from a guest who completed a stay here.", 9, fg=ui.MUTED, bg=bg).pack(
            anchor="w", pady=(4, 0))

        # ---- write-a-review prompt (only what applies to the person looking at the page)
        cta = tk.Frame(parent, bg=ui.PAPER2, highlightbackground=ui.LINE, highlightthickness=1, padx=16, pady=14)
        cta.pack(fill="x", pady=(14, 0))
        text = tk.Frame(cta, bg=ui.PAPER2)
        text.pack(side="left", fill="x", expand=True)
        if to_review is not None:
            ui.L(text, f"You stayed here {ui.fmt_range(to_review['check_in'], to_review['check_out'])}", 10, "bold",
                 bg=ui.PAPER2).pack(anchor="w")
            ui.L(text, "How was it? Your review helps future guests.", 9, fg=ui.MUTED, bg=ui.PAPER2).pack(
                anchor="w", pady=(2, 0))
            ui.button(cta, "Write a review", lambda t=to_review: open_dialog(t)).pack(side="right")
        else:
            if upcoming:
                msg = f"You can review your stay after check-out on {ui.fmt_day(upcoming[0]['check_out'])}."
            elif done:
                msg = "Thanks for reviewing your stay. You can edit your review below."
            elif user:
                msg = "Only guests who completed a stay here can leave a review."
            else:
                msg = "Log in and complete a stay here to leave a review."
            ui.L(text, msg, 10, fg=ui.MUTED, bg=ui.PAPER2).pack(anchor="w")

        if not rows:
            ui.L(parent, "No written reviews yet. Be the first once your stay is over.", 10, slant="italic",
                 family="Georgia", fg=ui.MUTED, bg=bg).pack(anchor="w", pady=(14, 0))
            return

        # ---- the reviews
        box = tk.Frame(parent, bg=bg)
        box.pack(fill="x")
        state = {"all": False}
        btn = tk.Button(parent, relief="flat", bg=ui.LINE, fg=ui.INK, font=("Arial", 10, "bold"),
                        padx=14, pady=6, cursor="hand2")

        def draw():
            for w in box.winfo_children():
                w.destroy()
            for r in (rows if state["all"] else rows[:3]):
                mine = bool(user) and r["guest_id"] == user["id"]
                card = tk.Frame(box, bg=bg, highlightbackground=ui.LINE, highlightthickness=1, padx=14, pady=12)
                card.pack(fill="x", pady=(10, 0))
                head = tk.Frame(card, bg=bg)
                head.pack(fill="x")
                name = r["guest_name"] or "Guest"
                av = tk.Canvas(head, width=34, height=34, bg=bg, highlightthickness=0)
                av.pack(side="left")
                av.create_oval(1, 1, 33, 33, fill=PALETTE[sum(map(ord, name)) % len(PALETTE)], outline="")
                av.create_text(17, 18, text=name[:1].upper(), fill="white", font=("Arial", 12, "bold"))
                who = tk.Frame(head, bg=bg)
                who.pack(side="left", padx=10)
                ui.L(who, name + ("  (you)" if mine else ""), 10, "bold", bg=bg).pack(anchor="w")
                ui.L(who, ui.fmt_day(r["created_at"][:10]), 8, fg=ui.MUTED, bg=bg).pack(anchor="w")
                ui.L(head, stars_text(r["rating"]), 11, fg=ui.CLAY, bg=bg).pack(side="right")
                if r["comment"]:
                    ui.L(card, r["comment"], 10, wraplength=520, justify="left", bg=bg).pack(anchor="w", pady=(8, 0))
                if mine and r["booking_id"] in trip_of:
                    link = tk.Label(card, text="Edit your review", fg=ui.CLAY, bg=bg, cursor="hand2",
                                    font=("Arial", 9, "bold"))
                    link.pack(anchor="w", pady=(8, 0))
                    link.bind("<Button-1>", lambda e, t=trip_of[r["booking_id"]]: open_dialog(t))
            if len(rows) > 3:
                btn.config(text="Show fewer" if state["all"] else f"Show all {len(rows)} reviews")

        def toggle():
            state["all"] = not state["all"]
            draw()

        btn.config(command=toggle)
        draw()
        if len(rows) > 3:
            btn.pack(anchor="w", pady=(14, 0))

    return reviews_section


def install(ns):
    """Called from app.py with globals(): swaps in the new admin dashboard and adds the review screens."""
    ui = _UI(ns)
    ns["AdminWindow"] = make_admin(ui)
    ns["ReviewDialog"] = make_review_dialog(ui)
    ns["reviews_section"] = make_reviews_section(ui)
    ns["review_for_booking"] = review_for_booking
    ns["CANCELLED_BY"]["admin"] = "RoamRest admin"