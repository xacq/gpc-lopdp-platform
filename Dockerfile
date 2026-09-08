FROM python:3.13-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install --no-install-recommends -y clamav clamav-freshclam \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements/base.txt /tmp/requirements.txt
RUN python -m pip install --upgrade pip \
    && python -m pip install -r /tmp/requirements.txt

RUN addgroup --system django \
    && adduser --system --ingroup django --home /app django \
    && mkdir -p /app/staticfiles /app/media /app/private_storage \
    && chown -R django:django /app

COPY --chown=django:django . /app
RUN chmod +x /app/deploy/entrypoint.sh

USER django

EXPOSE 8000

ENTRYPOINT ["/app/deploy/entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--timeout", "60", "--access-logfile", "-", "--error-logfile", "-"]
