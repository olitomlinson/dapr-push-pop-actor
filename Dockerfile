FROM python:3.11-slim

WORKDIR /app

# Copy package files
COPY pyproject.toml .
COPY src/ src/
COPY examples/ examples/

# Install package with API extras
RUN pip install --no-cache-dir -e ".[api]"

# Set Python path
ENV PYTHONPATH=/app/src

# Expose API server port
EXPOSE 8000

# Run API server
CMD ["python", "-m", "examples.api_server.main", "--host", "0.0.0.0", "--port", "8000"]
