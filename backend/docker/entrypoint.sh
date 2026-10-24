#!/bin/sh
# One image, several roles. The first argument chooses what runs:
#
#   api      (default) run database migrations, then serve the FastAPI app
#   worker   [args]    run the training worker (python -m worker.main)
#   migrate            run database migrations and exit
#   cli      [args]    operator commands (python -m app.cli ...), e.g. create-user
#   <other>            run that command as given, e.g. "uvicorn app.main:app --reload"
#
# Migrations run only when ENVIRONMENT is not "local" (local development builds its tables
# directly) and can be switched off with RUN_MIGRATIONS=false.
set -eu

role="${1:-api}"

case "$role" in
  api)
    if [ "${ENVIRONMENT:-local}" != "local" ] && [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
      python -m app.migrate
    fi
    # PORT is 8000 unless the platform says otherwise. No --reload and no proxy-header trust here:
    # the client address behind a proxy is handled by TRUSTED_PROXY_HOPS inside the app.
    exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --no-server-header
    ;;
  worker)
    shift
    exec python -m worker.main "$@"
    ;;
  migrate)
    exec python -m app.migrate
    ;;
  cli)
    shift
    exec python -m app.cli "$@"
    ;;
  *)
    exec "$@"
    ;;
esac
