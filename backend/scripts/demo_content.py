"""Everything the BrightSmile Dental demo files say, in one place.

`build_demo_docs` turns this into the PDF handbook, the DOCX price list and the TXT FAQ, so a
fact (a phone number, a fee, a price) is written once and can't drift between files. The clinic
is fictional: the phone numbers are in the reserved 555-01xx range and the email uses
example.com, because the name belongs to real clinics in several countries.

Nothing here mentions parking: the demo's refusal question asks about it.
"""

CLINIC = "BrightSmile Dental"
ADDRESS = "48 Larkspur Avenue, Suite 200, Millbrook"
PHONE = "(555) 555-0147"
EMERGENCY_PHONE = "(555) 555-0199"
EMAIL = "hello@brightsmile.example.com"
WEBSITE = "brightsmile.example.com"
DISCLAIMER = "Fictional clinic, created for a software demo."

CANCELLATION_FEE = "$40"
CHECKUP_PRICE = "$95"
IMPLANT_PRICE = "$2,400"
WHITENING_PRICE = "$350"
CHILD_CHECKUP_PRICE = "$60"
EMERGENCY_EXAM_PRICE = "$135"
PLAN_THRESHOLD = "$1,000"
INSURERS = "Northwind Health, Bluepeak Dental Plans, Harbor Mutual and Evergreen Care"

HANDBOOK_TITLE = f"{CLINIC} Patient Handbook"
HANDBOOK_INTRO = (
    f"Welcome to {CLINIC}. This handbook explains how our clinic works: when we are open, how "
    "to book and cancel, how insurance and payments are handled, what to do in an emergency, "
    f"and how to look after your teeth after treatment. Our clinic is at {ADDRESS}. You can "
    f"reach reception on {PHONE} or by email at {EMAIL}."
)

# (heading, paragraphs). A paragraph starting with "- " is shown as a bullet point.
HANDBOOK_SECTIONS: list[tuple[str, list[str]]] = [
    (
        "1. Opening hours",
        [
            "- Monday to Thursday: 8:00 am to 6:00 pm",
            "- Friday: 8:00 am to 4:00 pm",
            "- Saturday: 9:00 am to 1:00 pm",
            "- Sunday and public holidays: closed",
            "Reception answers the phone from 7:45 am on weekdays. The last appointment of the "
            "day starts 30 minutes before closing time.",
        ],
    ),
    (
        "2. Booking and cancellations",
        [
            f"You can book online at {WEBSITE}, by phone on {PHONE}, or at reception. New "
            "patients should arrive 15 minutes early to complete a medical history form.",
            "We ask for at least 24 hours' notice to cancel or move an appointment. Cancellations "
            f"with less than 24 hours' notice, and missed appointments, are charged a "
            f"{CANCELLATION_FEE} late cancellation fee.",
            "If you miss two appointments within 12 months, we will ask for a $50 deposit to "
            "secure future bookings. The deposit is taken off your bill on the day.",
            "If you are running more than 15 minutes late, we may need to rebook you so that "
            "other patients are not kept waiting.",
        ],
    ),
    (
        "3. Insurance",
        [
            f"We are in network with {INSURERS}. We submit claims to these insurers for you, "
            "and you pay only your co-payment at the end of each visit.",
            "For any treatment over $500 we can request a pre-treatment estimate from your "
            "insurer. Estimates usually come back within 5 business days.",
            "If your insurer is not on this list, you pay for the visit in full and we give you "
            "an itemised receipt to claim back from your insurer yourself.",
            "Please bring your insurance card to every visit and tell us if your plan changes.",
        ],
    ),
    (
        "4. Payments and refunds",
        [
            "We accept debit and credit cards, cash and bank transfer. Payment is due at the end "
            "of each visit.",
            f"Treatments costing more than {PLAN_THRESHOLD}, such as crowns, implants and root "
            "canal treatment, can be paid with our 0% interest payment plan. The plan needs a "
            "$200 deposit, and the rest is split into up to 12 equal monthly instalments. There "
            f"are no fees if the plan is paid on time. For example, a {IMPLANT_PRICE} dental "
            "implant can be paid as a $200 deposit and 11 monthly instalments of $200.",
            "If you cancel prepaid treatment with at least 48 hours' notice, we refund it in full "
            "to the original payment method within 10 business days.",
            "Lab-made items such as crowns, dentures and night guards are made specially for "
            "you, so their cost is not refundable once the lab work has started.",
        ],
    ),
    (
        "5. Dental emergencies",
        [
            "During opening hours, call reception on "
            f"{PHONE}. We keep emergency appointments free every weekday morning, so we can "
            "usually see you the same day.",
            f"Outside opening hours and at weekends, call our emergency line on {EMERGENCY_PHONE}"
            ". It is answered by an on-call dentist from 8:00 am to 8:00 pm on Saturdays, "
            "Sundays and public holidays, who can give advice and open the clinic if needed. An "
            f"emergency examination costs {EMERGENCY_EXAM_PRICE}.",
            "If a tooth is knocked out, hold it by the crown, keep it in milk and see a dentist "
            "within 60 minutes for the best chance of saving it.",
            "For severe facial swelling, bleeding that will not stop, or difficulty breathing or "
            "swallowing, call emergency services or go to the nearest hospital emergency "
            "department straight away.",
        ],
    ),
    (
        "6. Aftercare",
        [
            "- After a filling: wait 2 hours before eating, until the numbness wears off, so you "
            "do not bite your cheek or tongue.",
            "- After an extraction: do not rinse or spit for 24 hours, avoid drinking through a "
            "straw for 72 hours, and eat soft foods for the first few days.",
            "- After teeth whitening: avoid coffee, tea, red wine and other strongly coloured "
            "food and drink for 48 hours.",
            "- After a new crown: avoid sticky and very hard foods for 24 hours.",
            f"If bleeding, pain or swelling gets worse after 48 hours, call us on {PHONE}.",
        ],
    ),
]

