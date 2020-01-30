FROM python:3.7-slim
ENV PYTHONUNBUFFERED 1
RUN apt-get update \
  && apt-get install -y libcfitsio-bin \
  && rm -rf /var/lib/apt/lists/*
RUN mkdir /archive
WORKDIR /archive
COPY requirements.txt /archive/
RUN pip install -r requirements.txt
COPY . /archive/
CMD gunicorn --bind 0.0.0.0:8000 --worker-tmp-dir /dev/shm --workers=2 --threads=4 --worker-class=gthread pyobs_archive.wsgi
