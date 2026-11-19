FROM docker.io/library/python:3.12-slim-bookworm
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY requirements.txt .
RUN --mount=type=secret,id=build_ca \
    if [ -f /run/secrets/build_ca ]; then export PIP_CERT=/run/secrets/build_ca; fi && \
    pip install --no-cache-dir -r requirements.txt && useradd --uid 10001 --create-home tracker
COPY --chown=tracker:tracker tracker tracker
COPY --chown=tracker:tracker alembic.ini .
COPY --chown=tracker:tracker alembic alembic
USER tracker
CMD ["uvicorn", "tracker.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
