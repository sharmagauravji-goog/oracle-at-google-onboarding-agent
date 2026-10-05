FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Create non-root user for least-privilege execution
RUN groupadd -r odbagent && useradd -r -g odbagent -d /app -s /sbin/nologin odbagent

COPY requirements.txt pyproject.toml README.md ./
COPY ai_agent/ ./ai_agent/

RUN pip install --upgrade pip && \
    pip install -r requirements.txt && \
    pip install -e . && \
    mkdir -p /app/output && \
    chown -R odbagent:odbagent /app

USER odbagent

EXPOSE 8502

ENTRYPOINT ["streamlit", "run", "ai_agent/web.py", "--server.address=127.0.0.1", "--server.port=8502", "--server.headless=true"]
