"""The seeded demo workspace (created by `scripts/seed_demo.py`).

Its starter questions live here, and the API offers them for the workspace flagged `is_demo`
only (it was matched by name before step 18; `db.session` flags the old row once). They are
written against the files in `demo_data/`: one sets up a follow-up (implant cost, then "can I
pay monthly?") and the last one is deliberately not covered by the documents, to show the
refusal.
"""

DEMO_WORKSPACE_NAME = "Demo: BrightSmile Dental"

DEMO_STARTER_QUESTIONS = (
    "What are your opening hours on Saturday?",
    "How much does a dental implant cost?",
    "How much notice do I need to cancel an appointment, and is there a fee?",
    "Which insurance plans do you accept?",
    "What should I do if I have a dental emergency at the weekend?",
    "Is there parking at the clinic?",
)


def starter_questions(is_demo: bool) -> list[str]:
    return list(DEMO_STARTER_QUESTIONS) if is_demo else []
