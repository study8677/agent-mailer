FROM python:3.11-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY src/ src/
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

EXPOSE 9800

ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["uv", "run", "uvicorn", "agent_mailer.main:app", "--host", "0.0.0.0", "--port", "9800"]
