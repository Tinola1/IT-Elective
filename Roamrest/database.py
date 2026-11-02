"""RoamRest data layer: SQLite storage + business rules. No GUI code in here."""
import hashlib
import hmac
import math
import os
import re
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import date, datetime, time, timedelta

DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "roamrest.db")
DATE_FMT = "%Y-%m-%d"
PENDING_HOURS = 24  # how long a host has to answer a reservation request

# Fixed demo exchange rate (NOT live). Change this number to update the peso prices.
PHP_PER_USD = 58.0
# code -> (symbol, units per US dollar, label). Prices are always stored in US dollars.
CURRENCIES = {"USD": ("$", 1.0, "US dollar ($)"),
              "PHP": ("\u20B1", PHP_PER_USD, "Philippine peso (\u20B1)")}

CATEGORIES = ["Cabins & lodges", "City lofts", "Unique stays",
              "Beachfront", "Villas & pools", "Countryside"]
# category name -> id used by the landing page
CAT_IDS = {"Cabins & lodges": "cabins", "Beachfront": "beach", "City lofts": "lofts",
           "Villas & pools": "villas", "Countryside": "country", "Unique stays": "unique"}

ADMIN_EMAIL, ADMIN_PASSWORD = "admin@roamrest.com", "admin123"
DEMO_HOST_EMAIL, DEMO_HOST_PASSWORD = "host@roamrest.com", "host123"
DEMO_GUEST_EMAIL, DEMO_GUEST_PASSWORD = "guest@roamrest.com", "guest123"

# What a guest must have on their profile before they can book.
REQUIRED_PROFILE = [("phone", "Phone number"), ("address", "Street address"), ("city", "City"),
                    ("country", "Country"), ("birthdate", "Date of birth")]

# =============================================================== payments (escrow-style, simulated)
# Nothing here moves real money: it models how Airbnb-style payments work. Full card numbers and CVVs are
# validated and then thrown away; only the brand, last 4 digits and expiry are stored.
HOST_FEE_RATE = 0.03        # the flat 3% host service fee
PAYOUT_DELAY_HOURS = 24     # the host is paid about 24 hours after check-in
LONG_STAY_NIGHTS = 28       # stays this long are paid out in monthly instalments
SPLIT_MIN_DAYS = 14         # a payment plan's 2nd part is charged this many days before check-in
SPLIT_MIN_LEAD = 15         # ...so a plan is only offered if check-in is at least this many days away
CHECK_IN_HOUR = 15

PAYMENT_KINDS = [("card", "Credit or debit card"), ("paypal", "PayPal"), ("apple_pay", "Apple Pay"),
                 ("google_pay", "Google Pay"), ("gcash", "GCash"), ("maya", "Maya")]
KIND_NAMES = dict(PAYMENT_KINDS)
REFUND_ETA = {"card": "5\u201310 business days", "paypal": "1\u20133 business days",
              "apple_pay": "5\u201310 business days", "google_pay": "5\u201310 business days",
              "gcash": "within 24 hours", "maya": "within 24 hours"}

# kind -> (name, how long a payout takes, what the detail field asks for)
PAYOUT_KINDS = {"bank": ("Bank transfer (ACH)", "1\u20133 business days", "Account number"),
                "paypal": ("PayPal", "within a few hours", "PayPal email"),
                "fast_pay": ("Fast Pay (instant, debit card)", "instantly", "Debit card number"),
                "payoneer": ("Payoneer", "1\u20132 business days", "Payoneer email"),
                "wire": ("International wire transfer", "3\u20135 business days", "IBAN / account number"),
                "gcash": ("GCash", "instantly", "GCash mobile number")}

POLICIES = ("Flexible", "Moderate", "Strict")
DEFAULT_POLICY = "Moderate"
POLICY_TEXT = {
    "Flexible": "Full refund until 24 hours before check-in. After that, 50% back.",
    "Moderate": "Full refund until 5 days before check-in. After that, 50% back.",
    "Strict": "Full refund within 48 hours of booking if check-in is 14+ days away. 50% back until 7 days "
              "before check-in. No refund after that."}

