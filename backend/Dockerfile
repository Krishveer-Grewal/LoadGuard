FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 curl \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app

COPY requirements.txt requirements-yolo.txt ./
RUN pip install -r requirements.txt

# Pre-trained YOLO (CPU build of torch keeps the image small). Set INSTALL_YOLO=false for a
# lightweight image that uses the classical OpenCV detector only.
ARG INSTALL_YOLO=true
RUN if [ "$INSTALL_YOLO" = "true" ]; then \
      pip install --index-url https://download.pytorch.org/whl/cpu torch torchvision && \
      pip install -r requirements-yolo.txt && \
      (python -c "from ultralytics import YOLO; YOLO('yolo11n.pt')" || echo "weights will download at runtime"); \
    fi

COPY app ./app
COPY tests ./tests
ENV LG_DATA_DIR=/data
VOLUME /data
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=60s CMD curl -fs http://localhost:8000/api/health || exit 1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
