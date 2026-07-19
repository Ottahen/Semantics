# Semantics (ctf) — container image.
# Build:  docker build -t semantics .
# Run:    docker run -it --rm -v "$PWD":/workspace -e SEMANTICS_API_KEY semantics "add tests for utils.py"

FROM python:3.12-slim AS base

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    ripgrep \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml requirements.txt requirements.pro.txt ./
COPY src/ ./src/

# Core install by default; pass --build-arg INSTALL_PRO=1 for the TUI/browser/MCP extras.
ARG INSTALL_PRO=0
RUN pip install --no-cache-dir -e . \
    && if [ "$INSTALL_PRO" = "1" ]; then \
         pip install --no-cache-dir -e ".[pro]" && playwright install --with-deps chromium; \
       fi

WORKDIR /workspace
ENTRYPOINT ["ctf"]
CMD ["--help"]
