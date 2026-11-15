# BoardProof — Cloud Run / any container host.
# The image is self-contained: it builds a full demo dashboard at build time, then
# serves it with the stdlib HTTP server (no framework, no runtime dependencies).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    BOARDPROOF_MODEL=gemini-2.5-flash

WORKDIR /app
COPY pyproject.toml README.md ./
COPY boardproof ./boardproof
RUN python -m pip install --quiet --upgrade pip && python -m pip install --quiet .

COPY examples ./examples
COPY tests ./tests

# Build the artifacts a reviewer or a judge would look at, offline (no key needed).
RUN set -e; \
    mkdir -p artifacts; \
    boardproof check --config examples/demo/boardproof.pack.json \
        --explain --engine offline \
        --html artifacts/broken.html --json artifacts/broken.json || true; \
    boardproof check --config examples/demo/boardproof.pack.clean.json \
        --explain --engine offline \
        --html artifacts/clean.html --json artifacts/clean.json; \
    boardproof redteam --config examples/demo/boardproof.pack.clean.json \
        --json artifacts/redteam.json; \
    boardproof diff --base artifacts/clean.json --head artifacts/broken.json \
        --no-fail --json artifacts/diff.json > /dev/null; \
    boardproof passport --config examples/demo/boardproof.pack.json \
        --revision "Demo board · Revision B" --redteam artifacts/redteam.json \
        --base artifacts/clean.json --engine offline \
        --out artifacts/passport.html --json artifacts/passport.json || true; \
    boardproof dashboard --dir artifacts

# Cloud Run injects PORT; serve.py falls back to 8080.
ENV PORT=8080
EXPOSE 8080
CMD ["boardproof", "serve", "--dir", "artifacts"]
