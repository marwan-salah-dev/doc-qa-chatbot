# Retrospective — DocQA Support Agent, Stage 1

**Timeline:** 28 Oct – 1 Nov 2026, 35 commits, 20 planned steps plus a demo milestone. Step 21 (deploy) was deferred: the portfolio is the repo, screenshots and a demo video.

**Result:** a document Q&A agent with streamed, cited answers over PDF, DOCX and TXT, a citation preview panel, a seeded demo workspace, Docker Compose for a 2 GB VPS, public-demo hardening, retrieval and answer evals, and CI. All of it runs without paid API calls in tests.

## What went well

- **A written plan with small, testable steps.** [PLAN.md](PLAN.md) held the decisions, the architecture and a checklist. Each step ended with tests, lint and type checks passing, a plain-English explanation and a suggested commit. Nothing was half-built when a step closed.
- **Fakes for every paid service.** `FakeEmbedder` and `FakeChat` sit behind `Embedder` and `ChatModel` Protocols, so the whole suite runs offline and free, CI included (`HF_HUB_OFFLINE=1`).
- **Guard rails from step 1.** `.claude/settings.json` denied `.env` reads and asked before installs. ruff, pytest and (from step 4) pyright ran at every step, so problems were caught while the change was small.
- **Configuration guarded by tests.** `test_config.py` checks every setting is in `.env.example`; `test_docker_config.py` and `test_ci_config.py` guard the single worker, the trusted proxy subnet, pinned actions and no secrets in CI. Refactors couldn't quietly break deployment rules.
- **A demo-ready milestone in the middle of the plan.** Pulling the seeded demo workspace and `scripts\dev.ps1` forward meant there was something recordable after step 14, and it exposed real bugs (the PDF footer, the score threshold) early.
- **Measuring instead of guessing.** The eval in step 19 (34 golden questions, hit@k, score distributions) turned the `RAG_MIN_SCORE` debate into numbers, and the decision and its reasoning are recorded in code and docs.
- **Bundle discipline.** Lazy routes and vendor chunks cut the main frontend chunk from 690 kB to 51 kB; pdf.js (600 kB) loads only when a PDF citation opens.

## Problems we hit and how we fixed them

