ARG app_env=prod

FROM python:3.13-slim-bookworm AS base

ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

# Install the project's dependencies using the lockfile and settings
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-project --no-dev

# Then, add the rest of the project source code and install it
# Installing separately from its dependencies allows optimal layer caching
ADD . /app

# Add binaries from the project's virtual environment to the PATH
ENV PATH="/app/.venv/bin:$PATH"

CMD ["/bin/sh", "./scripts/run.sh"]

FROM base AS dev
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen

FROM base AS prod
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev