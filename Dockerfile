# Reel API image - hosts post_api.py (uvicorn).
# Secrets are NOT baked in; supply them as env vars at deploy time.
FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Source lives in src/ (content_agent, post_api, ...) and the reel audio
# in audio/ for the --video pipeline.
COPY src/ ./src/
COPY audio/ ./audio/

EXPOSE 8000
CMD ["uvicorn", "post_api:app", "--app-dir", "src", "--host", "0.0.0.0", "--port", "8000"]
