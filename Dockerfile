FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 TAIMI_DB=/data/taimi.sqlite3
WORKDIR /app
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt && useradd --uid 10001 --create-home taimi && mkdir /data && chown taimi:taimi /data
COPY --chown=taimi:taimi backend/app /app/backend/app
COPY --chown=taimi:taimi src /app/src
COPY --chown=taimi:taimi mobile /app/mobile
COPY --chown=taimi:taimi index.html /app/index.html
WORKDIR /app/backend
USER taimi
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=4)"
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-access-log"]