PAYMENT_SCHEMA = """
CREATE TABLE IF NOT EXISTS payment_methods (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    kind TEXT NOT NULL,
    brand TEXT DEFAULT '',
    last4 TEXT DEFAULT '',
    exp_month INTEGER,
    exp_year INTEGER,
    holder TEXT DEFAULT '',
    detail TEXT DEFAULT '',
    is_default INTEGER NOT NULL DEFAULT 0,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS payments (
    booking_id INTEGER PRIMARY KEY REFERENCES bookings(id),
    user_id INTEGER NOT NULL REFERENCES users(id),
    method_id INTEGER,
    method_kind TEXT DEFAULT '',
    method_label TEXT DEFAULT '',
    plan TEXT NOT NULL DEFAULT 'full',
    amount REAL NOT NULL,
    created_at TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS payout_methods (
    host_id INTEGER PRIMARY KEY REFERENCES users(id),
    kind TEXT NOT NULL,
    holder TEXT DEFAULT '',
    detail TEXT DEFAULT '',
    label TEXT DEFAULT '',
    created_at TEXT DEFAULT ''
);
"""

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    salt TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'guest' CHECK(role IN ('guest','host','admin')),
    active INTEGER NOT NULL DEFAULT 1,
    phone TEXT DEFAULT '',
    address TEXT DEFAULT '',
    city TEXT DEFAULT '',
    country TEXT DEFAULT '',
    birthdate TEXT DEFAULT '',
    emergency_name TEXT DEFAULT '',
    emergency_phone TEXT DEFAULT '',
    avatar TEXT DEFAULT '',
    currency TEXT NOT NULL DEFAULT 'USD'
);
CREATE TABLE IF NOT EXISTS listings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    host_id INTEGER NOT NULL REFERENCES users(id),
    title TEXT NOT NULL,
    category TEXT NOT NULL,
    location TEXT NOT NULL,
    price_per_night REAL NOT NULL,
    max_guests INTEGER NOT NULL,
    description TEXT DEFAULT '',
    blurb TEXT DEFAULT '',
    amenities TEXT DEFAULT '',
    rating REAL,
    review_count INTEGER NOT NULL DEFAULT 0,
    image_seed TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','approved','rejected')),
    active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS bookings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id INTEGER NOT NULL REFERENCES listings(id),
    guest_id INTEGER NOT NULL REFERENCES users(id),
    check_in TEXT NOT NULL,
    check_out TEXT NOT NULL,
    guests INTEGER NOT NULL,
    total_price REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT DEFAULT '',
    cancel_reason TEXT DEFAULT '',
    cancelled_by TEXT DEFAULT '',
    cancelled_at TEXT DEFAULT '',
    refund REAL NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS favorites (
    user_id INTEGER NOT NULL REFERENCES users(id),
    listing_id INTEGER NOT NULL REFERENCES listings(id),
    PRIMARY KEY (user_id, listing_id)
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id INTEGER NOT NULL REFERENCES listings(id),
    guest_id INTEGER NOT NULL REFERENCES users(id),
    sender_id INTEGER NOT NULL REFERENCES users(id),
    body TEXT NOT NULL,
    created_at TEXT NOT NULL,
    is_read INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS listing_photos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id INTEGER NOT NULL REFERENCES listings(id),
    filename TEXT NOT NULL,
    caption TEXT DEFAULT '',
    position INTEGER NOT NULL DEFAULT 0
);
"""

# title, category, location, price, max guests, rating, reviews, image seed, blurb, description, amenities
SEED_STAYS = [
    ("Cedar & Pine Cabin", "Cabins & lodges", "Estes Park, Colorado, USA", 124, 6, 4.97, 312, "stay-cedar",
     "Hot tub under the stars",
     "A hand-built cedar cabin on 12 forested acres at the edge of Rocky Mountain National Park. Wood stove, cedar hot tub, and a deck built for meteor showers.",
     "Wi-Fi 300 Mbps,Full kitchen,Wood fireplace,Hot tub"),
    ("Alfama Skyline Loft", "City lofts", "Lisbon, Portugal", 86, 3, 4.92, 541, "stay-alfama",
     "Rooftop tiles & tram bells",
     "Top-floor loft in a 19th-century building, two tiled balconies over the Alfama rooftops. Tram 28 at the door, pastelarias everywhere.",
     "Wi-Fi 500 Mbps,Full kitchen,Dedicated workspace,Washer"),
    ("Machiya House", "Unique stays", "Kyoto, Japan", 138, 4, 4.98, 264, "stay-machiya",
     "Tatami rooms, soaking tub",
     "A restored 90-year-old townhouse with tatami rooms, a courtyard garden and a hinoki soaking tub. Record player and a shelf of vinyl included.",
     "Wi-Fi 200 Mbps,Kitchen,Hinoki soaking tub,Workspace"),
    ("Casa Azul", "Beachfront", "Sayulita, Mexico", 102, 4, 4.89, 487, "stay-azul",
     "90 seconds to the sand",
     "A blue-washed casita a 90-second walk from the beach. Hammocks, an outdoor kitchen and the best coffee in town right next door.",
     "Wi-Fi,Outdoor kitchen,A/C,Surfboards"),
    ("Canal Boathouse", "Unique stays", "Utrecht, Netherlands", 118, 2, 4.90, 203, "stay-boat",
     "Life on the water",
     "A 1930s houseboat on a quiet canal, renovated last year. King bed in the bow, breakfast on the deck, swans as neighbours.",
     "Wi-Fi 400 Mbps,Kitchen,Heating,Two bikes included"),
    ("Olive Grove Villa", "Villas & pools", "Puglia, Italy", 186, 8, 4.95, 178, "stay-puglia",
     "A pool among the olive trees",
     "A trulli-inspired villa among 200 olive trees. Private pool, wood oven, and long tables for even longer dinners. Sleeps 8.",
     "Private pool,Full kitchen,Outdoor pizza oven,A/C"),
    ("Blue Hour Loft", "City lofts", "Copenhagen, Denmark", 96, 3, 4.87, 355, "stay-cph",
     "A cook's kitchen, harbor swims",
     "Architect-owned loft in Islands Brygge with a kitchen you'll actually cook in. Harbor swims 200m away, bakery closer.",
     "Wi-Fi 1 Gbps,Chef's kitchen,Dedicated workspace,Washer"),
    ("Farmhouse at Willowbrook", "Countryside", "Cotswolds, England, UK", 92, 5, 4.94, 167, "stay-cotswolds",
     "Aga warmth, farm-fresh eggs",
     "A honey-stone farmhouse on a working sheep farm. Aga stove, muddy boots by the door, breakfast eggs collected that morning.",
     "Full kitchen,Fireplace,Garden,Pets welcome"),
    ("Driftwood Cabana", "Beachfront", "Santa Teresa, Costa Rica", 79, 2, 4.91, 428, "stay-cabana",
     "Surf out front, sloths overhead",
     "Open-air cabana in the jungle, five minutes' walk from the break. Surf out front, sloths overhead, yoga deck upstairs.",
     "Outdoor shower,Kitchenette,Surfboard racks,Breakfast included"),
    ("Treetop Nest", "Unique stays", "Orcas Island, Washington, USA", 115, 2, 4.96, 158, "stay-treetop",
     "14 feet up a fir tree",
     "A cedar-and-glass treehouse 14 feet up a Douglas fir, with a suspended bridge entrance and a wood stove for foggy mornings.",
     "Wood stove,Kitchenette,Canopy deck,Stargazing kit"),
    ("Vineyard Cottage", "Countryside", "Mendoza, Argentina", 74, 4, 4.90, 219, "stay-mendoza",
     "The Andes out the window",
     "A whitewashed cottage set between vineyard rows, Andes out the window. Malbec in the fridge, horses in the next field.",
     "Wood fireplace,Kitchen,Wine cellar tours,Horses on-site"),
    ("Emberlight A-frame", "Cabins & lodges", "Whistler, Canada", 132, 4, 4.93, 241, "stay-aframe",
     "Sauna after the powder",
     "A black A-frame at the forest's edge, ten minutes from the lifts. Sauna on the deck, ski storage below, cocoa always on.",
     "Sauna,Kitchenette,Ski-in access,Fireplace"),
    ("Casa Palma", "Villas & pools", "Tulum, Mexico", 158, 8, 4.88, 263, "stay-palma",
     "Palm walls, plunge pool",
     "A four-suite villa behind a palm wall: plunge pool, open-air living room, cenote day trips arranged from the sofa.",
     "Plunge pool,Full kitchen,Chef on request,A/C"),
    ("The Print Room", "City lofts", "Barcelona, Spain", 89, 3, 4.91, 304, "stay-print",
     "Letterpress & a plaça balcony",
     "A printmaker's studio turned loft in Gràcia: high ceilings, letterpress on the wall, and a balcony over the plaça.",
     "Wi-Fi 500 Mbps,Full kitchen,Dedicated workspace,Balcony"),
]


class AppError(Exception):
    """A problem the user should see (bad input, rule broken)."""


@contextmanager
def session():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        with conn:  # commit on success, rollback on error
            yield conn
    finally:
        conn.close()


# ---------------------------------------------------------------- setup
def _migrate(c):
    """Add columns that older copies of roamrest.db don't have yet."""
    wanted = {
        "listings": (("cancellation_policy", "TEXT NOT NULL DEFAULT 'Moderate'"),
                     ("blurb", "TEXT DEFAULT ''"),
                     ("amenities", "TEXT DEFAULT ''"),
                     ("review_count", "INTEGER NOT NULL DEFAULT 0")),
        "users": (("phone", "TEXT DEFAULT ''"), ("address", "TEXT DEFAULT ''"),
                  ("city", "TEXT DEFAULT ''"), ("country", "TEXT DEFAULT ''"),
                  ("birthdate", "TEXT DEFAULT ''"), ("emergency_name", "TEXT DEFAULT ''"),
                  ("emergency_phone", "TEXT DEFAULT ''"), ("avatar", "TEXT DEFAULT ''"),
                  ("currency", "TEXT NOT NULL DEFAULT 'USD'"),
                  # 'none' | 'pending' | 'rejected' | 'approved' - a guest needs admin approval to become a host
                  ("host_status", "TEXT NOT NULL DEFAULT 'none'")),
        "bookings": (("confirmed_at", "TEXT DEFAULT ''"), ("policy", "TEXT DEFAULT ''"),
                     ("created_at", "TEXT DEFAULT ''"), ("cancel_reason", "TEXT DEFAULT ''"),
                     ("cancelled_by", "TEXT DEFAULT ''"), ("cancelled_at", "TEXT DEFAULT ''"),
                     ("refund", "REAL NOT NULL DEFAULT 0"),
                     # 0 = the host confirmed this booking and the guest has not looked at it yet (red badge).
                     # Everything that already exists, and every new request, starts as 1 (nothing to announce).
                     ("guest_seen", "INTEGER NOT NULL DEFAULT 1")),
    }
    for table, columns in wanted.items():
        have = {r["name"] for r in c.execute(f"PRAGMA table_info({table})")}
        for name, ddl in columns:
            if name not in have:
                c.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")


def init_db():
    with session() as c:
        c.executescript(SCHEMA)
        c.executescript(PAYMENT_SCHEMA)
        _migrate(c)
        expire_pending(c)
        _ensure_user(c, "Admin", ADMIN_EMAIL, ADMIN_PASSWORD, "admin")
        demo_guest = _ensure_user(c, "Demo Guest", DEMO_GUEST_EMAIL, DEMO_GUEST_PASSWORD, "guest")
        if not c.execute("SELECT 1 FROM payment_methods WHERE user_id=?", (demo_guest,)).fetchone():
            c.execute("INSERT INTO payment_methods (user_id,kind,brand,last4,exp_month,exp_year,holder,"
                      "is_default,created_at) VALUES (?,?,?,?,?,?,?,1,?)",
                      (demo_guest, "card", "Visa", "4242", 12, date.today().year + 3, "Demo Guest", _now()))
        host_id = _ensure_user(c, "Demo Host", DEMO_HOST_EMAIL, DEMO_HOST_PASSWORD, "host")
        if not c.execute("SELECT 1 FROM listings").fetchone():
            for t, cat, loc, price, guests, rating, reviews, seed, blurb, desc, amen in SEED_STAYS:
                c.execute(
                    "INSERT INTO listings (host_id,title,category,location,price_per_night,max_guests,"
                    "description,rating,review_count,image_seed,blurb,amenities,status)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,'approved')",
                    (host_id, t, cat, loc, price, guests, desc, rating, reviews, seed, blurb, amen))


# ---------------------------------------------------------------- helpers
def _hash(password, salt):
    return hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 100_000).hex()


def _insert_user(c, name, email, password, role):
    salt = os.urandom(16).hex()
    cur = c.execute("INSERT INTO users (name,email,password_hash,salt,role) VALUES (?,?,?,?,?)",
                    (name, email, _hash(password, salt), salt, role))
    return cur.lastrowid


