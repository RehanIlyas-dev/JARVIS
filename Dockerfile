FROM python:3.11-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    portaudio19-dev \
    libespeak-ng-dev \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN pip install --no-cache-dir -e "."

FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    portaudio19-dev \
    libespeak-ng-dev \
    libsndfile1 \
    espeak-ng \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY --from=builder /app /app

RUN addgroup --system --gid 1001 jarvis && \
    adduser --system --uid 1001 jarvis --ingroup jarvis && \
    chown -R jarvis:jarvis /app
USER jarvis

WORKDIR /app
ENV FLASK_HOST=0.0.0.0
EXPOSE 5000
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/api/status')" || exit 1

ENTRYPOINT ["jarvis-web"]
