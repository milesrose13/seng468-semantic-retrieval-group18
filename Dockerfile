FROM python:3.12-slim AS base

WORKDIR /app

COPY requirements.txt .
# Install CPU-only PyTorch then remaining deps
# Pin numpy<2 to avoid X86_V2 baseline requirement on older VM CPUs
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir "numpy<2" --force-reinstall && \
    pip install --no-cache-dir -r requirements.txt

# Pre-download the embedding model so it doesn't fetch at runtime
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

# --- API ---
FROM base AS api

COPY backend/ ./backend/
COPY alembic/ ./alembic/
COPY alembic.ini .
COPY entrypoint.api.sh .
RUN chmod +x entrypoint.api.sh

WORKDIR /app/backend
CMD ["/app/entrypoint.api.sh"]

# --- Worker ---
FROM base AS worker

COPY backend/ ./backend/

EXPOSE 8080

WORKDIR /app/backend
CMD ["python", "worker.py"]