PRICE_LIST_TITLE = f"{CLINIC} Price List 2026"
PRICE_LIST_INTRO = (
    "All prices are in US dollars and apply from 1 January 2026. Before any treatment over $500 "
    "we give you a written estimate."
)
# (treatment, price, notes)
PRICES: list[tuple[str, str, str]] = [
    ("New patient examination and X-rays", "$120", "Includes a full set of X-rays"),
    ("Check-up and clean", CHECKUP_PRICE, "Recommended every 6 months"),
    ("Children's check-up (under 12)", CHILD_CHECKUP_PRICE, "Includes fluoride treatment"),
    ("Emergency examination", EMERGENCY_EXAM_PRICE, "Same day where possible"),
    ("Tooth-coloured filling (one surface)", "$160", "Each extra surface $45"),
    ("Simple extraction", "$180", ""),
    ("Surgical wisdom tooth removal", "$420", "Per tooth"),
    ("Root canal treatment (molar)", "$980", "Crown charged separately"),
    ("Porcelain crown", "$1,250", "Two visits; lab-made"),
    ("Dental implant (including crown)", IMPLANT_PRICE, "Three to six months in total"),
    ("In-office teeth whitening", WHITENING_PRICE, "One 90-minute visit"),
    ("Custom night guard", "$290", "Lab-made"),
]
PRICE_LIST_NOTES = [
    f"Treatments over {PLAN_THRESHOLD} can be paid with our 0% interest payment plan over up to "
    "12 months. See the Patient Handbook, section 4, for details.",
    f"Missed appointments and cancellations with less than 24 hours' notice are charged "
    f"{CANCELLATION_FEE}.",
]

FAQ_TITLE = f"{CLINIC} - Frequently asked questions"
FAQ: list[tuple[str, str]] = [
    ("Where is the clinic?", f"We are at {ADDRESS}."),
    (
        "How do I book an appointment?",
        f"Book online at {WEBSITE}, call reception on {PHONE}, or email {EMAIL}.",
    ),
    (
        "What should I bring to my first visit?",
        "Photo ID, your insurance card and a list of any medicines you take. Please arrive 15 "
        "minutes early to fill in a medical history form.",
    ),
    (
        "Do you see children?",
        f"Yes, from age 2. A children's check-up for under-12s costs {CHILD_CHECKUP_PRICE}.",
    ),
    (
        "How much is a check-up and clean?",
        f"A check-up and clean costs {CHECKUP_PRICE}. We recommend one every 6 months.",
    ),
    (
        "Can I cancel or move my appointment?",
        "Yes, with at least 24 hours' notice. Later cancellations and missed appointments are "
        f"charged {CANCELLATION_FEE}.",
    ),
    (
        "Do you accept my insurance?",
        f"We are in network with {INSURERS}. With other insurers you pay in full and claim back "
        "with our itemised receipt.",
    ),
    (
        "I have toothache at the weekend. What should I do?",
        f"Call our emergency line on {EMERGENCY_PHONE}. An on-call dentist answers from 8:00 am "
        "to 8:00 pm on weekends and public holidays.",
    ),
    (
        "Do you offer payment plans?",
        f"Yes. Treatments over {PLAN_THRESHOLD} can be spread over up to 12 months at 0% "
        "interest after a $200 deposit.",
    ),
    (
        "How long does teeth whitening take?",
        f"In-office whitening takes one 90-minute visit and costs {WHITENING_PRICE}.",
    ),
]
