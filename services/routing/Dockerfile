FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

WORKDIR /app

# a fixed non-root user, created before anything is copied in
RUN useradd --create-home --uid 10001 app

# dependencies first, so editing code does not reinstall them (layer cache)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# only the files the service needs: no tests, no .env, no secrets
COPY app.py db.py migrate.py seed.py service.py web.py kpi_client.py ./
COPY migrations/ migrations/

USER app
EXPOSE 8000

# --preload runs create_app() once in the master before forking the workers,
# so migrations run once per container, not once per worker.
# --threads: a request waiting up to ~60s for a paused Azure SQL database to resume holds a
# thread, not a whole worker, so /health (the pipeline's health check) still answers meanwhile.
CMD ["sh", "-c", "exec gunicorn --preload --workers 2 --threads 4 --timeout 120 --bind 0.0.0.0:${PORT} 'app:create_app()'"]
