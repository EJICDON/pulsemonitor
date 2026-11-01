FROM python:3.11-slim

WORKDIR /opt/pulsemonitor

# Install build essentials for psutil if needed & procps/lsof
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc python3-dev procps curl && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY VERSION app.py run.sh ./
COPY static ./static

EXPOSE 8788

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8788"]
