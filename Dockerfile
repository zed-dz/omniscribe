# OmniScribe — full app (OCR + speech transcription + study materials).
# Builds on Hugging Face Spaces (Docker SDK) or any Docker host. Installs the system
# binaries the serverless cloud edition can't have: Tesseract (+ Arabic/English/French)
# and ffmpeg.
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        tesseract-ocr \
        tesseract-ocr-ara \
        tesseract-ocr-eng \
        tesseract-ocr-fra \
        ffmpeg \
        fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# Run as a non-root user (Hugging Face Spaces best practice).
RUN useradd -m -u 1000 user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    OMNISCRIBE_DATA=/home/user/data \
    OMNISCRIBE_MODELS=/home/user/models \
    TESSERACT_CMD=/usr/bin/tesseract \
    IMAGEIO_FFMPEG_EXE=/usr/bin/ffmpeg \
    OMNISCRIBE_HOST=0.0.0.0 \
    OMNISCRIBE_PORT=7860 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY --chown=user:user requirements-full.txt .
RUN pip install --no-cache-dir -r requirements-full.txt
COPY --chown=user:user . .

USER user
EXPOSE 7860

# Serve the full FastAPI web app.
CMD ["uvicorn", "omniscribe.web.app:app", "--host", "0.0.0.0", "--port", "7860"]
