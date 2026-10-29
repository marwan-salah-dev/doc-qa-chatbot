# DocQA Support Agent

An AI support agent that answers customer questions **only from a business's own documents**, with citations to the exact source file and page.

> Status: Stage 1 in progress. Live demo, screenshots and evaluation results are coming soon.

## Features (Stage 1)

- Upload PDF, DOCX and TXT files into separate workspaces (one per business)
- Ask questions in a chat and get streamed answers grounded in those documents
- Citations show the source file and page (PDF), section (DOCX) or lines (TXT); click one to preview the passage
- Says "I couldn't find that in the documents" instead of guessing
- Switch between Anthropic and OpenAI models with one environment variable

**Planned for Stage 2:** tool calling (book appointments, create support tickets) and an embeddable chat widget for any website.

## Tech stack

| Layer | Choice |
| --- | --- |
| API | Python 3.12, FastAPI |
| Retrieval | ChromaDB, sentence-transformers or OpenAI embeddings |
| LLM | Anthropic or OpenAI (`LLM_PROVIDER`) |
| Frontend | React, TypeScript, Vite, Tailwind CSS, shadcn/ui, TanStack Query |
| Tests | pytest, Vitest |
| Deploy | Docker Compose |

## Project layout

```
backend/    FastAPI app and tests
frontend/   React app
```

## Development

Requirements: Python 3.12, [uv](https://docs.astral.sh/uv/), Node 20.19+ or 22.12+ (required by Vite 8).

Backend (first terminal):

```bash
cd backend
cp .env.example .env   # then fill in your API key
uv sync
uv run pytest
uv run uvicorn app.main:create_app --factory --port 8000 --reload   # --reload restarts on code changes (development only)
```

Frontend (second terminal):

```bash
cd frontend
npm install
npm run test
npm run dev            # http://localhost:5173, proxies /api to the backend on :8000
```
