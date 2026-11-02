"""Pictures: profile photos, listing photos and the cached stock photos for the stay cards."""

import os
import queue
import re
import threading
import urllib.request
import uuid
from pathlib import Path

import database as db
from theme import CARD, PAPER2


try:
    from PIL import Image, ImageDraw, ImageOps, ImageTk
except ImportError:  # the app still runs, just without photos
    Image = None

# Photos, avatars and listing photos are kept inside core/, next to this file.
BASE = Path(__file__).resolve().parent

AVATAR_DIR = BASE / "avatars"

PHOTO_DIR = BASE / "listing_photos"  # pictures hosts upload for their listings


def avatar_photo(user, size):
    """A round PhotoImage of the user's profile picture, or None if they have none."""
    if Image is None or not user or not user.get("avatar"):
        return None
    try:
        with Image.open(AVATAR_DIR / user["avatar"]) as im:
            im = ImageOps.fit(im.convert("RGBA"), (size, size), Image.LANCZOS)
        big = Image.new("L", (size * 4, size * 4), 0)  # drawn large, shrunk = smooth edge
        ImageDraw.Draw(big).ellipse((0, 0, size * 4 - 1, size * 4 - 1), fill=255)
        im.putalpha(big.resize((size, size), Image.LANCZOS))
        return ImageTk.PhotoImage(im)
    except Exception:
        return None


def save_avatar(user_id, src_path):
    """Crop the chosen picture square, shrink it, store it in ./avatars. Returns the file name."""
    if Image is None:
        raise db.AppError("Profile photos need Pillow. Run: pip install pillow")
    try:
        AVATAR_DIR.mkdir(exist_ok=True)
        with Image.open(src_path) as im:
            im = ImageOps.exif_transpose(im).convert("RGB")
            im = ImageOps.fit(im, (256, 256), Image.LANCZOS)
        name = f"user_{user_id}.png"
        im.save(AVATAR_DIR / name)
    except db.AppError:
        raise
    except Exception:
        raise db.AppError("That file couldn't be opened as a picture. Try a PNG or JPG.")
    return name


def save_listing_photo(src_path, listing_id):
    """Fix the rotation, shrink to at most 1600 px, store as JPEG in ./listing_photos. Returns the file name."""
    if Image is None:
        raise db.AppError("Listing photos need Pillow. Run: pip install pillow")
    try:
        PHOTO_DIR.mkdir(exist_ok=True)
        with Image.open(src_path) as im:
            im = ImageOps.exif_transpose(im).convert("RGB")
            im.thumbnail((1600, 1600), Image.LANCZOS)
        name = f"l{listing_id}_{uuid.uuid4().hex[:10]}.jpg"
        im.save(PHOTO_DIR / name, quality=88)
    except Exception:
        raise db.AppError(f"\u201C{Path(src_path).name}\u201D couldn't be opened as a picture. Try a PNG or JPG.")
    return name


def delete_photo_file(name):
    try:
        (PHOTO_DIR / name).unlink()
    except OSError:
        pass


def photo_thumb(name, w, h, radius=10, bg=CARD):
    """A rounded PhotoImage of a stored listing photo (a plain tile if the file has gone missing)."""
    try:
        with Image.open(PHOTO_DIR / name) as im:
            im = ImageOps.fit(im.convert("RGB"), (w, h), Image.LANCZOS)
    except Exception:
        im = Image.new("RGB", (w, h), "#E3DAC6")
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, w - 1, h - 1), radius, fill=255)
    out = Image.new("RGB", (w, h), bg)
    out.paste(im, (0, 0), mask)
    return ImageTk.PhotoImage(out)


def cover_file(listing_id):
    """File name of the host's cover photo for a listing, or None (then the stock photo is used)."""
    files = db.photo_files(listing_id)
    return files[0] if files else None


class Photos:
    """Puts rounded photos into labels. Downloads happen in the background and are saved in ./photos."""

    def __init__(self, root):
        self.root = root
        self.dir = BASE / "photos"
        self.waiting = {}
        self.done = queue.Queue()
        self.ok = Image is not None
        if self.ok:
            try:
                self.dir.mkdir(exist_ok=True)
            except OSError:
                self.ok = False
        root.after(250, self.poll)

    def _show(self, label, im, w, h, radius, bg):
        im = ImageOps.fit(im.convert("RGB"), (w, h), Image.LANCZOS)
        mask = Image.new("L", (w, h), 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, w - 1, h - 1), radius, fill=255)
        out = Image.new("RGB", (w, h), bg)
        out.paste(im, (0, 0), mask)
        ph = ImageTk.PhotoImage(out)
        label.config(image=ph, text="")
        label.image = ph  # keep a reference or Tk drops the picture

    def blank(self, label, w, h, radius=14, bg=PAPER2):
        """An empty tile (used where a listing has fewer photos than the grid has slots)."""
        if self.ok:
            self._show(label, Image.new("RGB", (w, h), "#E9E1CF"), w, h, radius, bg)
        else:
            label.config(bg="#E9E1CF", width=max(w // 8, 1), height=max(h // 17, 1))

    def attach(self, label, seed, w, h, radius=14, bg=PAPER2, text="", local=None):
        """`local` = file name of a photo the host uploaded; it wins over the stock photo for `seed`."""
        if self.ok and local and (PHOTO_DIR / local).exists():
            try:
                with Image.open(PHOTO_DIR / local) as im:
                    self._show(label, im, w, h, radius, bg)
                return
            except Exception:
                pass  # unreadable file: fall back to the stock photo below
        if not self.ok:
            label.config(text=text, fg="white", bg="#B9A98A", wraplength=w - 20,
                         width=max(w // 8, 1), height=max(h // 17, 1))
            return
        self._show(label, Image.new("RGB", (w, h), "#E3DAC6"), w, h, radius, bg)  # placeholder
        safe = re.sub(r"[^A-Za-z0-9_-]", "_", seed)
        path = self.dir / f"{safe}_{w}x{h}.jpg"
        job = (label, path, w, h, radius, bg)
        if path.exists():
            self._apply(job)
        elif path in self.waiting:
            self.waiting[path].append(job)
        else:
            self.waiting[path] = [job]
            url = f"https://picsum.photos/seed/{seed}/{w}/{h}.jpg"
            threading.Thread(target=self._fetch, args=(url, path), daemon=True).start()

    def _fetch(self, url, path):
        tmp = path.with_suffix(".part")
        ok = False
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "RoamRest"})
            with urllib.request.urlopen(req, timeout=15) as r:
                tmp.write_bytes(r.read())
            os.replace(tmp, path)
            ok = True
        except Exception:
            pass
        self.done.put((path, ok))

    def _apply(self, job):
        label, path, w, h, radius, bg = job
        try:
            with Image.open(path) as im:
                self._show(label, im, w, h, radius, bg)
        except Exception:
            try:
                path.unlink()
            except OSError:
                pass

    def poll(self):
        try:
            while True:
                path, ok = self.done.get_nowait()
                for job in self.waiting.pop(path, []):
                    if ok and job[0].winfo_exists():
                        self._apply(job)
        except queue.Empty:
            pass
        self.root.after(250, self.poll)