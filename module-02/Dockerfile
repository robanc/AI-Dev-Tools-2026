FROM node:22-bookworm-slim AS frontend-build
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
ENV VITE_INTERVIEW_SERVICE=real VITE_API_BASE_URL=same-origin
RUN npm run build

FROM python:3.12-slim-bookworm AS backend-build
COPY --from=ghcr.io/astral-sh/uv:0.12.10 /uv /usr/local/bin/uv
WORKDIR /build/backend
ENV UV_PROJECT_ENVIRONMENT=/opt/venv UV_PYTHON_DOWNLOADS=never
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --locked --no-dev --no-install-project --no-cache

# Homework Question 6: the final runtime base image.
FROM python:3.12-slim-bookworm AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    DATABASE_URL=sqlite:////data/pairroom.db \
    FRONTEND_DIST=/app/frontend \
    FRONTEND_ORIGINS=http://localhost:8000,http://127.0.0.1:8000
WORKDIR /app/backend
RUN groupadd --gid 10001 pairroom && useradd --uid 10001 --gid pairroom --no-create-home pairroom \
    && mkdir /data && chown pairroom:pairroom /data
COPY --from=backend-build /opt/venv /opt/venv
COPY backend/app/ ./app/
COPY --from=frontend-build /build/frontend/dist/ /app/frontend/
USER pairroom
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
