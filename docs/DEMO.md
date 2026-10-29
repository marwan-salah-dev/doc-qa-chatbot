# Demo recording script (60-90 seconds)

A short screen recording of the seeded **Demo: BrightSmile Dental** workspace (a fictional clinic). It shows grounded answers, a clickable citation, a follow-up question and the refusal.

## Before you record

1. Start everything with one command from the repo root:
   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts\dev.ps1
   ```
   It starts the backend and frontend in their own windows, waits for the API, and seeds the demo workspace (rerunning it never duplicates anything).
2. Open http://localhost:5173 and switch to **Demo: BrightSmile Dental**. All three documents should show **Ready**:
   - `brightsmile-patient-handbook.pdf`
   - `brightsmile-price-list.docx`
   - `brightsmile-faq.txt`
3. **Delete old test chats** in the conversation list (the trash icon on each one), so the recording starts from an empty list and shows the starter-question chips.
4. Use a clean browser window at a readable zoom (about 110-125%), and hide bookmarks and other tabs.
5. **Rate limit:** Groq's free tier allows about 8K tokens per minute, and one answer can use about 5.5K. **Wait about 60 seconds between questions** while recording, then cut the pauses in editing. A 429 "rate limit" error means you asked too soon. It is not a bug: wait and press Retry.

## Shot list

| # | Time (after cuts) | Action | Say (optional voice-over) |
|---|---|---|---|
| 1 | 0:00-0:10 | Show the demo workspace: the three **Ready** documents on the left and the empty chat with its suggested questions. | "This is a support agent for a dental clinic. It answers only from the clinic's own documents: a PDF handbook, a Word price list and a text FAQ." |
| 2 | 0:10-0:22 | Click the chip **What are your opening hours on Saturday?** and let the answer stream in (9:00 am to 1:00 pm). | "Answers stream in, and every claim has a numbered citation." |
| 3 | 0:22-0:32 | Click the citation chip **1** in the answer (handbook, page 1), so the popover shows the cited passage. | "Clicking a citation shows exactly where the answer came from: the handbook, page 1." |
| 4 | 0:32-0:45 | Click **New chat**, then the chip **How much does a dental implant cost?** ($2,400, from the price list). | "Prices come from the Word price list." |
| 5 | 0:45-1:00 | Type the follow-up **Can I spread that over monthly payments?** and send it. The answer explains the 0% plan ($200 deposit, then monthly instalments) and cites the price list and the handbook. | "Follow-ups keep the context: 'that' means the implant, and the answer combines two documents." |
| 6 | 1:00-1:12 | Click **New chat**, then the chip **Is there parking at the clinic?** It shows **Not found in your documents**. | "And when the documents don't say, it says so instead of making something up." |
| 7 | 1:12-1:20 | Hold on the refusal, or pan back over the conversation list. | "Grounded answers, real citations, no guessing." |

## Notes

- The clinic, its phone numbers (555-01xx), its email (`example.com`) and its street are fictional. "Fictional clinic, created for a software demo." closes the PDF handbook (once, at the end, so it stays out of page citations) and is the DOCX footer (which the parser doesn't read).
- If an answer is refused when it shouldn't be, check that all three documents are **Ready**. Then rerun `scripts\dev.ps1` (or `uv run python -m scripts.seed_demo` from `backend/`), which reindexes any failed file.
- To change the demo content, edit `backend/scripts/demo_content.py`, rebuild the files with `uv run python -m scripts.build_demo_docs`, and commit `backend/demo_data/`. The next seed run sees the changed file (its SHA-256 differs from the stored one) and replaces that document.
