FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=120

ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
ARG PIP_TRUSTED_HOST=pypi.tuna.tsinghua.edu.cn
ENV PIP_INDEX_URL=${PIP_INDEX_URL} \
    PIP_TRUSTED_HOST=${PIP_TRUSTED_HOST}

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /build
COPY pyproject.toml README.md ./
COPY tradingagents ./tradingagents
COPY cli ./cli
RUN pip install --no-cache-dir .

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=Asia/Shanghai \
    TRADINGAGENTS_TIMEZONE=Asia/Shanghai \
    TRADINGAGENTS_WEB_HOST=0.0.0.0 \
    TRADINGAGENTS_WEB_PORT=8000 \
    TRADINGAGENTS_WEB_DB=/data/web.sqlite3 \
    TRADINGAGENTS_WEB_RUNNER=demo

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /data /home/appuser/.tradingagents/cache /home/appuser/.tradingagents/results \
    && chown -R appuser:appuser /data /home/appuser/.tradingagents

USER appuser
WORKDIR /home/appuser/app

COPY --from=builder --chown=appuser:appuser /build /home/appuser/app

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=5 \
  CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"TRADINGAGENTS_WEB_PORT\", \"8000\")}/api/health', timeout=3).read()"

CMD ["python", "-m", "tradingagents.web.main"]
