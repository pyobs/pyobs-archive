FROM python:3.11-slim
ENV PYTHONUNBUFFERED 1
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/
RUN apt-get update \
  && apt-get install -y libcfitsio-bin \
  && rm -rf /var/lib/apt/lists/*
RUN mkdir /archive
WORKDIR /archive
COPY pyproject.toml uv.lock /archive/
RUN uv sync --locked --no-install-project
COPY . /archive/
RUN uv run python manage.py collectstatic --no-input
CMD bash -c "uv run python manage.py migrate && uv run gunicorn --bind 0.0.0.0:8000 --worker-tmp-dir /dev/shm --workers=5 --threads=4 --worker-class=gthread pyobs_archive.wsgi"
