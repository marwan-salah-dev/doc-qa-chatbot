"""The seeded demo workspace (created by `scripts/seed_demo.py`).

Its starter questions live here, beside the name that identifies it, so the API can offer them
for that workspace only. They are written against the files in `demo_data/`: one sets up a
follow-up (implant cost, then "can I pay monthly?") and the last one is deliberately not covered
by the documents, to show the refusal.
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


def starter_questions(workspace_name: str) -> list[str]:
    return list(DEMO_STARTER_QUESTIONS) if workspace_name == DEMO_WORKSPACE_NAME else []
