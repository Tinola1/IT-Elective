"""The shared UI toolkit for the screens.

extras.py (admin + reviews), payments.py (payment screens) and datepicker.py (the calendar) were written to be
plugged into one shared namespace: each has an install(namespace) function that reads the colours and helpers it
needs from that namespace and adds its own screens to it. This module IS that namespace. It pulls in the
colours and helpers, lets the three plug-ins install themselves, and then the pages import everything they need
from here, for example:

    from toolkit import DateGuestBlock, PaymentPicker, reviews_section

Import this module before using any of the plug-in screens.
"""
import datepicker
import extras
import payments
from content import CANCELLED_BY
from helpers import (L, _cur, booking_ref, button, clear, fmt_day, fmt_night, fmt_range, fmt_when, link, make_tree,
                     money, money0, selected_id, to_usd)
from images import delete_photo_file
from navigation import Page, front_window
from theme import CARD, CLAY, CLAY_DEEP, INK, LINE, MUTED, PAPER, PAPER2, PILL_BG, STATUS_STYLE

# The names above are what the three plug-ins ask for. These calls add the plug-in screens to this module.
extras.install(globals())       # AdminWindow, ReviewDialog, reviews_section, review_for_booking
payments.install(globals())     # PaymentsWindow, PaymentPicker, PayoutsWindow, AddPaymentDialog, payment_details, ...
datepicker.install(globals())   # DatePopup, DateGuestBlock, booked_nights

_NEEDED = ("CARD CLAY CLAY_DEEP INK L LINE MUTED PAPER PAPER2 PILL_BG Page ReviewDialog STATUS_STYLE _cur booking_ref "
           "button clear delete_photo_file fmt_day fmt_night fmt_range fmt_when front_window link make_tree money "
           "money0 selected_id to_usd").split()
_missing = [n for n in _NEEDED if n not in globals()]
if _missing:  # fail loudly at start-up instead of deep inside a window
    raise ImportError("toolkit is missing names the plug-ins need: " + ", ".join(_missing))
