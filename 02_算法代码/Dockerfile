# Dockerfile for CP-202606 配电网图模拓扑智能识别与修正系统
# Python 3.11 + pandapower + FastAPI

FROM python:3.11-slim

WORKDIR /app

ENV PYTHONPATH=/app/_legacy_28anomaly:/app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ gfortran libffi-dev && \
    rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project code
COPY . .

# Create output directory
RUN mkdir -p output

# Expose API port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/v1/health')" || exit 1

# Start FastAPI server
CMD ["uvicorn", "--app-dir", "/app/_legacy_28anomaly", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
