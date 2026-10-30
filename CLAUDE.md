# CLAUDE.md

This file guides Claude Code when working in this repository.

## Start of every session

1. Read [docs/PLAN.md](docs/PLAN.md). It holds the Stage 1 plan, decisions and step checklist.
2. Find the first unticked step. That is the next step to work on, unless the user says otherwise.
3. When a step is done, tick it (`- [x]`) in docs/PLAN.md as part of that step's work.

## Project overview

DocQA Support Agent is a portfolio project: an AI support agent for a business.

- **Stage 1 (current):** users upload PDF, TXT or DOCX files into a workspace and ask questions. Answers are streamed and grounded only in those documents, with citations to the source file and page (PDF), heading and paragraphs (DOCX) or lines (TXT).
- **Stage 2 (later):** tool calling (book appointments, create tickets) and an embeddable website chat widget.

It must look and work like something a paying client would accept.

Stack: Python 3.12 + FastAPI, ChromaDB, OpenAI or Anthropic (`LLM_PROVIDER`), local or OpenAI embeddings (`EMBEDDING_PROVIDER`), React + TypeScript (Vite), pytest, Docker Compose.

## Layout

```
backend/    FastAPI app (app/), tests (tests/), demo docs (demo_data/) and their scripts (scripts/), managed with uv
frontend/   React app (src/), Vite + TypeScript, managed with npm
scripts/    dev.ps1: start backend + frontend and seed the demo
docker-compose.yml, backend/Dockerfile, frontend/Dockerfile + nginx.conf: the production-style stack
docs/       PLAN.md, DEMO.md (recording script) and other project docs
```

## Key commands

Run these from `backend/`:

```bash
uv sync                   # install/update dependencies into backend/.venv
uv run pytest             # run the test suite
uv run ruff check .       # lint
uv run ruff format .      # format (use --check to verify only)
uv run pyright            # type check (basic mode, configured in pyproject.toml)
uv run uvicorn app.main:create_app --factory --port 8000 --reload   # start the API in development; --reload picks up backend changes (there is no app.main:app)
uv run python -m scripts.seed_demo        # seed "Demo: BrightSmile Dental" through the running API (idempotent)
uv run python -m scripts.build_demo_docs  # rebuild demo_data/ after editing scripts/demo_content.py (reportlab, dev-only)
```

Run these from `frontend/`:

```bash
npm install               # install dependencies
npm run dev               # start the dev server on http://localhost:5173 (proxies /api to :8000)
npm run test              # Vitest, single run with a 10 s test timeout (add a file path to run one file; use this, not npx vitest)
npm run lint              # ESLint (typescript-eslint strict, type-aware)
npm run typecheck         # tsc -b (strict)
npm run format            # Prettier (format:check to verify only)
npm run build             # production build into frontend/dist
```

