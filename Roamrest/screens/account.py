"""Login / sign up, profile, account settings and the language & currency window."""

import tkinter as tk
from tkinter import filedialog
from tkinter import messagebox
from tkinter import ttk

import database as db
from helpers import CUR, L, button
from images import AVATAR_DIR, avatar_photo, save_avatar
from navigation import Page
from theme import CLAY, CLAY_DEEP, LINE, MUTED, PAPER, PILL_BG


class AuthDialog(tk.Toplevel):
    def __init__(self, app):
        super().__init__(app.root)
        self.app = app
        self.title("RoamRest account")
        self.configure(bg=PAPER, padx=20, pady=16)
        self.resizable(False, False)
        tk.Label(self, text="RoamRest", font=("Georgia", 20, "bold"), bg=PAPER, fg=CLAY).pack()
        self.nb = ttk.Notebook(self)
        self.nb.pack(pady=10)

        lf = ttk.Frame(self.nb, padding=16)
        self.nb.add(lf, text="Log in")
        self.l_email = self._field(lf, "Email", 0)
        self.l_pass = self._field(lf, "Password", 1, "*")
        button(lf, "Log in", self.do_login).grid(row=2, column=0, columnspan=2, pady=10)

        rf = ttk.Frame(self.nb, padding=16)
        self.nb.add(rf, text="Sign up")
        self.r_name = self._field(rf, "Full name", 0)
        self.r_email = self._field(rf, "Email", 1)
        self.r_pass = self._field(rf, "Password", 2, "*")
        self.r_host = tk.BooleanVar()
        ttk.Checkbutton(rf, text="I also want to host (list my place)",
                        variable=self.r_host).grid(row=3, column=0, columnspan=2, pady=4)
        button(rf, "Create account", self.do_register).grid(row=4, column=0, columnspan=2, pady=10)

        tk.Label(self, text="Demo logins:  admin@roamrest.com / admin123\n"
                            "host@roamrest.com / host123   |   guest@roamrest.com / guest123",
                 bg=PAPER, fg=MUTED, font=("Arial", 8), justify="center").pack()
        self.bind("<Return>", lambda e: self.do_login() if self.nb.index("current") == 0
                  else self.do_register())
        self.l_entry.focus_set()

    def _field(self, parent, label, row, show=""):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="e", padx=5, pady=6)
        var = tk.StringVar()
        entry = ttk.Entry(parent, textvariable=var, show=show, width=30)
        entry.grid(row=row, column=1, pady=6)
        if not hasattr(self, "l_entry"):
            self.l_entry = entry
        return var

    def do_login(self):
        try:
            user = db.login(self.l_email.get(), self.l_pass.get())
        except db.AppError as e:
            return messagebox.showerror("Log in failed", str(e), parent=self)
        self.app.set_user(user)
        self.destroy()

    def do_register(self):
        try:
            db.register_user(self.r_name.get(), self.r_email.get(), self.r_pass.get(), self.r_host.get())
            user = db.login(self.r_email.get(), self.r_pass.get())
        except db.AppError as e:
            return messagebox.showerror("Sign up failed", str(e), parent=self)
        self.app.set_user(user)
        self.destroy()


class CurrencyWindow(Page):
    def __init__(self, app):
        super().__init__(app.root)
        self.app = app
        self.title("Languages & currency")
        self.configure(bg=PAPER, padx=32, pady=24)
        self.resizable(False, False)
        L(self, "Languages & currency", 16, "bold", family="Georgia").pack(anchor="w")

        tk.Frame(self, bg=LINE, height=1).pack(fill="x", pady=14)
        L(self, "Language", 11, "bold").pack(anchor="w")
        L(self, "English (United States)", 10).pack(anchor="w", pady=(4, 0))
        L(self, "More languages are coming soon.", 9, fg=MUTED).pack(anchor="w")

        tk.Frame(self, bg=LINE, height=1).pack(fill="x", pady=14)
        L(self, "Currency", 11, "bold").pack(anchor="w")
        self.v = tk.StringVar(value=CUR["code"])
        for code, (sym, rate, label) in db.CURRENCIES.items():
            tk.Radiobutton(self, text=label, value=code, variable=self.v, command=self.apply,
                           bg=PAPER, activebackground=PAPER, font=("Arial", 10), anchor="w",
                           cursor="hand2").pack(anchor="w", pady=2)
        php_sym, php_rate, _ = db.CURRENCIES["PHP"]
        L(self, f"1 US dollar = {php_sym}{php_rate:,.2f}  (fixed demo rate, not a live one)", 9,
          fg=MUTED).pack(anchor="w", pady=(6, 0))
        self.note = L(self, "", 9, "bold", fg="#2F6B3A")
        self.note.pack(anchor="w", pady=(8, 0))
        button(self, "Done", self.destroy, False).pack(anchor="w", pady=(14, 0))
        self.show_note(False)

    def show_note(self, changed):
        if self.app.user:
            self.note.config(text="\u2713 Saved to your account." if changed else
                             "Your choice is saved to your account.", fg="#2F6B3A" if changed else MUTED)
        else:
            self.note.config(text="Log in to save this choice to your account.", fg=MUTED)

    def apply(self):
        self.app.set_currency(self.v.get())
        self.show_note(True)