| Problem | What happened | Fix | Lesson |
| --- | --- | --- | --- |
| **PyMuPDF is AGPL** | PyMuPDF is the usual first pick for PDF text and layout, but its AGPL licence would oblige clients who reuse the code to open their own source. | Switched to **pypdf (BSD)** for the parser (b42fe37) and wrote the no-GPL/AGPL rule into CLAUDE.md (2b4af9f). Later licence checks covered bge-small (MIT), react-pdf (MIT) and sonner (MIT). | Check the licence *before* a dependency enters the plan, not after code depends on it. |
| **Embedding token limit vs chunk size** | MiniLM truncates input at 256 tokens without warning, so 350-token chunks would lose their tails. With bge-small (512), the cheap "4 characters per token" estimate still under-counted codes and digits: a real chunk came to 828 tokens against a 512 limit. | Chose **bge-small-en-v1.5** for its 512 limit. The chunker takes an injected `count_tokens`, and ingestion passes the embedder's **real tokenizer**. `ensure_chunk_fits` checks the setting at startup, and a safety net splits any chunk the counter still rejects (a4b240f, 45aa581). | Read the model's real input limit and count with its real tokenizer. Silent truncation never shows up as an error, only as worse answers. |
| **Heavy dependencies** | On Linux the default torch wheel pulls several GB of `nvidia-*` CUDA packages. The model downloaded at start-up. pdf.js alone is 600 kB. slowapi would have added 3 packages and didn't fit the SSE route. | CPU-only torch index for Linux in `pyproject.toml`; the model baked into the image and run with `HF_HUB_OFFLINE=1`; reportlab kept dev-only; pdf.js lazy-loaded; an in-process sliding-window rate limiter instead of slowapi (d1e1c15, 85dd0d2). The backend image is still 2.81 GB. | Judge a dependency by install size, transitive packages and production image size, not only by features. Prefer the standard library when the need is small. |
| **Windows PATH and shell quirks** | uv was installed through winget, but shells opened before the install didn't have `uv` on PATH. `curl` in PowerShell is `Invoke-WebRequest`. `localhost` tried `::1` first while uvicorn listened on IPv4 only, so health checks hung. PowerShell 5.1 has no `&&`. | `scripts\dev.ps1` checks each tool is on PATH and says "open a new terminal after installing". Scripts and docs use `127.0.0.1` and `curl.exe`. The PowerShell rules went into CLAUDE.md's plan self-review (04ec102, 5c8bdf5). | After installing a tool, open a new terminal. Write Windows rules down on day 1, not after the first hang. |
| **Score threshold refused real questions** | "Which insurance plans do you accept?" scored 0.483 and was refused by the 0.5 cut-off before the LLM saw it. | Lowered `RAG_MIN_SCORE` to 0.45 (1fe73e0), then re-checked it with the step 19 eval rather than by feel. | Tune thresholds against a golden set, and err towards letting the LLM's own refusal be the backstop. |
| **One chunk per small document** | Short multi-topic demo files indexed as one chunk each, so retrieval couldn't tell sections apart. | Section-aware chunking: PDF headings by font size (and later bold headings), DOCX headings, TXT `Q:` pairs. The demo went from 3 chunks to 21 (17cd04c, f0e0429). | Look at what actually gets indexed early, with real documents. |
| **Repeated PDF footer** | The demo PDF's per-page disclaimer led every page's chunk and every citation preview. | Moved the disclaimer to one closing line; the seed now replaces demo files whose hash changed (0101257). | Inspect parsed text, not just the rendered file. |
| **Groq free tier (8K tokens/min)** | Follow-up questions with history and sources could exceed the per-minute limit. | `RAG_TOKEN_BUDGET` fits the whole call, trimming history before sources; live tests wait about 60 s between questions; a daily token cap protects the public demo. | Put provider rate limits into the design and the test routine from the first LLM step. |
| **Model output quirks** | gpt-oss wrote citations as `【1】` / `【1†source】` and used narrow no-break spaces, so answers were flagged uncited. | Normalised both before parsing (2faf0f3, 17cd04c). | Test with the real model early; fake models only cover the format you expect. |
| **Chroma evicted small indexes** | Chroma 1.5.9 keeps indexes under 1000 vectors only in memory, and the embedded client's pool on Windows was about 1 slot, so two workspaces could collide ("Nothing found on disk"). | Sized the pool like Chroma's server does, routed every client through one factory, pinned `chromadb==1.5.9`, and added a 150-workspace regression test (dab2f9f). | Pin libraries whose internals you patch or depend on, and add a regression test that would catch an upgrade. |
| **Tooling friction** | Vitest runs could hang, and `npx` can download and run any package. | `npm run test` with a 10 s test timeout; every `npx` stays behind a prompt (7fc76da). | Run tools through project scripts with timeouts, and keep download-and-run commands behind approval. |
| **Personal email in commits** | Every commit originally used a personal email address. | The history was rewritten so every commit uses the GitHub noreply address before publishing (step 20). | Set the noreply email in the repo before the first commit; a history rewrite later is avoidable risk. |

## What to do differently next time

1. **Set the git identity first.** Use the GitHub noreply email in `git config user.email` before the first commit.
2. **Licence and size check in the plan.** Every dependency in the plan gets a licence, its install and image size, and dev or runtime. No GPL/AGPL.
3. **Read real limits up front.** Model input limits, provider rate limits and free-tier quotas go into the plan's decisions, and the code counts with real tokenizers.
4. **Build a small golden set early.** Ten questions with expected sources by the time retrieval works, grown into the full eval later, so thresholds and chunking are measured from the start.
5. **Look at the indexed data.** A quick script that prints chunks and their locations for the demo documents would have caught the footer and the one-chunk-per-file issue days earlier.
6. **Test against the real model once per LLM step,** spaced for the rate limit, to catch output quirks that fakes can't.
7. **Windows rules from day 1:** `curl.exe`, `127.0.0.1`, no `&&` in PowerShell 5.1, and a new terminal after installs.
8. **Plan the portfolio from the start.** List the screenshots and the demo script when the demo milestone is planned, not after the last step.
9. **Pin what you patch.** Any dependency we work around gets an exact version pin and a regression test.