def _ensure_user(c, name, email, password, role):
    row = c.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
    return row["id"] if row else _insert_user(c, name, email, password, role)


def parse_date(text):
    try:
        return datetime.strptime(str(text).strip(), DATE_FMT).date()
    except ValueError:
        raise AppError(f"'{text}' is not a valid date. Use YYYY-MM-DD.")


def _now():
    return datetime.now().isoformat(timespec="seconds")


def _parse_ts(text):
    try:
        return datetime.fromisoformat(text)
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------- users
def register_user(name, email, password, wants_host=False):
    """New accounts always start as guests. Ticking 'I want to host' only files a host request
    that an admin has to approve."""
    name, email = name.strip(), email.strip().lower()
    if not name or "@" not in email:
        raise AppError("Please enter a name and a valid email.")
    if len(password) < 6:
        raise AppError("Password must be at least 6 characters.")
    try:
        with session() as c:
            uid = _insert_user(c, name, email, password, "guest")
            if wants_host:
                c.execute("UPDATE users SET host_status='pending' WHERE id=?", (uid,))
    except sqlite3.IntegrityError:
        raise AppError("An account with that email already exists.")


def login(email, password):
    with session() as c:
        row = c.execute("SELECT * FROM users WHERE email=?", (email.strip().lower(),)).fetchone()
    if row is None or not hmac.compare_digest(_hash(password, row["salt"]), row["password_hash"]):
        raise AppError("Invalid email or password.")
    if not row["active"]:
        raise AppError("This account has been deactivated. Contact an admin.")
    return dict(row)


def get_user(user_id):
    with session() as c:
        row = c.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    return dict(row) if row else None


# ---- host requests: a guest asks, an admin decides
def become_host(user_id):
    """A guest asks to become a host. The role does NOT change here: it stays 'guest' until an admin
    approves the request (approve_host_request)."""
    with session() as c:
        u = c.execute("SELECT role, host_status FROM users WHERE id=?", (user_id,)).fetchone()
        if u is None:
            raise AppError("Account not found.")
        if u["role"] != "guest":
            raise AppError("Only guest accounts can ask to become a host.")
        if u["host_status"] == "pending":
            raise AppError("Your host request is already waiting for admin approval.")
        c.execute("UPDATE users SET host_status='pending' WHERE id=?", (user_id,))


def host_requests():
    """Guests waiting for an admin to approve them as a host."""
    with session() as c:
        return c.execute("SELECT * FROM users WHERE role='guest' AND host_status='pending' AND active=1"
                         " ORDER BY id").fetchall()


def approve_host_request(user_id):
    with session() as c:
        u = c.execute("SELECT role, host_status FROM users WHERE id=?", (user_id,)).fetchone()
        if u is None or u["role"] != "guest" or u["host_status"] != "pending":
            raise AppError("That user has no pending host request.")
        c.execute("UPDATE users SET role='host', host_status='approved' WHERE id=?", (user_id,))


def reject_host_request(user_id):
    with session() as c:
        u = c.execute("SELECT role, host_status FROM users WHERE id=?", (user_id,)).fetchone()
        if u is None or u["role"] != "guest" or u["host_status"] != "pending":
            raise AppError("That user has no pending host request.")
        c.execute("UPDATE users SET host_status='rejected' WHERE id=?", (user_id,))


def set_currency(user_id, code):
    if code not in CURRENCIES:
        raise AppError("Unknown currency.")
    with session() as c:
        c.execute("UPDATE users SET currency=? WHERE id=?", (code, user_id))


def all_users():
    with session() as c:
        return c.execute("SELECT * FROM users ORDER BY id").fetchall()


def _editable_user(c, user_id):
    row = c.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    if row is None:
        raise AppError("User not found.")
    if row["role"] == "admin":
        raise AppError("Admin accounts can't be changed from here.")


def set_role(user_id, role):
    if role not in ("guest", "host"):
        raise AppError("Role must be guest or host.")
    with session() as c:
        _editable_user(c, user_id)
        c.execute("UPDATE users SET role=?, host_status=? WHERE id=?",
                  (role, "approved" if role == "host" else "none", user_id))


def set_user_active(user_id, active):
    with session() as c:
        _editable_user(c, user_id)
        c.execute("UPDATE users SET active=? WHERE id=?", (int(active), user_id))


# ---------------------------------------------------------------- profile
def profile_missing(user):
    """Labels of the required profile fields that are still empty. `user` is a dict."""
    return [label for key, label in REQUIRED_PROFILE if not str(user.get(key) or "").strip()]


def _check_phone(text, label):
    text = text.strip()
    digits = re.sub(r"\D", "", text)
    if not re.fullmatch(r"[0-9+\-\s()]+", text) or not 7 <= len(digits) <= 15:
        raise AppError(f"{label} doesn't look right. Use digits, e.g. +63 917 123 4567.")


def update_profile(user_id, name, phone, address, city, country, birthdate,
                   emergency_name="", emergency_phone=""):
    vals = {"name": name.strip(), "phone": phone.strip(), "address": address.strip(),
            "city": city.strip(), "country": country.strip(), "birthdate": birthdate.strip(),
            "emergency_name": emergency_name.strip(), "emergency_phone": emergency_phone.strip()}
    if not vals["name"]:
        raise AppError("Please enter your full name.")
    missing = profile_missing(vals)
    if missing:
        raise AppError("Please fill in: " + ", ".join(missing) + ".")
    _check_phone(vals["phone"], "Phone number")
    if vals["emergency_phone"]:
        _check_phone(vals["emergency_phone"], "Emergency contact phone")
    born = parse_date(vals["birthdate"])
    today = date.today()
    age = today.year - born.year - ((today.month, today.day) < (born.month, born.day))
    if age < 18:
        raise AppError("You must be at least 18 to book a stay.")
    if age > 120:
        raise AppError("Please check your date of birth.")
    with session() as c:
        c.execute(
            "UPDATE users SET name=?, phone=?, address=?, city=?, country=?, birthdate=?,"
            " emergency_name=?, emergency_phone=? WHERE id=?",
            (vals["name"], vals["phone"], vals["address"], vals["city"], vals["country"],
             vals["birthdate"], vals["emergency_name"], vals["emergency_phone"], user_id))


def set_avatar(user_id, filename):
    with session() as c:
        c.execute("UPDATE users SET avatar=? WHERE id=?", (filename, user_id))


def change_password(user_id, old_password, new_password):
    if len(new_password) < 6:
        raise AppError("New password must be at least 6 characters.")
    with session() as c:
        row = c.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        if row is None or not hmac.compare_digest(_hash(old_password, row["salt"]), row["password_hash"]):
            raise AppError("Your current password is wrong.")
        salt = os.urandom(16).hex()
        c.execute("UPDATE users SET password_hash=?, salt=? WHERE id=?",
                  (_hash(new_password, salt), salt, user_id))


# ---------------------------------------------------------------- listings
MAX_NIGHTLY_PRICE = 10_000  # US dollars per night


def _image_seed(title):
    """Stock-photo seed for a new listing: title slug plus a random suffix, so two listings with the
    same title (or titles made only of symbols) never share one picture."""
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return "rr-" + (slug + "-" if slug else "") + uuid.uuid4().hex[:6]


def _validate_listing(title, category, location, price, max_guests):
    if not title.strip() or not location.strip():
        raise AppError("Title and location are required.")
    if category not in CATEGORIES:
        raise AppError("Please choose a category.")
    try:
        price = float(str(price).strip().replace("$", "").replace("\u20B1", "").replace(",", ""))
        max_guests = int(str(max_guests).strip())
    except ValueError:
        raise AppError("Price must be a number and max guests a whole number.")
    if not math.isfinite(price):
        raise AppError("Price must be a real number.")
    if price <= 0 or max_guests < 1:
        raise AppError("Price must be above 0 and guests at least 1.")
    if price > MAX_NIGHTLY_PRICE:
        raise AppError(f"Price can be at most ${MAX_NIGHTLY_PRICE:,} a night.")
    return price, max_guests


def _blurb(description):
    first = re.split(r"[.!?\n]", description.strip())[0].strip()
    if not first:
        return "New on RoamRest"
    return first[:48] + "…" if len(first) > 48 else first


def _amenities(text):
    return ",".join(a.strip() for a in text.split(",") if a.strip())


def _check_policy(policy):
    if policy not in POLICIES:
        raise AppError("Choose a cancellation policy.")
    return policy


