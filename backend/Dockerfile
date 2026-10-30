# syntax=docker/dockerfile:1
# Backend image: FastAPI + embedded Chroma + the bge-small embedding model, CPU only.
# Build from the repo root with `docker compose build backend` (context: backend/).

ARG PYTHON_IMAGE=python:3.12.16-slim-trixie@sha256:8523d6abeb48ceae0b7240d30c5808fc26cb79c1a635bacdf19cf3baecfbec07

# --- builder: resolve the locked runtime dependencies into /app/.venv -------------------------
FROM ${PYTHON_IMAGE} AS builder
COPY --from=ghcr.io/astral-sh/uv:0.13.6@sha256:af22a52f5eafef3d78e551599d405c02df61919d18028f0cea8eda93bc9986d0 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0 \
    UV_PYTHON=/usr/local/bin/python
WORKDIR /app
COPY pyproject.toml uv.lock .python-version ./
# --frozen: exactly what uv.lock says. --no-dev: no reportlab, pytest, ruff or pyright.
# On Linux, [tool.uv.sources] in pyproject.toml takes torch from the PyTorch CPU index, so no
# nvidia-* CUDA packages are installed.
RUN uv sync --frozen --no-dev

# --- model: download the embedding model and tokenizer once, at build time -------------------
# Baked into the image rather than a volume: it is ~130 MB of disk (no RAM cost either way),
# startups never touch the network, and the model version ships with the code that expects it.
FROM builder AS model
ARG EMBEDDING_MODEL=BAAI/bge-small-en-v1.5
ENV HF_HOME=/opt/hf
# The same two loaders app/services/embeddings/local.py uses, so the runtime finds the cache
RUN /app/.venv/bin/python -c "import sys; from sentence_transformers import SentenceTransformer; from tokenizers import Tokenizer; SentenceTransformer(sys.argv[1]); Tokenizer.from_pretrained(sys.argv[1])" "${EMBEDDING_MODEL}"

# --- runtime ----------------------------------------------------------------------------------
FROM ${PYTHON_IMAGE} AS runtime
RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --home-dir /app --no-create-home app
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY --from=model /opt/hf /opt/hf
COPY app ./app
COPY scripts ./scripts
COPY demo_data ./demo_data
# The named volume mounted here starts with this ownership, so the app user can write to it
RUN mkdir -p /app/data && chown app:app /app/data

ENV PATH=/app/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HF_HOME=/opt/hf \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    DATA_DIR=/app/data \
    FORWARDED_ALLOW_IPS=127.0.0.1

USER app
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)"]

# Exactly ONE worker: SQLite writes, the embedded Chroma store, the embedder's model-load lock
# and the per-conversation reply guard (the 409 "reply already in progress") all live in this
# one process. A second worker would get its own copies of them and they would stop working.
# Forwarded client IPs are only trusted from FORWARDED_ALLOW_IPS (compose sets its network's
# subnet, where only the web proxy talks to us); never "*", or any client could pick its IP.
CMD ["sh", "-c", "exec uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8000 --workers 1 --proxy-headers --forwarded-allow-ips=\"$FORWARDED_ALLOW_IPS\""]