Run these from the repo root (Docker, production-style, app on http://127.0.0.1:8080):

```bash
docker compose up -d --build      # build and start backend + web (needs backend/.env)
docker compose exec backend python -m scripts.seed_demo --api-url http://127.0.0.1:8000 --ui-url http://127.0.0.1:8080
docker compose logs -f backend    # follow the API's logs
docker compose down               # stop; data stays in the docqa_backend-data volume (down -v wipes it)
```

The backend runs exactly one uvicorn worker (SQLite, embedded Chroma, the model lock and the reply guard are in-process), has no host port (only `web` reaches it) and trusts `X-Forwarded-For` only from the pinned compose subnet. nginx overwrites that header. `backend/tests/test_docker_config.py` guards these.

From the repo root, `powershell -ExecutionPolicy Bypass -File scripts\dev.ps1` starts both servers in their own windows, waits for `/health`, then seeds the demo (Ctrl+C stops both; servers already running are reused). Otherwise start the backend first, then the frontend, each in its own terminal. Long-running servers (uvicorn, `npm run dev`) should be started in the background, never in the foreground.

On this Windows machine uv was installed through winget. A shell opened before that install may not have `uv` on PATH yet.

## Working agreement

- **One step at a time.** After each step: run the tests, ruff and pyright, explain in plain English what was built and why, suggest a commit message, and stop until the user says "continue".
- **Don't commit** unless the user asks.
- **Design choices:** pick the recommended option and mention it. Only ask the user about choices that are expensive or hard to undo.
- **Package installs need approval.** `.claude/settings.json` asks before installs. Never try to get around that.
- **Never read or print `.env` files.** Use `backend/.env.example` to learn the configuration.

## Plan self-review

Before presenting any plan, check it against this list. Under the plan, add a short "Self-review" list of each concern found and the fix already applied to the plan (or "No concerns" for a section that has none).

- **New dependencies:** licence (no GPL/AGPL), install and bundle size, dev or runtime dependency, and whether it ships in the production Docker image. Prefer the standard library or an existing dependency.
- **Groq free tier:** about 8K tokens per minute. Keep prompts and retrieved context small, and wait about 60 s between live questions when testing against the real API.
- **Windows / PowerShell:** use `curl.exe` (plain `curl` is an alias for `Invoke-WebRequest`), `127.0.0.1` instead of `localhost` (avoids IPv6 resolution delays and misses), PowerShell syntax (no `&&` in 5.1), and backslash paths in scripts.
- **Security:** every query, upload and delete is scoped to its workspace; no secrets, keys or customer data in code, logs or commits; `.env` is never read.
- **Frontend bundle size:** lazy-load heavy libraries (`React.lazy` / dynamic `import()`) and check the `npm run build` output for size changes.
- **Live verification:** say how the change will be checked in the browser against the running app, not only by tests.

## Conventions

- **Frontend:** the browser calls `/api/...`; Vite (dev) strips the prefix and proxies to the backend, so there is no CORS in development. Hand-written API types in `frontend/src/api/types.ts` mirror `backend/app/api/schemas.py`; update both together. Server settings the UI must match (today `max_upload_mb`) come from `GET /config` (`useConfig`), never a copied constant. Component tests use jsdom + Testing Library: put `// @vitest-environment jsdom` at the top of the file and mock `api` from `@/api/client`. TypeScript is pinned to 6.0 until typescript-eslint supports 7. Colours come from the tokens in `index.css` (`primary`, `primary-soft`, `surface`, `highlight`, `success`, `warning`); don't hard-code Tailwind palette colours. Below `lg` (`useMediaQuery(WIDE_LAYOUT)`) side lists render in a `Sheet` instead of beside the chat; component tests get the desktop layout unless they call `setMatchMedia(false)`. Confirm user actions with `toast` from `sonner`, alongside any inline error.
- **Tests:** they never call paid APIs. Use the `Fake*` providers (fake embedder and fake chat model) and mocked SDKs.
- **Public demo:** `PUBLIC_DEMO=true` (docker-compose's default) turns on visitor ownership (`X-Visitor-Id`, `app/api/access.py`), the read-only demo workspace, expiry, per-IP rate limits and the daily token cap. With it off, behaviour must stay exactly as before. A new route that touches a workspace's data goes through `get_workspace_or_404(..., access, write=...)`. A browser fetch to the API sends `apiHeaders()` (`src/lib/visitor.ts`), so never link to an API URL directly.
- **Configuration:** comes from environment variables through `pydantic-settings`. Every new setting must also be added to `backend/.env.example` with a comment (`test_config.py` checks this). The app loads `backend/.env` wherever commands are run from.
- **Ruff rules:** E, W, F, I, B, UP, SIM, RUF, with line length 100. Keep `ruff check` and `ruff format --check` clean.
- **Type checking:** pyright in basic mode must report 0 errors.
- **Licenses:** avoid GPL/AGPL dependencies, since clients may reuse this code (PDF parsing uses pypdf, BSD, not PyMuPDF).