def add_listing(host_id, title, category, location, price, max_guests, description, amenities="",
                cancellation_policy=DEFAULT_POLICY):
    """`price` is in US dollars (the app converts from the host's currency)."""
    price, max_guests = _validate_listing(title, category, location, price, max_guests)
    _check_policy(cancellation_policy)
    seed = _image_seed(title)
    with session() as c:
        cur = c.execute(
            "INSERT INTO listings (host_id,title,category,location,price_per_night,max_guests,"
            "description,blurb,amenities,image_seed,cancellation_policy) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (host_id, title.strip(), category, location.strip(), price, max_guests,
             description.strip(), _blurb(description), _amenities(amenities), seed, cancellation_policy))
        return cur.lastrowid


def update_listing(listing_id, host_id, title, category, location, price, max_guests,
                   description, amenities="", cancellation_policy=None):
    """cancellation_policy=None keeps whatever policy the listing already has."""
    price, max_guests = _validate_listing(title, category, location, price, max_guests)
    if cancellation_policy is not None:
        _check_policy(cancellation_policy)
    with session() as c:
        cur = c.execute(
            "UPDATE listings SET title=?, category=?, location=?, price_per_night=?, max_guests=?,"
            " description=?, blurb=?, amenities=?, cancellation_policy=COALESCE(?, cancellation_policy)"
            " WHERE id=? AND host_id=?",
            (title.strip(), category, location.strip(), price, max_guests,
             description.strip(), _blurb(description), _amenities(amenities), cancellation_policy,
             listing_id, host_id))
        if cur.rowcount == 0:
            raise AppError("Listing not found.")


def delete_listing(listing_id, host_id=None):
    """Soft delete so past bookings keep their history. host_id=None means admin.
    The listing's photo rows are removed; returns their file names so the caller can delete the files."""
    with session() as c:
        sql, params = "SELECT * FROM listings WHERE id=?", [listing_id]
        if host_id is not None:
            sql += " AND host_id=?"
            params.append(host_id)
        if c.execute(sql, params).fetchone() is None:
            raise AppError("Listing not found.")
        expire_pending(c)
        upcoming = c.execute(
            "SELECT COUNT(*) FROM bookings WHERE listing_id=? AND status IN ('confirmed','pending')"
            " AND check_out >= ?",
            (listing_id, date.today().isoformat())).fetchone()[0]
        if upcoming:
            raise AppError("This listing has upcoming bookings or requests and can't be removed yet.")
        names = [r["filename"] for r in c.execute(
            "SELECT filename FROM listing_photos WHERE listing_id=?", (listing_id,))]
        c.execute("DELETE FROM listing_photos WHERE listing_id=?", (listing_id,))
        c.execute("UPDATE listings SET active=0 WHERE id=?", (listing_id,))
        return names


def host_listings(host_id):
    with session() as c:
        return c.execute("SELECT * FROM listings WHERE host_id=? AND active=1 ORDER BY id DESC",
                         (host_id,)).fetchall()


# ---------------------------------------------------------------- listing photos
MAX_PHOTOS = 20  # per listing


def _photo_order(c, listing_id):
    return [r[0] for r in c.execute(
        "SELECT id FROM listing_photos WHERE listing_id=? ORDER BY position, id", (listing_id,))]


def _renumber(c, ids):
    for pos, pid in enumerate(ids):
        c.execute("UPDATE listing_photos SET position=? WHERE id=?", (pos, pid))


def _own_photo(c, photo_id, host_id):
    """The photo row, if it belongs to one of this host's listings (host_id=None means admin)."""
    sql = ("SELECT p.* FROM listing_photos p JOIN listings l ON l.id=p.listing_id WHERE p.id=?")
    params = [photo_id]
    if host_id is not None:
        sql += " AND l.host_id=?"
        params.append(host_id)
    row = c.execute(sql, params).fetchone()
    if row is None:
        raise AppError("Photo not found.")
    return row


def listing_photos(listing_id):
    """All photo rows of a listing, cover first."""
    with session() as c:
        return c.execute("SELECT * FROM listing_photos WHERE listing_id=? ORDER BY position, id",
                         (listing_id,)).fetchall()


def photo_files(listing_id):
    """Just the file names, cover first (empty list if the host hasn't added any)."""
    return [r["filename"] for r in listing_photos(listing_id)]


def photo_counts(host_id):
    """{listing_id: number of photos} for all of a host's listings."""
    with session() as c:
        rows = c.execute(
            "SELECT p.listing_id, COUNT(*) FROM listing_photos p JOIN listings l ON l.id=p.listing_id"
            " WHERE l.host_id=? GROUP BY p.listing_id", (host_id,)).fetchall()
    return {r[0]: r[1] for r in rows}


def add_listing_photo(listing_id, host_id, filename, caption=""):
    """Adds a photo at the end of the listing's gallery. Returns the new photo id."""
    with session() as c:
        if c.execute("SELECT 1 FROM listings WHERE id=? AND host_id=? AND active=1",
                     (listing_id, host_id)).fetchone() is None:
            raise AppError("Listing not found.")
        n = c.execute("SELECT COUNT(*) FROM listing_photos WHERE listing_id=?",
                      (listing_id,)).fetchone()[0]
        if n >= MAX_PHOTOS:
            raise AppError(f"A listing can have up to {MAX_PHOTOS} photos.")
        cur = c.execute("INSERT INTO listing_photos (listing_id, filename, caption, position)"
                        " VALUES (?,?,?,?)", (listing_id, filename, caption.strip()[:120], n))
        return cur.lastrowid


def update_listing_photo(photo_id, host_id, filename=None, caption=None):
    """Replace the picture (filename) and/or edit the caption. If the picture was replaced,
    returns the OLD file name so the caller can delete that file."""
    with session() as c:
        p = _own_photo(c, photo_id, host_id)
        new_caption = p["caption"] if caption is None else caption.strip()[:120]
        c.execute("UPDATE listing_photos SET filename=?, caption=? WHERE id=?",
                  (filename or p["filename"], new_caption, photo_id))
        return p["filename"] if filename else None


def delete_listing_photo(photo_id, host_id):
    """Removes the photo. Returns its file name so the caller can delete the file."""
    with session() as c:
        p = _own_photo(c, photo_id, host_id)
        c.execute("DELETE FROM listing_photos WHERE id=?", (photo_id,))
        _renumber(c, _photo_order(c, p["listing_id"]))
        return p["filename"]


def move_listing_photo(photo_id, host_id, step):
    """step = -1 moves the photo one place earlier, +1 one place later."""
    with session() as c:
        p = _own_photo(c, photo_id, host_id)
        ids = _photo_order(c, p["listing_id"])
        i = ids.index(photo_id)
        j = i + (-1 if step < 0 else 1)
        if 0 <= j < len(ids):
            ids[i], ids[j] = ids[j], ids[i]
            _renumber(c, ids)


def set_cover_photo(photo_id, host_id):
    """Makes this photo first - it's the one shown on search cards."""
    with session() as c:
        p = _own_photo(c, photo_id, host_id)
        ids = [i for i in _photo_order(c, p["listing_id"]) if i != photo_id]
        _renumber(c, [photo_id] + ids)


def search_listings(query="", category="All", check_in="", check_out="", guests=""):
    """Approved, live listings. Every word of `query` must appear in title/location/category.
    If dates are given, listings with a clashing confirmed or pending booking are left out."""
    sql = ("SELECT l.*, u.name AS host_name FROM listings l JOIN users u ON u.id=l.host_id"
           " WHERE l.active=1 AND l.status='approved' AND u.active=1")
    params = []
    for tok in [t for t in re.split(r"[,\s]+", query.lower()) if t and t != "the"]:
        sql += " AND LOWER(l.title || ' ' || l.location || ' ' || l.category) LIKE ? ESCAPE '\\'"
        esc = tok.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        params.append(f"%{esc}%")
    if category and category != "All":
        sql += " AND l.category=?"
        params.append(category)
    if str(guests).strip():
        try:
            n = int(guests)
        except ValueError:
            raise AppError("Guests must be a whole number.")
        sql += " AND l.max_guests >= ?"
        params.append(n)
    if str(check_in).strip() or str(check_out).strip():
        ci, co = _check_range(check_in, check_out)
        sql += (" AND NOT EXISTS (SELECT 1 FROM bookings b WHERE b.listing_id=l.id"
                " AND b.status IN ('confirmed','pending') AND b.check_in < ? AND b.check_out > ?)")
        params += [co.isoformat(), ci.isoformat()]
    sql += " ORDER BY l.id"
    with session() as c:
        expire_pending(c)
        return c.execute(sql, params).fetchall()


