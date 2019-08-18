FROM debian:9.8 as builder
ENV NODE_ENV production
RUN apt-get update \
  && apt-get install -y curl \
  && curl -sL https://deb.nodesource.com/setup_10.x | bash - \
  && apt-get update \
  && apt-get install -y nodejs \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/*
COPY package.json package-lock.json webpack.config.js /
COPY src /src
COPY static /static
RUN npm install \
  && npm install --only=dev \
  && npm run build

FROM python:3.7-slim
ENV PYTHONUNBUFFERED 1
RUN mkdir /pyobs-archive
WORKDIR /pyobs-archive
COPY requirements.txt /pyobs-archive/
RUN pip install -r requirements.txt
COPY . /pyobs-archive/
COPY --from=builder /static static
CMD gunicorn pyobs_archive.wsgi
