"""Messages between guests and hosts."""

import tkinter as tk
from tkinter import messagebox
from tkinter import ttk

import database as db
from helpers import L, button, clear, fmt_when
from navigation import Page
from theme import CARD, LINE, MUTED, PAPER, PILL_BG


class MessagesWindow(Page):
    def __init__(self, app):
        super().__init__(app.root)
        self.app = app
        self.title("Messages")
        self.geometry("960x600")
        self.minsize(780, 440)
        self.configure(bg=PAPER)
        self.convs = {}      # row id "listing:guest" -> conversation info
        self.cur = None      # row id of the open conversation
        self.draft = None    # a conversation started from a button that has no messages yet
        self._loading = False

        left = tk.Frame(self, bg=PAPER, padx=14, pady=14)
        left.pack(side="left", fill="y")
        L(left, "Messages", 18, "bold", family="Georgia").pack(anchor="w", pady=(0, 8))
        frame = ttk.Frame(left)
        frame.pack(fill="y", expand=True)
        self.tree = ttk.Treeview(frame, columns=("chat", "new"), show="headings", height=18,
                                 selectmode="browse")
        self.tree.heading("chat", text="Conversation", anchor="w")
        self.tree.heading("new", text="", anchor="w")
        self.tree.column("chat", width=270, anchor="w")
        self.tree.column("new", width=46, anchor="w")
        sb = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="y", expand=True)
        sb.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self.on_select)

        right = tk.Frame(self, bg=PAPER, padx=6, pady=14)
        right.pack(side="left", fill="both", expand=True)
        self.head = L(right, "Select a conversation", 13, "bold", family="Georgia", wraplength=520, justify="left")
        self.head.pack(anchor="w", pady=(0, 8))
        tbox = tk.Frame(right, bg=PAPER)
        tbox.pack(fill="both", expand=True)
        self.text = tk.Text(tbox, wrap="word", state="disabled", bg=CARD, relief="flat",
                            font=("Arial", 10), padx=10, pady=10, highlightbackground=LINE,
                            highlightthickness=1, cursor="arrow")
        tsb = ttk.Scrollbar(tbox, orient="vertical", command=self.text.yview)
        self.text.configure(yscrollcommand=tsb.set)
        tsb.pack(side="right", fill="y")
        self.text.pack(side="left", fill="both", expand=True)
        self.text.tag_configure("me", background=PILL_BG, lmargin1=140, lmargin2=140, rmargin=8)
        self.text.tag_configure("them", background="#EDE6D6", lmargin1=8, lmargin2=8, rmargin=140)
        self.text.tag_configure("meta_me", justify="right", foreground=MUTED, font=("Arial", 8),
                                lmargin1=140, lmargin2=140, rmargin=8, spacing1=6)
        self.text.tag_configure("meta_them", foreground=MUTED, font=("Arial", 8),
                                lmargin1=8, lmargin2=8, rmargin=140, spacing1=6)

        compose = tk.Frame(right, bg=PAPER)
        compose.pack(fill="x", pady=(10, 0))
        self.box = tk.Text(compose, height=3, wrap="word", font=("Arial", 10), relief="flat",
                           highlightbackground=LINE, highlightthickness=1)
        self.box.pack(side="left", fill="x", expand=True)
        self.box.bind("<Return>", lambda e: self.send())
        self.box.bind("<Shift-Return>", lambda e: None)  # Shift+Enter keeps its normal new line
        button(compose, "Send", self.send).pack(side="left", padx=(10, 0), fill="y")
        L(right, "Enter sends  \u00B7  Shift+Enter adds a new line", 8, fg=MUTED).pack(anchor="w", pady=(4, 0))

        self.refresh()

    # ----- list
    def refresh(self):
        self.load_list()
        self.show_thread()

    def load_list(self):
        uid = self.app.user["id"]
        self._loading = True
        rows = [dict(r) for r in db.conversations(uid)]
        self.convs = {}
        clear(self.tree)
        if self.draft and not any(r["listing_id"] == self.draft["listing_id"]
                                  and r["guest_id"] == self.draft["guest_id"] for r in rows):
            rows.insert(0, dict(self.draft, unread=0))
        for r in rows:
            iid = f"{r['listing_id']}:{r['guest_id']}"
            other = r["host_name"] if uid == r["guest_id"] else r["guest_name"]
            r["other"] = other
            self.convs[iid] = r
            self.tree.insert("", "end", iid=iid, values=(
                f"{other} \u2014 {r['title']}", f"\u25CF {r['unread']}" if r["unread"] else ""))
        if self.cur and self.tree.exists(self.cur):
            self.tree.selection_set(self.cur)
        self._loading = False

    def on_select(self, _e=None):
        if self._loading:
            return
        sel = self.tree.selection()
        if sel and sel[0] != self.cur:
            self.cur = sel[0]
            self.show_thread()

    # ----- thread
    def show_thread(self):
        t = self.text
        t.config(state="normal")
        t.delete("1.0", "end")
        info = self.convs.get(self.cur)
        if not info:
            self.head.config(text="Select a conversation")
            if not self.convs:
                t.insert("end", "No messages yet.\n\nUse \u201CContact host\u201D on a stay, or "
                                "\u201CMessage guest\u201D in Hosting, to start a conversation.")
            t.config(state="disabled")
            return
        uid = self.app.user["id"]
        try:
            msgs = db.thread(uid, info["listing_id"], info["guest_id"])
        except db.AppError as e:
            t.config(state="disabled")
            return messagebox.showerror("Messages", str(e), parent=self)
        self.head.config(text=f"{info['other']}  \u00B7  {info['title']}")
        if not msgs:
            t.insert("end", f"Say hello to {info['other']}. They'll see your message next time they "
                            "open Messages.")
        for m in msgs:
            mine = m["sender_id"] == uid
            who = "You" if mine else m["sender_name"]
            t.insert("end", f"{who} \u00B7 {fmt_when(m['created_at'])}\n", "meta_me" if mine else "meta_them")
            t.insert("end", m["body"] + "\n", "me" if mine else "them")
        t.config(state="disabled")
        t.see("end")
        if self.tree.exists(self.cur):
            self.tree.set(self.cur, "new", "")
        self.app.refresh_nav()  # the unread number in the header

    def open_thread(self, listing_id, guest_id):
        info = db.conversation_info(self.app.user["id"], listing_id, guest_id)
        self.draft = {"listing_id": listing_id, "guest_id": guest_id, "title": info["title"],
                      "host_id": info["host_id"], "host_name": info["host_name"],
                      "guest_name": info["guest_name"], "last_body": "", "last_at": ""}
        self.cur = f"{listing_id}:{guest_id}"
        self.load_list()
        self.show_thread()
        self.box.focus_set()

    def send(self):
        info = self.convs.get(self.cur)
        if not info:
            messagebox.showinfo("Messages", "Select a conversation first.", parent=self)
            return "break"
        try:
            db.send_message(self.app.user["id"], info["listing_id"], info["guest_id"], self.box.get("1.0", "end"))
        except db.AppError as e:
            messagebox.showerror("Messages", str(e), parent=self)
            return "break"
        self.box.delete("1.0", "end")
        self.load_list()
        self.show_thread()
        return "break"
