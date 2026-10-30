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
backend/    FastAPI app, tests, demo documents (demo_data/) and their scripts (scripts/)
frontend/   React app
scripts/    dev.ps1: start everything locally and seed the demo
docs/       plan and demo script
```

## Development

Requirements: Python 3.12, [uv](https://docs.astral.sh/uv/), Node 20.19+ or 22.12+ (required by Vite 8).

### One command (Windows PowerShell)

After the one-time setup below (`.env`, `uv sync`, `npm install`), run this from the repo root:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\dev.ps1
```

It starts the backend and the frontend in their own windows, waits until the API is up, and seeds the **Demo: BrightSmile Dental** workspace with sample documents (it is safe to run again: nothing is duplicated). Then open http://localhost:5173. Press Ctrl+C in the script's window to stop both servers, or close a server's window to stop that server. [docs/DEMO.md](docs/DEMO.md) has a short demo recording script.

### Step by step

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

Demo workspace (with the backend running):

```bash
cd backend
uv run python -m scripts.seed_demo
```

## Run with Docker

Production-style: two containers sized for a 2 GB server. `backend` runs FastAPI with embedded Chroma and the bge-small model baked into the image, and `web` runs nginx, which serves the built React app and proxies `/api` with streaming unbuffered. Requirements: Docker with Compose v2.

```bash
cp backend/.env.example backend/.env    # then fill in your API key (the only file you need to edit)
docker compose up -d --build            # first build downloads CPU-only PyTorch and the model: several minutes
docker compose exec backend python -m scripts.seed_demo --api-url http://127.0.0.1:8000 --ui-url http://127.0.0.1:8080
```

Open http://127.0.0.1:8080.

- **Data** (SQLite, the Chroma index and uploaded files) lives in the named volume `docqa_backend-data`. `docker compose down` followed by `docker compose up -d` keeps it, and `docker compose down -v` deletes it.
- **Secrets** come only from `backend/.env` at runtime (`env_file`). `.dockerignore` keeps `.env` out of both images.
- **Memory:** the limits are 1200 MB for the backend and 64 MB for web. Measured: the backend uses about 230 MB idle, 600-780 MB once the embedding model is loaded and indexing, and web about 15 MB.
- **Low-memory option:** set `EMBEDDING_PROVIDER=openai` in `backend/.env` (needs `OPENAI_API_KEY`). The local model and PyTorch are then never loaded, so the backend stays at a few hundred MB. Existing documents need a re-index after switching.
- **One worker on purpose:** SQLite, embedded Chroma, the model lock and the one-reply-per-conversation guard all live in a single process, so don't scale the backend to more than one worker or replica.
- Logs: `docker compose logs -f backend`. Stop: `docker compose down`.