def admin_listings():
    with session() as c:
        return c.execute(
            "SELECT l.*, u.name AS host_name FROM listings l JOIN users u ON u.id=l.host_id"
            " WHERE l.active=1 ORDER BY CASE l.status WHEN 'pending' THEN 0 ELSE 1 END, l.id DESC"
        ).fetchall()


def set_listing_status(listing_id, status):
    if status not in ("pending", "approved", "rejected"):
        raise AppError("Invalid status.")
    with session() as c:
        c.execute("UPDATE listings SET status=? WHERE id=?", (status, listing_id))


# ---------------------------------------------------------------- favorites
def favorite_ids(user_id):
    with session() as c:
        rows = c.execute(
            "SELECT f.listing_id FROM favorites f JOIN listings l ON l.id=f.listing_id"
            " WHERE f.user_id=? AND l.active=1 AND l.status='approved' ORDER BY f.rowid",
            (user_id,)).fetchall()
    return [r[0] for r in rows]


def toggle_favorite(user_id, listing_id):
    with session() as c:
        ok = c.execute("SELECT 1 FROM listings WHERE id=? AND active=1 AND status='approved'",
                       (listing_id,)).fetchone()
        if ok is None:
            raise AppError("This place is no longer available.")
        cur = c.execute("DELETE FROM favorites WHERE user_id=? AND listing_id=?", (user_id, listing_id))
        if cur.rowcount == 0:
            c.execute("INSERT INTO favorites (user_id, listing_id) VALUES (?,?)", (user_id, listing_id))
    return favorite_ids(user_id)


def clear_favorites(user_id):
    with session() as c:
        c.execute("DELETE FROM favorites WHERE user_id=?", (user_id,))


# ---------------------------------------------------------------- bookings
def _check_range(check_in, check_out):
    ci, co = parse_date(check_in), parse_date(check_out)
    if ci < date.today():
        raise AppError("Check-in can't be in the past.")
    if co <= ci:
        raise AppError("Check-out must be after check-in.")
    return ci, co


def quote(price_per_night, check_in, check_out):
    ci, co = _check_range(check_in, check_out)
    nights = (co - ci).days
    return nights, nights * price_per_night


def expire_pending(c):
    """Requests the host didn't answer in PENDING_HOURS are cancelled and fully refunded."""
    cutoff = (datetime.now() - timedelta(hours=PENDING_HOURS)).isoformat(timespec="seconds")
    c.execute(
        "UPDATE bookings SET status='cancelled', cancelled_by='system', cancelled_at=?,"
        " cancel_reason='Request expired: the host did not respond within 24 hours', refund=total_price"
        " WHERE status='pending' AND created_at != '' AND created_at < ?", (_now(), cutoff))


def create_booking(listing_id, guest_id, check_in, check_out, guests, method_id=None, plan="full"):
    """Creates a PENDING request (the host has PENDING_HOURS hours to accept) and records how the guest will
    pay. Nothing is charged until the host accepts. Returns the total."""
    ci, co = _check_range(check_in, check_out)
    if plan not in ("full", "split"):
        plan = "full"
    if plan == "split" and not split_eligible(check_in):
        raise AppError(f"Paying in two parts needs check-in to be at least {SPLIT_MIN_LEAD} days away.")
    try:
        guests = int(guests)
    except (TypeError, ValueError):
        raise AppError("Guests must be a whole number.")
    with session() as c:
        c.execute("BEGIN IMMEDIATE")  # lock so two people can't grab the same dates
        expire_pending(c)
        guest = c.execute("SELECT * FROM users WHERE id=?", (guest_id,)).fetchone()
        if guest is None:
            raise AppError("Account not found.")
        missing = profile_missing(dict(guest))
        if missing:
            raise AppError("Complete your profile before booking. Missing: " + ", ".join(missing) + ".")
        listing = c.execute("SELECT * FROM listings WHERE id=? AND active=1 AND status='approved'",
                            (listing_id,)).fetchone()
        if listing is None:
            raise AppError("This place is no longer available.")
        owner = c.execute("SELECT active FROM users WHERE id=?", (listing["host_id"],)).fetchone()
        if owner is None or not owner["active"]:
            raise AppError("This place is no longer available.")
        if listing["host_id"] == guest_id:
            raise AppError("You can't book your own listing.")
        if guests < 1 or guests > listing["max_guests"]:
            raise AppError(f"This place sleeps up to {listing['max_guests']} guests.")
        clash = c.execute(
            "SELECT 1 FROM bookings WHERE listing_id=? AND status IN ('confirmed','pending')"
            " AND check_in < ? AND check_out > ?",
            (listing_id, co.isoformat(), ci.isoformat())).fetchone()
        if clash:
            raise AppError("Those dates are already booked or on hold for another request.")
        method = c.execute("SELECT * FROM payment_methods WHERE id=? AND user_id=? AND active=1",
                           (method_id, guest_id)).fetchone() if method_id else None
        if method is None:
            raise AppError("Choose how you'd like to pay before sending your request.")
        total = (co - ci).days * listing["price_per_night"]
        policy = listing["cancellation_policy"] or DEFAULT_POLICY
        cur = c.execute(
            "INSERT INTO bookings (listing_id,guest_id,check_in,check_out,guests,total_price,status,created_at,policy)"
            " VALUES (?,?,?,?,?,?,'pending',?,?)",
            (listing_id, guest_id, ci.isoformat(), co.isoformat(), guests, total, _now(), policy))
        c.execute("INSERT INTO payments (booking_id,user_id,method_id,method_kind,method_label,plan,amount,created_at)"
                  " VALUES (?,?,?,?,?,?,?,?)",
                  (cur.lastrowid, guest_id, method["id"], method["kind"], method_label(method), plan, total, _now()))
        return total


def guest_bookings(guest_id):
    with session() as c:
        expire_pending(c)
        return c.execute(
            "SELECT b.*, l.title, l.location, l.image_seed, u.name AS host_name,"
            " u.phone AS host_phone, u.email AS host_email"
            " FROM bookings b JOIN listings l ON l.id=b.listing_id JOIN users u ON u.id=l.host_id"
            " WHERE b.guest_id=? ORDER BY b.id DESC", (guest_id,)).fetchall()


def unseen_trip_ids(guest_id):
    """Ids of this guest's bookings that a host has confirmed and the guest has not looked at yet."""
    with session() as c:
        rows = c.execute("SELECT id FROM bookings WHERE guest_id=? AND status='confirmed' AND guest_seen=0",
                         (guest_id,)).fetchall()
    return [r["id"] for r in rows]


def unseen_trip_count(guest_id):
    """The red number: how many confirmed trips the guest has not looked at yet."""
    with session() as c:
        return c.execute("SELECT COUNT(*) FROM bookings WHERE guest_id=? AND status='confirmed' AND guest_seen=0",
                         (guest_id,)).fetchone()[0]


def mark_trips_seen(guest_id, booking_ids):
    """The guest has looked at these confirmed trips: clear their red badge."""
    ids = [int(i) for i in booking_ids]
    if not ids:
        return
    with session() as c:
        c.execute(f"UPDATE bookings SET guest_seen=1 WHERE guest_id=? AND id IN ({','.join('?' * len(ids))})",
                  (guest_id, *ids))


def host_bookings(host_id):
    with session() as c:
        expire_pending(c)
        return c.execute(
            "SELECT b.*, l.title, u.name AS guest_name, u.phone AS guest_phone FROM bookings b"
            " JOIN listings l ON l.id=b.listing_id JOIN users u ON u.id=b.guest_id"
            " WHERE l.host_id=?"
            " ORDER BY CASE b.status WHEN 'pending' THEN 0 WHEN 'confirmed' THEN 1 ELSE 2 END,"
            " b.check_in DESC", (host_id,)).fetchall()


def host_pending_count(host_id):
    """Reservation requests waiting for this host's approval."""
    with session() as c:
        expire_pending(c)
        return c.execute(
            "SELECT COUNT(*) FROM bookings b JOIN listings l ON l.id=b.listing_id"
            " WHERE l.host_id=? AND b.status='pending'", (host_id,)).fetchone()[0]


def all_bookings():
    with session() as c:
        expire_pending(c)
        return c.execute(
            "SELECT b.*, l.title, u.name AS guest_name FROM bookings b"
            " JOIN listings l ON l.id=b.listing_id JOIN users u ON u.id=b.guest_id"
            " ORDER BY b.id DESC").fetchall()


