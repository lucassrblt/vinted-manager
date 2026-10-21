#!/bin/sh
set -e
alembic upgrade head
# Un seul worker : APScheduler tourne dans ce process (une seule instance).
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --workers 1 --proxy-headers --forwarded-allow-ips='*'
