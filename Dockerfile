FROM python:3.11-slim

WORKDIR /app

# Copy deps first for layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app code
COPY src/ ./src/
COPY start.sh .

RUN chmod +x start.sh

# Persist chat settings across restarts
VOLUME ["/app/src/settings"]

# Telegram bot — no HTTP port exposed
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import os,sys; sys.exit(0 if any(os.path.exists(f'/proc/{p}/cmdline') and b'src.main' in open(f'/proc/{p}/cmdline','rb').read() for p in os.listdir('/proc') if p.isdigit()) else 1)"

CMD ["python", "-m", "src.main"]