def cancel_booking(booking_id, guest_id):
    """Guest withdraws a pending request or cancels a confirmed booking. Returns the refund."""
    with session() as c:
        expire_pending(c)
        b = c.execute("SELECT * FROM bookings WHERE id=? AND guest_id=?",
                      (booking_id, guest_id)).fetchone()
        if b is None:
            raise AppError("Booking not found.")
        if b["status"] == "cancelled":
            raise AppError("This booking is already cancelled.")
        if b["status"] != "pending" and b["check_in"] <= date.today().isoformat():
            raise AppError("Trips that have started or finished can't be cancelled.")
        refund, _ = guest_refund(b, c)
        reason = ("Request withdrawn by guest" if b["status"] == "pending"
                  else "Cancelled by guest")
        c.execute(
            "UPDATE bookings SET status='cancelled', cancelled_by='guest', cancelled_at=?,"
            " cancel_reason=?, refund=? WHERE id=?", (_now(), reason, refund, booking_id))
        return refund


def host_decide(booking_id, host_id, action):
    """Host answers a request: 'approve' or 'decline' (pending), or 'cancel' (confirmed)."""
    if action not in ("approve", "decline", "cancel"):
        raise AppError("Unknown action.")
    with session() as c:
        expire_pending(c)
        b = c.execute(
            "SELECT b.*, l.host_id AS owner FROM bookings b JOIN listings l ON l.id=b.listing_id"
            " WHERE b.id=?", (booking_id,)).fetchone()
        if b is None or b["owner"] != host_id:
            raise AppError("Reservation not found.")
        if action == "approve":
            if b["status"] != "pending":
                raise AppError("Only pending requests can be approved (it may have expired).")
            if b["check_in"] < date.today().isoformat():
                raise AppError("The check-in date has already passed, so this request can't be approved.")
            c.execute("UPDATE bookings SET status='confirmed', confirmed_at=?, guest_seen=0 WHERE id=?",
                      (_now(), booking_id))
        elif action == "decline":
            if b["status"] != "pending":
                raise AppError("Only pending requests can be declined (it may have expired).")
            c.execute(
                "UPDATE bookings SET status='cancelled', cancelled_by='host', cancelled_at=?,"
                " cancel_reason='Declined by host', refund=total_price WHERE id=?", (_now(), booking_id))
        else:
            if b["status"] != "confirmed":
                raise AppError("Only confirmed reservations can be cancelled.")
            if b["check_out"] < date.today().isoformat():
                raise AppError("That stay is already over.")
            c.execute(  # the host cancels: the guest gets back everything they have paid
                "UPDATE bookings SET status='cancelled', cancelled_by='host', cancelled_at=?,"
                " cancel_reason='Cancelled by host', refund=? WHERE id=?",
                (_now(), paid_amount(b, c), booking_id))


# ---------------------------------------------------------------- messages
def conversation_info(user_id, listing_id, guest_id):
    """Who is talking about which listing. Raises if `user_id` isn't one of the two people."""
    with session() as c:
        row = c.execute(
            "SELECT l.id AS listing_id, l.title, l.host_id, hu.name AS host_name,"
            " gu.id AS guest_id, gu.name AS guest_name"
            " FROM listings l JOIN users hu ON hu.id=l.host_id JOIN users gu ON gu.id=?"
            " WHERE l.id=?", (guest_id, listing_id)).fetchone()
    if row is None:
        raise AppError("Conversation not found.")
    info = dict(row)
    if info["guest_id"] == info["host_id"]:
        raise AppError("That's your own listing, so there is nobody to message.")
    if user_id not in (info["guest_id"], info["host_id"]):
        raise AppError("You're not part of that conversation.")
    return info


def conversations(user_id):
    """One row per conversation the user is in, newest first, with an unread count."""
    with session() as c:
        return c.execute(
            "SELECT m.listing_id, m.guest_id, l.title, l.host_id,"
            " gu.name AS guest_name, hu.name AS host_name,"
            " m.body AS last_body, m.created_at AS last_at, MAX(m.id) AS last_id,"
            " SUM(CASE WHEN m.sender_id != ? AND m.is_read = 0 THEN 1 ELSE 0 END) AS unread"
            " FROM messages m JOIN listings l ON l.id=m.listing_id"
            " JOIN users gu ON gu.id=m.guest_id JOIN users hu ON hu.id=l.host_id"
            " WHERE m.guest_id=? OR l.host_id=?"
            " GROUP BY m.listing_id, m.guest_id ORDER BY last_id DESC",
            (user_id, user_id, user_id)).fetchall()


def thread(user_id, listing_id, guest_id):
    """All messages of one conversation (oldest first). Marks the other person's messages read."""
    conversation_info(user_id, listing_id, guest_id)
    with session() as c:
        rows = c.execute(
            "SELECT m.*, u.name AS sender_name FROM messages m JOIN users u ON u.id=m.sender_id"
            " WHERE m.listing_id=? AND m.guest_id=? ORDER BY m.id", (listing_id, guest_id)).fetchall()
        c.execute("UPDATE messages SET is_read=1 WHERE listing_id=? AND guest_id=? AND sender_id != ?",
                  (listing_id, guest_id, user_id))
    return rows


def send_message(sender_id, listing_id, guest_id, body):
    body = body.strip()
    if not body:
        raise AppError("Type a message first.")
    if len(body) > 2000:
        raise AppError("Messages can be up to 2000 characters.")
    info = conversation_info(sender_id, listing_id, guest_id)
    with session() as c:
        if sender_id == info["host_id"]:  # hosts only write to guests who contacted or booked them
            known = c.execute(
                "SELECT 1 FROM messages WHERE listing_id=? AND guest_id=?"
                " UNION SELECT 1 FROM bookings WHERE listing_id=? AND guest_id=?",
                (listing_id, guest_id, listing_id, guest_id)).fetchone()
            if known is None:
                raise AppError("Guests need to contact you first, or have a reservation with you.")
        c.execute(
            "INSERT INTO messages (listing_id, guest_id, sender_id, body, created_at) VALUES (?,?,?,?,?)",
            (listing_id, guest_id, sender_id, body, _now()))


def unread_count(user_id):
    with session() as c:
        return c.execute(
            "SELECT COUNT(*) FROM messages m JOIN listings l ON l.id=m.listing_id"
            " WHERE (m.guest_id=? OR l.host_id=?) AND m.sender_id != ? AND m.is_read=0",
            (user_id, user_id, user_id)).fetchone()[0]


# ---------------------------------------------------------------- admin stats
def stats():
    with session() as c:
        def one(sql):
            return c.execute(sql).fetchone()[0]
        return {
            "users": one("SELECT COUNT(*) FROM users WHERE role!='admin'"),
            "hosts": one("SELECT COUNT(*) FROM users WHERE role='host'"),
            "live": one("SELECT COUNT(*) FROM listings WHERE active=1 AND status='approved'"),
            "pending": one("SELECT COUNT(*) FROM listings WHERE active=1 AND status='pending'"),
            "bookings": one("SELECT COUNT(*) FROM bookings WHERE status='confirmed'"),
            "value": one("SELECT COALESCE(SUM(total_price),0) FROM bookings WHERE status='confirmed'"),
        }


# =============================================================== payments: the logic

def _f(row, key, default=""):
    """row[key] for a sqlite Row or a dict, with a default when the column is missing or empty."""
    try:
        v = row[key]
    except (KeyError, IndexError):
        return default
    return default if v is None else v


def _dt(day, hour=0):
    return datetime.combine(parse_date(day), time(hour, 0))


def _luhn(number):
    total = 0
    for i, ch in enumerate(reversed(number)):
        d = int(ch)
        if i % 2:
            d = d * 2 - 9 if d > 4 else d * 2
        total += d
    return total % 10 == 0


def card_brand(number):
    n = re.sub(r"\D", "", number)
    if n.startswith("4"):
        return "Visa"
    if re.match(r"^(5[1-5]|2(2[2-9][1-9]|2[3-9]|[3-6]|7[01]|720))", n):
        return "MasterCard"
    if n[:2] in ("34", "37"):
        return "Amex"
    if n.startswith(("6011", "65")) or re.match(r"^64[4-9]", n):
        return "Discover"
    return ""


