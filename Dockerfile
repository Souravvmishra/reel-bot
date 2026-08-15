# Reel API image - hosts post_api.py (uvicorn).
# Secrets are NOT baked in; supply them as env vars at deploy time.
FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY *.py ./

EXPOSE 8000
CMD ["uvicorn", "post_api:app", "--host", "0.0.0.0", "--port", "8000"]
