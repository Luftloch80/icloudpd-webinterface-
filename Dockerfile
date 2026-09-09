# Builds on all common Raspberry Pi targets (linux/arm64, linux/arm/v7) as
# well as linux/amd64, since the official python:slim images are multi-arch.
FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DATA_DIR=/data

WORKDIR /app

# Build tools are only needed if pip has to compile a wheel (e.g. cryptography
# on 32-bit ARM where no prebuilt wheel exists on PyPI); removed again after
# install to keep the final image small.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        libffi-dev \
        libssl-dev \
        cargo \
        rustc \
        pkg-config \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && apt-get purge -y --auto-remove build-essential cargo rustc pkg-config

COPY app ./app
COPY run.py wsgi.py ./

RUN mkdir -p /data

# Runs as root by design: the app only writes inside the /data volume you
# mount from the host, and running as root avoids UID/GID mismatches with
# host-owned bind mounts on Raspberry Pi OS. If you prefer a non-root user,
# add USER/--uid and chown /data accordingly for your setup.
VOLUME ["/data"]
EXPOSE 5000

# Single worker is required: login/2FA state and running-job tracking are
# kept in the process' memory.
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "1", \
     "--worker-class", "gthread", "--threads", "4", "--timeout", "120", \
     "wsgi:app"]
