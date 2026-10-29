# WebPuente backend image.  NOTE: written carefully but not run by the author (no Docker in the build sandbox). Test it locally first.
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Static files for the admin site. A throw-away key is used only for this build step.
RUN DJANGO_SECRET_KEY=build-only DJANGO_SETTINGS_MODULE=core.settings.development python manage.py collectstatic --noinput

RUN useradd --create-home appuser && chown -R appuser /app
USER appuser

EXPOSE 8000
# The web service. For a separate worker run:  python manage.py run_worker
CMD ["sh", "-c", "python manage.py migrate --noinput && gunicorn core.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers ${WEB_CONCURRENCY:-2} --threads 4 --timeout 120 --access-logfile -"]
