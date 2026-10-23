"""Colours, sizes and the ttk look shared by every RoamRest window."""

from tkinter import ttk


PAPER, PAPER2, CARD, INK, MUTED = "#F4EEE1", "#FAF5E9", "#FFFDF6", "#232015", "#6B6353"


CLAY, CLAY_DEEP, LINE, GREEN = "#B44A1E", "#8F3A13", "#E1D7C0", "#20362A"


PILL_BG, APRICOT, FOOT = "#F0DDD0", "#E9A170", "#232015"


CARD_W, IMG_H, ROW_W = 230, 215, 1100  # stay card photo size and the width of one row


# trip status -> (label, text color, background color)
STATUS_STYLE = {"confirmed": ("Confirmed", "#2F6B3A", "#E1EFE2"),
                "pending": ("Pending", "#8A5A00", "#FBEBC8"),
                "cancelled": ("Cancelled", "#9B2C2C", "#F6DADA")}


def apply_theme(root):
    """One warm RoamRest look for every ttk widget (tables, inputs, scrollbars, tabs) so all windows match."""
    st = ttk.Style(root)
    st.theme_use("clam")  # the only built-in theme that lets tables and inputs be recoloured properly
    base = ("Arial", 10)
    st.configure(".", background=PAPER, foreground=INK, font=base, bordercolor=LINE,
                 troughcolor=PAPER2, focuscolor=PAPER)
    st.configure("TFrame", background=PAPER)
    st.configure("TLabel", background=PAPER, foreground=INK)
    st.configure("TCheckbutton", background=PAPER, foreground=INK)
    st.map("TCheckbutton", background=[("active", PAPER)])
    st.configure("TLabelframe", background=PAPER, bordercolor=LINE, relief="solid")
    st.configure("TLabelframe.Label", background=PAPER, foreground=MUTED, font=("Arial", 9, "bold"))

    # inputs: white field, soft border, clay border while focused
    for name in ("TEntry", "TCombobox", "TSpinbox"):
        st.configure(name, fieldbackground="white", foreground=INK, bordercolor=LINE, lightcolor=LINE,
                     darkcolor=LINE, insertcolor=INK, padding=(8, 6))
        st.map(name, bordercolor=[("focus", CLAY)], lightcolor=[("focus", CLAY)],
               darkcolor=[("focus", CLAY)])
    st.configure("TCombobox", arrowcolor=MUTED, background=LINE)
    st.map("TCombobox", fieldbackground=[("readonly", "white")], foreground=[("readonly", INK)],
           selectbackground=[("readonly", "white")], selectforeground=[("readonly", INK)],
           background=[("active", "#D3C7AA"), ("readonly", LINE)])
    root.option_add("*TCombobox*Listbox.background", "white")
    root.option_add("*TCombobox*Listbox.foreground", INK)
    root.option_add("*TCombobox*Listbox.selectBackground", PILL_BG)
    root.option_add("*TCombobox*Listbox.selectForeground", INK)
    root.option_add("*TCombobox*Listbox.font", base)

    # tables: roomy rows, quiet header, soft apricot selection
    st.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])  # no ugly focus border
    st.configure("Treeview", background=CARD, fieldbackground=CARD, foreground=INK, rowheight=32,
                 borderwidth=0, relief="flat", font=base)
    st.map("Treeview", background=[("selected", PILL_BG)], foreground=[("selected", INK)])
    st.configure("Treeview.Heading", background="#EFE6D2", foreground=MUTED, font=("Arial", 9, "bold"),
                 relief="flat", borderwidth=0, padding=(8, 8))
    st.map("Treeview.Heading", background=[("active", "#E6DBC2")])

    # slim scrollbar without arrow buttons
    st.layout("Vertical.TScrollbar", [("Vertical.Scrollbar.trough", {"sticky": "ns", "children": [
        ("Vertical.Scrollbar.thumb", {"expand": "1", "sticky": "nswe"})]})])
    st.configure("Vertical.TScrollbar", background=LINE, troughcolor=PAPER2, bordercolor=PAPER2,
                 lightcolor=LINE, darkcolor=LINE, gripcount=0, width=10)
    st.map("Vertical.TScrollbar", background=[("active", "#CDBF9F"), ("pressed", "#BFB08C")])

    # tabs (admin window)
    st.configure("TNotebook", background=PAPER, borderwidth=0)
    st.configure("TNotebook.Tab", background=LINE, foreground=MUTED, padding=(16, 7), borderwidth=0)
    st.map("TNotebook.Tab", background=[("selected", CARD)], foreground=[("selected", INK)])