class ProfileWindow(Page):
    FIELDS = [("name", "Full name *"), ("phone", "Phone number *"), ("address", "Street address *"),
              ("city", "City *"), ("country", "Country *"), ("birthdate", "Date of birth * (YYYY-MM-DD)"),
              ("emergency_name", "Emergency contact name"), ("emergency_phone", "Emergency contact phone")]

    def __init__(self, app):
        super().__init__(app.root)
        self.app = app
        self.title("Profile")
        self.configure(bg=PAPER, padx=34, pady=22)
        self.resizable(False, False)
        u = app.user

        head = tk.Frame(self, bg=PAPER)
        head.pack(fill="x")
        self.av = tk.Canvas(head, width=96, height=96, bg=PAPER, highlightthickness=0)
        self.av.pack(side="left")
        side = tk.Frame(head, bg=PAPER)
        side.pack(side="left", padx=18)
        L(side, u["email"], 10, fg=MUTED).pack(anchor="w")
        L(side, f"Account type: {u['role']}", 10, "bold", fg=CLAY).pack(anchor="w", pady=(2, 8))
        btns = tk.Frame(side, bg=PAPER)
        btns.pack(anchor="w")
        button(btns, "Change photo", self.pick_photo, small=True).pack(side="left")
        button(btns, "Remove", self.remove_photo, False, small=True).pack(side="left", padx=6)
        self.draw_avatar()

        self.status = L(self, "", 10, "bold", wraplength=420, justify="left")
        self.status.pack(anchor="w", pady=(16, 4))

        form = tk.Frame(self, bg=PAPER)
        form.pack(anchor="w")
        self.v = {}
        for i, (key, label) in enumerate(self.FIELDS):
            L(form, label, 9, fg=MUTED).grid(row=i * 2, column=0, sticky="w", pady=(6, 0))
            self.v[key] = tk.StringVar(value=u.get(key) or "")
            ttk.Entry(form, textvariable=self.v[key], width=48).grid(row=i * 2 + 1, column=0, sticky="w")
        L(self, "* needed to book a stay. Hosts you book with can see your name and phone number.", 8,
          fg=MUTED, wraplength=420, justify="left").pack(anchor="w", pady=(10, 0))
        button(self, "Save profile", self.save).pack(anchor="w", pady=(12, 0))
        self.paint_status()

    def draw_avatar(self):
        u = self.app.user
        self.av.delete("all")
        ph = avatar_photo(u, 96)
        if ph is not None:
            self.av.photo = ph
            self.av.create_image(48, 48, image=ph)
        else:
            self.av.create_oval(2, 2, 94, 94, fill=PILL_BG, outline="")
            self.av.create_text(48, 48, text=u["name"][:1].upper(), fill=CLAY_DEEP, font=("Arial", 32, "bold"))

    def paint_status(self):
        missing = db.profile_missing(self.app.user)
        if missing:
            self.status.config(text="Missing for booking: " + ", ".join(missing), fg=CLAY_DEEP)
        else:
            self.status.config(text="\u2713 Profile complete. You're ready to book.", fg="#2F6B3A")

    def pick_photo(self):
        path = filedialog.askopenfilename(
            parent=self, title="Choose a profile photo",
            filetypes=[("Pictures", "*.png *.jpg *.jpeg *.gif *.bmp *.webp"), ("All files", "*.*")])
        if not path:
            return
        try:
            name = save_avatar(self.app.user["id"], path)
            db.set_avatar(self.app.user["id"], name)
        except db.AppError as e:
            return messagebox.showerror("Profile photo", str(e), parent=self)
        self.app.reload_user()
        self.draw_avatar()

    def remove_photo(self):
        if not self.app.user.get("avatar"):
            return
        try:
            (AVATAR_DIR / self.app.user["avatar"]).unlink()
        except OSError:
            pass
        db.set_avatar(self.app.user["id"], "")
        self.app.reload_user()
        self.draw_avatar()

    def save(self):
        v = {k: var.get() for k, var in self.v.items()}
        try:
            db.update_profile(self.app.user["id"], v["name"], v["phone"], v["address"], v["city"],
                              v["country"], v["birthdate"], v["emergency_name"], v["emergency_phone"])
        except db.AppError as e:
            return messagebox.showerror("Profile", str(e), parent=self)
        self.app.reload_user()
        self.draw_avatar()
        self.paint_status()
        messagebox.showinfo("Profile", "Profile saved.", parent=self)


class AccountWindow(Page):
    def __init__(self, app):
        super().__init__(app.root)
        self.app = app
        self.title("Account settings")
        self.configure(bg=PAPER, padx=30, pady=22)
        self.resizable(False, False)
        L(self, "Account settings", 16, "bold", family="Georgia").pack(anchor="w")
        L(self, "Your name, phone and address live under Profile.", 9, fg=MUTED).pack(anchor="w", pady=(2, 0))
        tk.Frame(self, bg=LINE, height=1).pack(fill="x", pady=14)
        L(self, "Change password", 10, "bold").pack(anchor="w")
        self.v_old, self.v_new, self.v_new2 = tk.StringVar(), tk.StringVar(), tk.StringVar()
        for label, var in (("Current password", self.v_old), ("New password", self.v_new),
                           ("Repeat new password", self.v_new2)):
            L(self, label, 9, fg=MUTED).pack(anchor="w", pady=(8, 0))
            ttk.Entry(self, textvariable=var, show="*", width=34).pack(anchor="w")
        button(self, "Update password", self.save_password).pack(anchor="w", pady=(12, 0))

    def save_password(self):
        if self.v_new.get() != self.v_new2.get():
            return messagebox.showerror("Account", "The new passwords don't match.", parent=self)
        try:
            db.change_password(self.app.user["id"], self.v_old.get(), self.v_new.get())
        except db.AppError as e:
            return messagebox.showerror("Account", str(e), parent=self)
        self.v_old.set("")
        self.v_new.set("")
        self.v_new2.set("")
        messagebox.showinfo("Account", "Password updated.", parent=self)
