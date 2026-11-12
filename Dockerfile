FROM python:3.12-slim-bookworm@sha256:935c3c5b12357a7e10caa9c1e6ca5692344d97cf229832ef584be2cec9fc03df AS build
WORKDIR /opt/memory
RUN pip install --no-cache-dir uv==0.12.5
ENV UV_HTTP_TIMEOUT=300
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
COPY third_party ./third_party
ARG INSTALL_MODELS=false
RUN if [ "$INSTALL_MODELS" = "true" ]; then \
      uv sync --frozen --no-dev --no-editable --extra models; \
    else \
      uv sync --frozen --no-dev --no-editable; \
    fi

FROM python:3.12-slim-bookworm@sha256:935c3c5b12357a7e10caa9c1e6ca5692344d97cf229832ef584be2cec9fc03df
ENV PATH="/opt/memory/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    GRAPHITI_TELEMETRY_ENABLED=false \
    MEMORY_DATABASE_URL=sqlite:////state/memory.db
WORKDIR /opt/memory
COPY --from=build /opt/memory/.venv ./.venv
COPY examples ./examples
RUN groupadd --gid 10001 memory \
    && useradd --uid 10001 --gid memory --create-home memory \
    && mkdir /state /models \
    && chown memory:memory /state /models
USER 10001:10001
ENTRYPOINT ["governed-memory"]
CMD ["serve"]
