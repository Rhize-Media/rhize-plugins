FROM python:3.12-slim-bookworm@sha256:392307d22300de8b5986851a12d9176dfc0fc073e65bf6523ebd7dcbeb23564e
WORKDIR /app
COPY adapters.py worker.py LICENSE provenance.json ./
USER 65534:65534
ENV HOME=/nonexistent PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
ENTRYPOINT ["python", "-I", "/app/worker.py"]
