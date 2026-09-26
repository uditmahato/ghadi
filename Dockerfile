# GHADI shadow service. One process, one station, decisions recorded, nothing sent.
#
#   docker build -t ghadi:latest .
#   docker run --rm -v ghadi-state:/var/lib/ghadi ghadi:latest live --hours 1
#
# The image holds the library, the scripts, and the catalogue. It does not hold the
# waveform cache, the audit log, or any credential. State lives in the mounted volume.

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /opt/ghadi

# Build dependencies for obspy's compiled parts, removed after the install.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md LICENSE ./
COPY src ./src
COPY scripts ./scripts
COPY data/catalog ./data/catalog
COPY deploy/ghadi.toml /etc/ghadi/ghadi.toml

RUN pip install --no-cache-dir . \
    && apt-get purge -y build-essential \
    && apt-get autoremove -y

# The service runs as an unprivileged user and owns only its state directory.
RUN useradd --system --create-home --home-dir /var/lib/ghadi ghadi \
    && chown -R ghadi:ghadi /var/lib/ghadi
USER ghadi
VOLUME ["/var/lib/ghadi"]
EXPOSE 8771

HEALTHCHECK --interval=60s --timeout=5s --start-period=120s --retries=3 \
    CMD python -c "import json,sys,urllib.request; d=json.load(urllib.request.urlopen('http://127.0.0.1:8771/health', timeout=4)); sys.exit(0 if d.get('ok') else 1)"

ENTRYPOINT ["python", "scripts/run_shadow.py"]
CMD ["live", "--settings", "/etc/ghadi/ghadi.toml", "--hours", "0"]
