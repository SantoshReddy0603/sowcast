FROM python:3.12-slim-bookworm@sha256:e697c81897302a4c4333bade000d98038fbb21eb064f8ee1fd42d02ebcd9d337
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY apps/api/requirements.lock /app/requirements.lock
RUN python -m pip install --no-cache-dir -r requirements.lock
COPY apps/api/pyproject.toml /app/apps/api/pyproject.toml
COPY apps/api/src /app/apps/api/src
RUN python -m pip install --no-cache-dir --no-deps /app/apps/api && useradd --uid 10001 --create-home sowcast && mkdir /app/.sowcast && chown 10001:10001 /app/.sowcast
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','8000')+'/health', timeout=8)"
CMD ["python", "-m", "sowcast", "serve"]
