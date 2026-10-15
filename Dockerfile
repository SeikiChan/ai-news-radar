# AI News Radar — container image for 24/7 cloud deployment.
# Runtime is standard-library + tzdata + pypdf, so the image stays tiny.
FROM python:3.12-slim

WORKDIR /app

# Install the package first (better layer caching: deps rarely change).
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir -e .

# Persistent runtime data (FINRA cache, IV history, diagnosis archive, signals)
# lives here; mount a volume at /app/data so it survives container restarts.
VOLUME ["/app/data"]

# Bind to all interfaces inside the container; the host/platform maps the port.
# AI_NEWS_RADAR_PASSWORD MUST be set at runtime — the server refuses to bind to
# a non-localhost interface without it.
ENV PORT=8765
EXPOSE 8765

# Shell form so $PORT expands; serve() enforces the password gate.
CMD python -m src.abnormal_news_radar web --host 0.0.0.0 --port ${PORT}
