FROM python:3.7-slim
ENV PYTHONUNBUFFERED 1
RUN apt-get update \
  && apt-get install -y libcfitsio-bin \
  && rm -rf /var/lib/apt/lists/*
RUN mkdir /pyobs-archive
WORKDIR /pyobs-archive
COPY requirements.txt /pyobs-archive/
RUN pip install -r requirements.txt
COPY . /pyobs-archive/
CMD gunicorn pyobs_archive.wsgi
