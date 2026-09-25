FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN useradd --create-home --uid 1000 brooks \
    && mkdir -p /app/data

COPY pyproject.toml README.md ./
COPY bot ./bot

RUN pip install --no-cache-dir . \
    && chown -R brooks:brooks /app

USER brooks

VOLUME ["/app/data"]

CMD ["python", "-m", "bot"]
