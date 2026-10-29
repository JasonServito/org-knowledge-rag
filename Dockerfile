# check=skip=CopyIgnoredFile
# (Line 1: BuildKit's copy check misreads the allowlist .dockerignore, which starts with `*`, as
# excluding `COPY . .`; the build sends only the allowed files either way.)
# The one image (S15-T3, ADR-014 D4): the API by default, the worker with
# `python -m orgknow.ingestion.worker`. Build it with `make image`, check it with `make image-check`.
# Base images are pinned by digest (the multi-arch index), so a rebuild gets the same bytes.
FROM python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1

# git: ingestion reads the corpus cache's clones with it (ingestion/git_reader.py).
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

# uv installs the locked dependencies; the same version as on the laptop.
COPY --from=ghcr.io/astral-sh/uv:0.12.19@sha256:04d046b13e60d6bcec73cbc5e1cad25d680dea90c8573340950a0ac2d1aef424 /uv /usr/local/bin/uv
# No uv cache left in the image; .pyc files written now (the runtime user can't write them); the
# base image's Python, never a downloaded one.
ENV UV_NO_CACHE=1 UV_COMPILE_BYTECODE=1 UV_PYTHON_DOWNLOADS=never

WORKDIR /app
# The dependencies first, in their own layer: a code change doesn't download them again.
# --frozen: exactly uv.lock (torch from the CPU index, as pyproject.toml says); --no-dev: no tools.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
ENV PATH=/app/.venv/bin:$PATH

# The reranker's weights (ADR-008), downloaded once here, at the pinned revision, the way
# retrieval/cross_encoder.py loads them; the app reads them offline. These must equal
# settings.py's RERANK_MODEL and RERANK_REVISION: otherwise the reranker fails to load at startup.
ARG RERANK_MODEL=BAAI/bge-reranker-base
ARG RERANK_REVISION=2cfc18c9415c912f9d8155881c133215df768a70
ENV HF_HOME=/opt/hf
RUN python -c "import os; \
from transformers import AutoModelForSequenceClassification, AutoTokenizer; \
name, revision = os.environ['RERANK_MODEL'], os.environ['RERANK_REVISION']; \
AutoTokenizer.from_pretrained(name, revision=revision); \
AutoModelForSequenceClassification.from_pretrained(name, revision=revision, use_safetensors=True)"
ENV HF_HUB_OFFLINE=1

# The code and the files it reads relative to /app (config/, the eval files): exactly what
# .dockerignore allows, so that list alone decides what is in the image. Then the project itself.
COPY . .
RUN uv sync --frozen --no-dev

# The runtime user: not root.
RUN useradd --uid 10001 --create-home orgknow
# Git trusts every directory: the mounted corpus cache belongs to another user (ADR-014 D4).
RUN git config --system --add safe.directory '*'
USER orgknow
# Git may use only local transports: a file missing from the cache fails the ingest instead of
# being fetched from GitHub (ADR-014 D4). The cache is mounted here, read-only, into the worker.
ENV GIT_ALLOW_PROTOCOL=file CORPUS_CACHE_DIR=/corpus_cache

EXPOSE 8000
CMD ["uvicorn", "--factory", "orgknow.api.app:create_app", "--host", "0.0.0.0", "--port", "8000", \
     "--log-config", "config/logging.json", "--no-access-log"]