def _check_card(number, expiry, cvv, holder):
    digits = re.sub(r"[\s-]", "", number)
    if not digits.isdigit() or not 13 <= len(digits) <= 19 or not _luhn(digits):
        raise AppError("That card number doesn't look right. Check the digits and try again.")
    brand = card_brand(digits)
    if not brand:
        raise AppError("We accept Visa, MasterCard, Amex and Discover cards.")
    m = re.fullmatch(r"\s*(\d{1,2})\s*/\s*(\d{2}|\d{4})\s*", expiry)
    if not m or not 1 <= int(m.group(1)) <= 12:
        raise AppError("Expiry date should look like MM/YY, e.g. 08/28.")
    month, year = int(m.group(1)), int(m.group(2))
    year += 2000 if year < 100 else 0
    today = date.today()
    if (year, month) < (today.year, today.month):
        raise AppError("That card has expired.")
    need = 4 if brand == "Amex" else 3
    if not re.fullmatch(rf"\d{{{need}}}", cvv.strip()):
        raise AppError(f"The security code (CVV) for {brand} is {need} digits.")
    if len(holder.strip()) < 2:
        raise AppError("Enter the name on the card.")
    return brand, digits[-4:], month, year


def _check_email(text, label):
    text = text.strip()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", text):
        raise AppError(f"{label} doesn't look like an email address.")
    return text.lower()


def _check_mobile(text, label):
    digits = re.sub(r"\D", "", text)
    if digits.startswith("63") and len(digits) == 12:
        digits = "0" + digits[2:]
    if not re.fullmatch(r"09\d{9}", digits):
        raise AppError(f"{label} should be a Philippine mobile number like 0917 123 4567.")
    return digits


def method_label(m):
    kind = _f(m, "kind")
    if kind == "card":
        return f"{_f(m, 'brand')} \u2022\u2022\u2022\u2022 {_f(m, 'last4')}"
    if kind == "paypal":
        return f"PayPal ({_f(m, 'detail')})"
    if kind in ("gcash", "maya"):
        return f"{KIND_NAMES[kind]} \u2022\u2022\u2022\u2022 {_f(m, 'detail')[-4:]}"
    return KIND_NAMES.get(kind, "Payment method")


def method_sub(m):
    """The grey second line under a saved method."""
    kind = _f(m, "kind")
    if kind == "card":
        return f"{_f(m, 'holder')}  \u00B7  expires {int(_f(m, 'exp_month', 0)):02d}/{int(_f(m, 'exp_year', 0)) % 100:02d}"
    if kind == "paypal":
        return "PayPal account"
    if kind in ("apple_pay", "google_pay"):
        return "Digital wallet on this device"
    return "Mobile wallet"


def payment_methods(user_id):
    with session() as c:
        return c.execute("SELECT * FROM payment_methods WHERE user_id=? AND active=1"
                         " ORDER BY is_default DESC, id", (user_id,)).fetchall()


