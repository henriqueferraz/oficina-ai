FROM python:3.13-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY . .

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

CMD sh -c "python manage.py migrate --noinput && \
    python manage.py collectstatic --noinput && \
    gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 2"
