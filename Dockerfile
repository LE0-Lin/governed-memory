FROM rust:1.90.0-slim-bookworm@sha256:64232e656c058f4468e8d024e990acff04f0fd5a5c0a88a574dc37773d7325c9 AS native
WORKDIR /native
COPY native/Cargo.toml native/Cargo.lock ./
COPY native/src ./src
# abi3-py312 permits a native extension build without a host Python interpreter.
ENV PYO3_NO_PYTHON=1
RUN cargo build --release --locked --features extension-module

FROM python:3.12-slim-bookworm@sha256:935c3c5b12357a7e10caa9c1e6ca5692344d97cf229832ef584be2cec9fc03df AS build
WORKDIR /opt/memory
RUN pip install --no-cache-dir uv==0.12.5
ENV UV_HTTP_TIMEOUT=300
COPY pyproject.toml uv.lock README.md ./
COPY native ./native
ARG INSTALL_MODELS=false
RUN if [ "$INSTALL_MODELS" = "true" ]; then \
      uv sync --frozen --no-dev --no-install-project --extra models; \
    else \
      uv sync --frozen --no-dev --no-install-project; \
    fi
COPY src ./src
COPY third_party ./third_party
RUN if [ "$INSTALL_MODELS" = "true" ]; then \
      uv sync --frozen --no-dev --no-editable --extra models; \
    else \
      uv sync --frozen --no-dev --no-editable; \
    fi
COPY --from=native /native/target/release/libgoverned_memory_native.so /opt/memory/.venv/lib/python3.12/site-packages/governed_memory_native.abi3.so

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