def add_payment_method(user_id, kind, holder="", number="", expiry="", cvv="", detail=""):
    """Validates and saves a payment method. Returns its id. The card number and CVV are NOT stored."""
    if kind not in KIND_NAMES:
        raise AppError("Choose a payment method type.")
    brand, last4, month, year, stored = "", "", None, None, ""
    if kind == "card":
        brand, last4, month, year = _check_card(number, expiry, cvv, holder)
        holder = holder.strip()
    elif kind == "paypal":
        stored = _check_email(detail, "That PayPal email")
    elif kind in ("gcash", "maya"):
        stored = _check_mobile(detail, f"The {KIND_NAMES[kind]} number")
    with session() as c:
        for m in c.execute("SELECT * FROM payment_methods WHERE user_id=? AND active=1 AND kind=?",
                           (user_id, kind)).fetchall():
            same = (kind == "card" and m["last4"] == last4 and m["brand"] == brand) or \
                   (kind in ("paypal", "gcash", "maya") and m["detail"] == stored) or \
                   kind in ("apple_pay", "google_pay")
            if same:
                raise AppError("You've already saved that payment method.")
        first = not c.execute("SELECT 1 FROM payment_methods WHERE user_id=? AND active=1", (user_id,)).fetchone()
        cur = c.execute(
            "INSERT INTO payment_methods (user_id,kind,brand,last4,exp_month,exp_year,holder,detail,"
            "is_default,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (user_id, kind, brand, last4, month, year, holder, stored, int(first), _now()))
        return cur.lastrowid


def set_default_method(user_id, method_id):
    with session() as c:
        if not c.execute("SELECT 1 FROM payment_methods WHERE id=? AND user_id=? AND active=1",
                         (method_id, user_id)).fetchone():
            raise AppError("Payment method not found.")
        c.execute("UPDATE payment_methods SET is_default=0 WHERE user_id=?", (user_id,))
        c.execute("UPDATE payment_methods SET is_default=1 WHERE id=?", (method_id,))


def remove_payment_method(user_id, method_id):
    """Hides the method. Past bookings keep their own copy of its name, so receipts still read correctly."""
    with session() as c:
        m = c.execute("SELECT * FROM payment_methods WHERE id=? AND user_id=? AND active=1",
                      (method_id, user_id)).fetchone()
        if m is None:
            raise AppError("Payment method not found.")
        busy = c.execute(
            "SELECT 1 FROM payments p JOIN bookings b ON b.id=p.booking_id WHERE p.method_id=? AND"
            " (b.status='pending' OR (b.status='confirmed' AND b.check_out >= ?))",
            (method_id, date.today().isoformat())).fetchone()
        if busy:
            raise AppError("This method pays for a current reservation, so it can't be removed yet. Add another "
                           "method to use for new bookings, then remove this one after the stay.")
        c.execute("UPDATE payment_methods SET active=0, is_default=0 WHERE id=?", (method_id,))
        if m["is_default"]:
            nxt = c.execute("SELECT id FROM payment_methods WHERE user_id=? AND active=1 ORDER BY id LIMIT 1",
                            (user_id,)).fetchone()
            if nxt:
                c.execute("UPDATE payment_methods SET is_default=1 WHERE id=?", (nxt["id"],))


def split_eligible(check_in):
    """Payment plans (pay in two parts) need check-in to be at least SPLIT_MIN_LEAD days away."""
    try:
        return (parse_date(check_in) - date.today()).days >= SPLIT_MIN_LEAD
    except AppError:
        return False


def split_amounts(total):
    first = round(total / 2, 2)
    return first, round(total - first, 2)


def split_due(check_in):
    return parse_date(check_in) - timedelta(days=SPLIT_MIN_DAYS)


# ---------------------------------------------------------------- what a guest has paid so far
def _payment_row(b, c=None):
    if c is not None:
        return c.execute("SELECT * FROM payments WHERE booking_id=?", (b["id"],)).fetchone()
    with session() as c2:
        return c2.execute("SELECT * FROM payments WHERE booking_id=?", (b["id"],)).fetchone()


def _confirmed_ts(b):
    return _parse_ts(_f(b, "confirmed_at")) or _parse_ts(_f(b, "created_at")) or datetime.now()


def was_requested_only(b):
    """True if the booking was cancelled before the host accepted it (so nothing was ever charged)."""
    if _f(b, "status") != "cancelled":
        return False
    if _f(b, "confirmed_at"):
        return False
    reason = _f(b, "cancel_reason")
    return reason.startswith(("Request withdrawn", "Declined by host", "Request expired")) \
        or "before the host replied" in reason


def paid_amount(b, c=None, at=None):
    """How much of the booking the guest has actually been charged at time `at` (default: now)."""
    status = _f(b, "status")
    if status == "pending" or was_requested_only(b):
        return 0.0
    at = at or datetime.now()
    total = float(b["total_price"])
    pay = _payment_row(b, c)
    if at < _confirmed_ts(b):
        return 0.0
    if pay is None or pay["plan"] != "split":
        return round(total, 2)
    first, second = split_amounts(total)
    paid = first
    if at >= datetime.combine(split_due(b["check_in"]), time(0, 0)):
        paid += second
    return round(paid, 2)


def refund_policy_of(b):
    p = _f(b, "policy") or DEFAULT_POLICY
    return p if p in POLICIES else DEFAULT_POLICY


def guest_refund(b, c=None):
    """(amount, explanation) a guest gets back if they cancel booking `b` right now. It follows the host's
    cancellation policy and can never exceed what the guest has actually paid."""
    total = float(b["total_price"])
    if b["status"] == "pending":
        return total, "Full refund: nothing is charged until the host accepts."
    policy = refund_policy_of(b)
    created = _parse_ts(_f(b, "created_at"))
    days = (parse_date(b["check_in"]) - date.today()).days
    within_48h = bool(created) and datetime.now() - created <= timedelta(hours=48)
    pct, note = 0.5, f"50% refund: cancelled late under the host's {policy} policy."
    if policy == "Strict":
        if within_48h and days >= 14:
            pct, note = 1.0, "Full refund: cancelled within 48 hours of booking (Strict policy)."
        elif days >= 7:
            pct, note = 0.5, "50% refund: cancelled 7 or more days before check-in (Strict policy)."
        else:
            pct, note = 0.0, "No refund: cancelled less than 7 days before check-in (Strict policy)."
    elif within_48h:
        pct, note = 1.0, "Full refund: cancelled within 48 hours of booking."
    elif policy == "Flexible" and days >= 1:
        pct, note = 1.0, "Full refund: cancelled at least 24 hours before check-in (Flexible policy)."
    elif policy == "Moderate" and days >= 5:
        pct, note = 1.0, "Full refund: cancelled 5 or more days before check-in (Moderate policy)."
    refund = round(total * pct, 2)
    paid = paid_amount(b, c)
    if refund > paid:
        refund = paid
        note += " Only the part you've already paid is refunded; the rest is never charged."
    return refund, note


def refunded_amount(b):
    """What the guest actually got back for a cancelled booking (0 if it was never charged)."""
    if _f(b, "status") != "cancelled" or was_requested_only(b):
        return 0.0
    at = _parse_ts(_f(b, "cancelled_at")) or datetime.now()
    return round(min(float(_f(b, "refund", 0) or 0), paid_amount(b, at=at)), 2)


def payment_summary(b):
    """Everything the 'Payment' part of a trip needs, worked out from the booking and its payment record."""
    pay = _payment_row(b)
    total = float(b["total_price"])
    status = b["status"]
    out = {"recorded": pay is not None, "method": (pay["method_label"] if pay else ""),
           "kind": (pay["method_kind"] if pay else ""), "plan": (pay["plan"] if pay else "full"),
           "total": total, "parts": [], "paid": 0.0, "refund": 0.0, "refund_eta": "",
           "never_charged": False, "release_at": None, "released": False}
    now = datetime.now()
    ci_release = _dt(b["check_in"], CHECK_IN_HOUR) + timedelta(hours=PAYOUT_DELAY_HOURS)
    out["release_at"] = ci_release
    split = out["plan"] == "split"
    amounts = split_amounts(total) if split else (total,)
    due = [None] + ([split_due(b["check_in"])] if split else [])
    cancelled_at = _parse_ts(_f(b, "cancelled_at")) if status == "cancelled" else None
    for i, amt in enumerate(amounts):
        when = None if i == 0 else datetime.combine(due[i], time(0, 0))
        if status == "pending":
            state = "authorized" if i == 0 else "scheduled"
        elif was_requested_only(b):
            state = "released" if i == 0 else "cancelled"
        else:
            charged_at = _confirmed_ts(b) if when is None else when
            if cancelled_at and charged_at > cancelled_at:
                state = "cancelled"
            else:
                state = "paid" if charged_at <= now else "scheduled"
        out["parts"].append({"n": i + 1, "amount": amt, "due": when, "state": state,
                             "at": _confirmed_ts(b) if (i == 0 and state == "paid") else when})
    out["paid"] = paid_amount(b, at=(cancelled_at or now)) if status != "pending" else 0.0
    if status == "cancelled":
        out["never_charged"] = was_requested_only(b)
        out["refund"] = refunded_amount(b)
        out["refund_eta"] = REFUND_ETA.get(out["kind"], "5\u201310 business days")
    out["released"] = status == "confirmed" and now >= ci_release
    return out


# ---------------------------------------------------------------- host payouts
def payout_method(host_id):
    with session() as c:
        return c.execute("SELECT * FROM payout_methods WHERE host_id=?", (host_id,)).fetchone()


def payout_label(m):
    return _f(m, "label") or PAYOUT_KINDS.get(_f(m, "kind"), ("Payout method",))[0]


def set_payout_method(host_id, kind, holder="", detail=""):
    if kind not in PAYOUT_KINDS:
        raise AppError("Choose how you'd like to be paid.")
    name = PAYOUT_KINDS[kind][0]
    holder = holder.strip()
    if kind in ("paypal", "payoneer"):
        stored = _check_email(detail, f"The {name} email")
        label = f"{name} ({stored})"
    elif kind == "gcash":
        stored = _check_mobile(detail, "The GCash number")
        label = f"GCash \u2022\u2022\u2022\u2022 {stored[-4:]}"
    else:
        digits = re.sub(r"[\s-]", "", detail)
        need = (13, 19) if kind == "fast_pay" else (6, 34)
        if len(holder) < 2:
            raise AppError("Enter the account holder's name.")
        if not digits.isalnum() or not need[0] <= len(digits) <= need[1]:
            raise AppError(f"That {PAYOUT_KINDS[kind][2].lower()} doesn't look right.")
        if kind == "fast_pay" and not (digits.isdigit() and _luhn(digits)):
            raise AppError("Fast Pay needs a valid debit card number.")
        stored = digits[-4:]
        label = f"{name.split(' (')[0]} \u2022\u2022\u2022\u2022 {stored}"
    with session() as c:
        c.execute("INSERT INTO payout_methods (host_id,kind,holder,detail,label,created_at) VALUES (?,?,?,?,?,?)"
                  " ON CONFLICT(host_id) DO UPDATE SET kind=excluded.kind, holder=excluded.holder,"
                  " detail=excluded.detail, label=excluded.label, created_at=excluded.created_at",
                  (host_id, kind, holder, stored, label, _now()))


def remove_payout_method(host_id):
    with session() as c:
        c.execute("DELETE FROM payout_methods WHERE host_id=?", (host_id,))


def booking_net(total):
    """(host fee, what the host keeps) for a booking total."""
    fee = round(total * HOST_FEE_RATE, 2)
    return fee, round(total - fee, 2)


def host_payouts(host_id):
    """(rows, summary): every payout the host is owed or has received, derived from confirmed bookings.
    Rules: paid ~24h after check-in; a brand-new host's first payout waits until 24h after check-out;
    stays of 28+ nights are paid in monthly instalments."""
    now = datetime.now()
    method = payout_method(host_id)
    with session() as c:
        bookings = c.execute(
            "SELECT b.*, l.title, u.name AS guest_name FROM bookings b JOIN listings l ON l.id=b.listing_id"
            " JOIN users u ON u.id=b.guest_id WHERE l.host_id=? AND b.status='confirmed'"
            " ORDER BY b.check_in, b.id", (host_id,)).fetchall()
    rows, summary = [], {"escrow": 0.0, "held": 0.0, "paid": 0.0, "waiting": 0.0, "next": None}
    for b in bookings:
        total = float(b["total_price"])
        fee, net = booking_net(total)
        nights = (parse_date(b["check_out"]) - parse_date(b["check_in"])).days
        first = _dt(b["check_in"], CHECK_IN_HOUR) + timedelta(hours=PAYOUT_DELAY_HOURS)
        prior = any(o["check_out"] < b["check_in"] for o in bookings if o["id"] != b["id"])
        held = False
        if nights >= LONG_STAY_NIGHTS:
            parts = -(-nights // 30)
            amounts = [round(net / parts, 2)] * (parts - 1)
            amounts.append(round(net - sum(amounts), 2))
            dates = [first + timedelta(days=30 * k) for k in range(parts)]
        else:
            amounts, dates = [net], [first]
            if not prior:  # a new host: hold the first payout until 24h after check-out
                held = True
                dates = [min(_dt(b["check_out"]) + timedelta(hours=PAYOUT_DELAY_HOURS),
                             first + timedelta(days=30))]
        for k, (amt, when) in enumerate(zip(amounts, dates), start=1):
            if when > now:
                state = "held" if held else "escrow"
            else:
                state = "paid" if method else "waiting"
            rows.append({"booking_id": b["id"], "title": b["title"], "guest": b["guest_name"],
                         "check_in": b["check_in"], "check_out": b["check_out"], "nights": nights,
                         "gross": total if k == 1 else None, "fee": fee if k == 1 else None,
                         "amount": amt, "seq": k, "of": len(amounts), "release_at": when, "state": state,
                         "new_host_hold": held})
            summary[state] += amt
            if state in ("escrow", "held") and (summary["next"] is None or when < summary["next"]):
                summary["next"] = when
    rows.sort(key=lambda r: r["release_at"], reverse=True)
    return rows, summary