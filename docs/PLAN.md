# Stage 1 Plan — Document Q&A Support Agent

## Context
This is a portfolio project for Upwork: an AI support agent that a business could deploy. In Stage 1, users upload PDF, TXT or DOCX files to a workspace, ask questions, and get streamed answers based only on those documents, with clickable citations. Stage 2 (tool calling, embeddable widget) comes later, so Stage 1's design leaves room for it without building it now.

**Decisions**
- **Workspaces, no login.** Each workspace (for example "Acme Dental") has its own documents, Chroma collection and conversations. Stage 2 widget keys will attach to a workspace.
- **Embeddings can be switched with `EMBEDDING_PROVIDER`:** `local` (sentence-transformers `BAAI/bge-small-en-v1.5`, the default: MIT licence, 384 dimensions, 512-token input limit, so chunks are not silently truncated the way they would be with MiniLM's 256) or `openai` (`text-embedding-3-small`). Chat can be switched with `LLM_PROVIDER=openai|anthropic`, and model names come from env vars.
- **Public live demo** plus the repo, so abuse and cost protection are in scope.
- **Chat UX:** streaming answers, saved history with follow-ups, and a citation preview panel. No OCR.
- **Public demo access:** visitors can use a read-only seeded demo workspace and can create their own temporary workspaces, which expire after 24h and have upload caps. Admin-only operations need `ADMIN_API_KEY`.
- **Citation locations by file type:** a PDF cites the **file + page**. A DOCX cites the **file + nearest heading + paragraph range**. A TXT cites the **file + line range**. The UI labels each one honestly.
- **Tooling:** uv for packages and ruff for lint/format. The frontend uses Tailwind + shadcn/ui and TanStack Query.

## Architecture
```
frontend/ (Vite React TS) ──HTTP/SSE──> backend/ (FastAPI)
                                            ├─ SQLite (workspaces, documents, conversations, messages)
                                            ├─ file storage volume (originals, for preview)
                                            ├─ ChromaDB server (one collection per workspace + embedding model)
                                            └─ LLM provider (OpenAI | Anthropic), Embedder (local | OpenAI)
```
Backend layout: `backend/app/{config.py, main.py, db/, api/routes/, services/{parsers, chunking, embeddings, vectorstore, llm, rag, ingestion}}`, with tests in `backend/tests/`.

Key design points:
- **Provider interfaces** (`Embedder`, `ChatModel` Protocols) each have a `Fake*` implementation, so tests never call paid APIs.
- **The collection name includes the embedding model slug** (`ws_{id}__{model-slug}`, for example `ws_3__bge-small-en-v1-5`). Switching providers then can't mix vector dimensions, and a re-index endpoint rebuilds the collection.
- **Grounding:** retrieved chunks are numbered `[1]..[n]` in the prompt, and the model must cite with `[n]` or reply with a fixed "not found in the documents" answer. A similarity threshold skips the LLM entirely when nothing relevant comes back. Only sources the answer actually cites are returned as citations.
- **Follow-ups:** the last few turns are condensed into a standalone question for retrieval. The full answer is then generated with that history.
- **Streaming:** `POST /workspaces/{id}/conversations/{id}/messages` returns SSE events (`sources`, then `delta`s, then `done` with the cited sources and both message ids, or `error` with a safe message). The frontend reads it with `fetch` + `ReadableStream`, since EventSource can't POST.
- **Ingestion runs in a background task.** Each document's status moves pending → processing → ready/failed. SHA-256 dedup stops the same file being indexed twice in a workspace. Deleting a document also removes its vectors and its file.

## Working agreement
- **One step at a time.** After each step: run the tests, explain in plain English what was built and why, suggest a commit message (don't commit unless asked), and stop until the user says "continue".
- **Design choices:** pick the recommended option and mention it. Only ask the user about choices that are expensive or hard to undo.
- **Tick off each step** in this file when it's done.

## Steps

### Backend foundation
- [x] **1. Scaffold:** monorepo dirs, `.gitignore`, `.env.example`, uv project, ruff + pytest config, README skeleton, `master`→`main` rename, and `.claude/settings.json`. That file denies Read/Edit of `.env` and `.env.local` at any depth plus the obvious shell reads (this can't cover every possible command), and asks before package installs.
- [x] **2. Config + app:** `pydantic-settings` config, FastAPI app factory, CORS, `/health`, structured logging. Test: health returns OK.
- [x] **3. Database:** SQLAlchemy models (Workspace, Document, Conversation, Message, Citation JSON) on SQLite, and workspace CRUD routes. Tests: CRUD with a temporary DB.

### Ingestion pipeline
- [x] **4. Parsers:** PDF (PyMuPDF, per page), DOCX (python-docx, tracks headings and paragraphs), TXT (encoding detection, line numbers). Each one outputs `Segment(text, location)`. Tests: fixture files for each type, an empty/corrupt file, and an image-only PDF that should give a clear "no text found" error.
- [x] **5. Chunker:** token-aware, 350 tokens by default with 50 overlap (`CHUNK_SIZE_TOKENS`, `CHUNK_OVERLAP_TOKENS`). It takes an injected `count_tokens`; ingestion passes the embedder's own counter (the real bge tokenizer locally), because the cheap 4-characters estimate under-counts codes and digits (a real test hit 828 tokens against a 512 limit). A safety net splits any chunk the counter still rejects, so none is ever oversized. It keeps location metadata and joins page ranges when a chunk crosses a page. Tests: boundaries, overlap, metadata.
- [x] **6. Embedders:** `LocalEmbedder` (bge-small; adds the bge query prefix to queries only), `OpenAIEmbedder` and `FakeEmbedder`, behind a factory, with chunk size/overlap as settings. Tests: the factory, the fake, the local query prefix, the default chunk size fitting the local model's limit (OpenAI, sentence-transformers and the tokenizer are stubbed in the default suite; a `slow`-marked test checks the real bge model and tokenizer). Each embedder exposes `max_tokens` and `count_tokens()`.
- [x] **7. Vector store:** Chroma wrapper behind a `VectorStore` Protocol for add (replaces a document's old chunks), query (cosine similarity clamped to 0..1), delete-by-document and delete-workspace (every model's collection). Collections are `ws_{id}__{slug}`, with the slug hashed if the name would pass Chroma's 63-char limit. Telemetry is off. Tests use `FakeEmbedder` and a temp-dir Chroma client.
- [x] **8. Upload API:** (call `ensure_chunk_fits(embedder, settings.chunk_size_tokens)` at startup/ingestion, and chunk with `count_tokens=embedder.count_tokens`) `POST /workspaces/{id}/documents` (type and size validation), background ingestion, status listing, delete, `GET .../file` for preview, and re-index. Tests: upload → ready → query finds chunks; dedup; delete removes vectors.

### Answering
- [x] **9. LLM providers:** `OpenAIChat`, `AnthropicChat` and `FakeChat`, all with a streaming interface, and env-configurable models. Tests use mocked SDK streams. Closing a stream early closes the provider stream; per-call token usage goes to an `on_usage` callback (for step 18's spend cap); SDK errors map to our `LLM*Error` types; API keys are `SecretStr`.
- [x] **10. RAG service:** question condensing, retrieval + threshold, prompt build, `[n]` citation parsing and mapping. Tests: grounded answer with citations; off-topic question → refusal without an LLM call; citations that don't exist are dropped. Output is an event stream (sources → answer deltas → done with only the cited sources, `refused`, `uncited`). The whole answer call (system, history, sources, question, reserved output) fits `RAG_TOKEN_BUDGET`, trimming history before sources, so a follow-up stays under Groq's free 8K tokens/min. `[n]` markers are stripped from old answers in history, and document text is fenced as data against prompt injection.
- [x] **11. Chat API:** conversation CRUD, SSE `POST /workspaces/{id}/conversations/{id}/messages` (FastAPI's built-in SSE, with keep-alive pings), and saving the user and assistant messages with their citations and `refused`/`uncited`/`incomplete` flags. A client that leaves mid-answer (Stop) gets its partial answer saved as `incomplete`; errors become an `error` event and save nothing; one reply streams per conversation at a time (409, in-process guard: single worker). Token usage is logged per message. Tests: SSE event sequence, persisted history, errors, the 409 guard, and disconnects (service-level and a raw-ASGI hang-up).

### Frontend
- [ ] **12. Scaffold:** Vite + TS + Tailwind + shadcn/ui, routing, a typed API client, TanStack Query, and the app shell/layout.
- [ ] **13. Workspaces + documents UI:** workspace list/create, drag-and-drop upload with progress, status badges (with polling), delete with confirmation.
- [ ] **14. Chat UI:** conversation sidebar, streaming message rendering (markdown), citation chips `[1]` with a source list, stop/retry, and suggested starter questions.
- [ ] **★ Milestone: local demo you can screen-record.** One command (`scripts/dev` for backend + frontend) starts the app with a seeded demo workspace of sample business docs (pulled forward from step 17). You can then upload a file, watch it reach "ready", ask questions, get streamed answers with citations, open a past conversation, and see the "not in the documents" refusal. Includes a short demo script of questions to ask.
- [ ] **15. Citation preview panel:** a PDF opens at the cited page with `react-pdf` and the cited passage shown. DOCX and TXT show the passage with its heading or line context.
- [ ] **16. Polish:** empty, loading and error states, toasts, a responsive/mobile layout, keyboard and accessibility checks, light/dark theme, and favicon/branding.

### Ship
- [ ] **17. Docker Compose:** **bake both the bge tokenizer (`tokenizer.json`, used by the chunker through `tokenizers`) and the bge model files into the backend image** (for example `HF_HOME` set to a path inside the image, pre-filled at build time), so ingestion works offline and chunk counting never downloads at runtime. Backend (multi-stage, **CPU-only PyTorch** wheels from the PyTorch CPU index through a uv index config, embedding model baked into the image), Chroma, and the frontend built and served by nginx, with named volumes. Memory limits are sized for a **2GB VPS**. The README documents `EMBEDDING_PROVIDER=openai` as the low-memory option, which skips torch and the model entirely. A seed script creates the demo workspace with sample business docs (FAQ, pricing PDF, policies DOCX).
- [ ] **18. Demo hardening:** rate limiting (slowapi, per IP), upload caps (size, files per workspace, pages; the hard size cap lives in the proxy, see step 21), visitor-workspace TTL cleanup, a read-only demo workspace, `ADMIN_API_KEY`, and a daily LLM spend/request cap with a friendly message when it's reached.
- [ ] **19. Quality evidence:** an `eval/` script running about 20 golden Q&A pairs against the demo docs. It reports answer accuracy, citation accuracy and refusal accuracy, and the results go in the README.
- [ ] **20. CI + README:** GitHub Actions (ruff, pytest, frontend typecheck/build). The README gets an architecture diagram, screenshots/GIF, a quickstart, env var docs and design decisions.
- [ ] **21. Deploy:** a 2GB VPS (with swap enabled as a safety net) running docker compose behind Caddy (automatic HTTPS) with the live demo URL. **Caddy must cap request bodies** (`request_body { max_size … }`, set to `MAX_UPLOAD_MB` plus a small margin for multipart overhead): the app's 413 check only runs after the whole upload has been received. If nginx ever proxies the API, set `client_max_body_size` there too. Smoke test after the deploy.

## Verification
- `uv run pytest` passes at every backend step, using fake providers with no API keys.
- After step 11: run the full flow with curl (create workspace → upload → wait for ready → ask → SSE answer with citations).
- After step 16: manual browser check of upload → ask → click citation → correct page/passage, plus a question the docs can't answer gets the refusal.
- After step 17: `docker compose up --build` from a clean clone works with only `.env` filled in.
- After step 18: confirm the rate limit and caps return clean 429/413 errors that the UI shows.
- Run the step 19 eval with both `LLM_PROVIDER=openai` and `anthropic`.
