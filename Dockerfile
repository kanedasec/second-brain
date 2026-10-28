FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    SECOND_BRAIN_DATA_DIR=/data

WORKDIR /srv/second-brain

RUN groupadd --gid 10001 secondbrain \
    && useradd --uid 10001 --gid secondbrain --no-create-home --shell /usr/sbin/nologin secondbrain \
    && install -d -o secondbrain -g secondbrain -m 0750 /data

COPY requirements.txt ./
RUN python -m pip install --no-cache-dir --requirement requirements.txt

COPY --chown=secondbrain:secondbrain app ./app

USER 10001:10001
EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=3s --start-period=8s --retries=5 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/ready', timeout=2)"]

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*", "--no-access-log"]
