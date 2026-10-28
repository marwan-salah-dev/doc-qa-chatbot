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
backend/    FastAPI app (app/) and tests (tests/), managed with uv
frontend/   React app (added in step 12)
docs/       PLAN.md and other project docs
```

## Key commands

Run these from `backend/`:

```bash
uv sync                   # install/update dependencies into backend/.venv
uv run pytest             # run the test suite
uv run ruff check .       # lint
uv run ruff format .      # format (use --check to verify only)
uv run pyright            # type check (basic mode, configured in pyproject.toml)
```

On this Windows machine uv was installed through winget. A shell opened before that install may not have `uv` on PATH yet.

## Working agreement

- **One step at a time.** After each step: run the tests, ruff and pyright, explain in plain English what was built and why, suggest a commit message, and stop until the user says "continue".
- **Don't commit** unless the user asks.
- **Design choices:** pick the recommended option and mention it. Only ask the user about choices that are expensive or hard to undo.
- **Package installs need approval.** `.claude/settings.json` asks before installs. Never try to get around that.
- **Never read or print `.env` files.** Use `backend/.env.example` to learn the configuration.

## Conventions

- **Tests:** they never call paid APIs. Use the `Fake*` providers (fake embedder and fake chat model) and mocked SDKs.
- **Configuration:** comes from environment variables through `pydantic-settings`. Every new setting must also be added to `backend/.env.example` with a comment (a test checks this). The app loads `backend/.env` wherever commands are run from.
- **Ruff rules:** E, W, F, I, B, UP, SIM, RUF, with line length 100. Keep `ruff check` and `ruff format --check` clean.
- **Type checking:** pyright in basic mode must report 0 errors.
- **Licenses:** avoid GPL/AGPL dependencies, since clients may reuse this code (PDF parsing uses pypdf, BSD, not PyMuPDF).
