"""The fixed copy shown on the site: landing-page text, FAQ, footer links and policy blurbs."""




STATUS_BLURB = {
    "confirmed": "Your reservation is finalized and booked. No further action is needed until check-in.",
    "pending": "Waiting for the host to accept your request. They have 24 hours to respond. "
               "You can withdraw it any time before it's confirmed, with no penalty.",
    "cancelled": "This reservation was cancelled. The details and refund are below."}


CANCELLED_BY = {"guest": "You", "host": "The host", "system": "RoamRest (automatic)"}


TAGS = {"Cabins & lodges": "Fireplaces, forests, quiet.", "Beachfront": "Wake up to the water.",
        "City lofts": "Walk everywhere.", "Villas & pools": "Room for the whole crew.",
        "Countryside": "Slow mornings, fresh eggs.", "Unique stays": "Beds in the branches."}


STATS = [("10K+", "stays booked this year"), ("4.9", "average guest rating"),
         ("$2.4M", "paid out to hosts"), ("190+", "cities & counting")]


STEPS = [("01", "Find your kind of place",
          "Filter by what actually matters \u2014 Wi-Fi speed, a real kitchen, workspace, pet-friendly. "
          "Every listing shows the all-in price before you click."),
         ("02", "Book without the gamble",
          "Reserve in two taps. Your payment sits in escrow until 24 hours after check-in, and most "
          "stays cancel free up to 5 days before arrival."),
         ("03", "Arrive like you live there",
          "Check-in details, the Wi-Fi code and your host's local tips land in your inbox before you "
          "pack. 24/7 support if anything's off.")]


PILLARS = [("Verified before it's ever listed",
            "Every property passes a 42-point check \u2014 photos confirmed, amenities tested, host ID "
            "verified \u2014 before it goes live. If a listing slips below a 4.3 rating, it's delisted.",
            "Fewer than 8% of applications make it live"),
           ("The price you see is the price you pay",
            "Nightly rate, service fee, taxes \u2014 everything's bundled into one number upfront. No "
            "cleaning-fee ambush at checkout. Ever. Payments are held in escrow until you've checked in.",
            "$0 in surprise fees across 10,000+ bookings"),
           ("Humans answer in minutes, not days",
            "24/7 support with a median response time of three minutes. If a stay goes sideways and "
            "can't be fixed within the hour, we rebook you or refund you \u2014 your call.",
            "3-minute median response, day or night")]


REVIEWS = [("Maya R.", "Alfama Skyline Loft \u00B7 Lisbon",
            "I booked from the airport in about four minutes. The price on the card was the price I paid "
            "\u2014 no cleaning-fee ambush at checkout. First time a booking site hasn't made me feel "
            "nickeled-and-dimed."),
           ("Daniel & Priya K.", "Machiya House \u00B7 Kyoto",
            "The photos honestly undersold it. Every detail was thought through \u2014 the kitchen, the "
            "record player, handwritten notes about the neighbourhood. It felt like borrowing a friend's home."),
           ("Tom W.", "Olive Grove Villa \u00B7 Puglia",
            "The water heater died on night two. I messaged support at 11pm and got a human in three "
            "minutes. By the next evening we'd been moved to a comparable villa with one night refunded.")]


FAQ = [("How do bookings and payments work?",
        "Once a host accepts your request (they have 24 hours to respond), your card is charged and the money is "
        "held in escrow \u2014 the host isn't paid until 24 hours after you've checked in. If your request "
        "isn't accepted, you're never charged."),
       ("What's the cancellation policy?",
        "Most bookings are free to cancel within 48 hours of making it (Strict listings need check-in 14+ days away). Beyond that, each listing shows its "
        "policy upfront \u2014 Flexible, Moderate or Strict. The refund math is shown before you confirm."),
       ("How do you verify hosts and properties?",
        "Government ID for every host, plus a 42-point property review. Fewer than 8% of applications make "
        "it live, and listings that fall below a 4.3 rating get delisted."),
       ("What if something goes wrong mid-stay?",
        "Message support \u2014 a human, median response three minutes, any hour. If we can't fix it within "
        "the hour, we move you to a comparable stay or refund the remaining nights."),
       ("What fees does RoamRest charge?",
        "One flat service fee, always included inside the nightly price you first see. Hosts pay a flat 3%. "
        "That's the entire pricing model.")]


POLICIES = {
    "Terms": "RoamRest connects guests with independent hosts. Bookings are agreements with the host; "
             "RoamRest handles payments, verification and support. Hosts pay a flat 3% fee.",
    "Privacy": "We collect only what's needed to run a safe marketplace: account details and booking "
               "history. Passwords are stored hashed. We never sell personal data.",
    "Safety": "Every host is verified and every property reviewed before going live. Listings below a "
              "4.3 rating are delisted.",
    "Cookies": "This desktop app does not use cookies."}


FOOT_COLS = [("EXPLORE", [("All stays", ("cat", "All")), ("Cabins & lodges", ("cat", "Cabins & lodges")),
                          ("Beachfront", ("cat", "Beachfront")), ("City lofts", ("cat", "City lofts"))]),
             ("HOSTING", [("List your space", ("go", "host")), ("Earnings calculator", ("go", "host")),
                          ("Host fees, explained", ("go", "faq"))]),
             ("SUPPORT", [("Help centre", ("go", "faq")), ("Cancellation policy", ("go", "faq")),
                          ("support@roamrest.com", None)]),
             ("COMPANY", [("About RoamRest", ("go", "why")), ("How it works", ("go", "how")),
                          ("Traveler reviews", ("go", "reviews"))])]
