# Production image for the API and the training worker (one image, chosen at run time).
#
#   docker build -t automl-backend backend/
#   docker run --rm -p 8000:8000 --env-file backend/.env automl-backend          # the API
#   docker run --rm --env-file backend/.env automl-backend worker                # the worker
#   docker run --rm --env-file backend/.env automl-backend cli create-user alice
#
# See docker/entrypoint.sh for the roles. Configuration is environment variables only; no
# secret is baked into the image.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app

WORKDIR /app

# Dependencies first: this layer is rebuilt only when pyproject.toml changes. The project's own
# code is run from /app (not installed), so the dev tools in the "dev" extra are never included.
COPY pyproject.toml ./
RUN python -c "import tomllib; print(chr(10).join(tomllib.load(open('pyproject.toml', 'rb'))['project']['dependencies']))" > /tmp/requirements.txt \
    && pip install -r /tmp/requirements.txt \
    && rm /tmp/requirements.txt

COPY app ./app
COPY automl ./automl
COPY worker ./worker
COPY migrations ./migrations
COPY alembic.ini ./
COPY --chmod=0755 docker/entrypoint.sh /usr/local/bin/entrypoint.sh

# Run as an unprivileged user. Local-mode data (SQLite, artifacts) goes to /data when used.
RUN adduser --system --uid 10001 --no-create-home --group app \
    && mkdir -p /data \
    && chown -R app:app /app /data
USER 10001

EXPOSE 8000
ENTRYPOINT ["entrypoint.sh"]
CMD ["api"]
