FROM python:3.11-slim

# Install build dependencies for psutil, then install Python packages, then clean up
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc python3-dev && \
    pip install --no-cache-dir \
        locust==2.24.1 \
        httpx==0.27.0 \
        pandas==2.2.0 \
        psutil==5.9.8 && \
    apt-get purge -y gcc python3-dev && \
    apt-get autoremove -y && \
    rm -rf /var/lib/apt/lists/*

# Create locust user and directories
RUN useradd -m -u 1000 locust
WORKDIR /home/locust

# Copy load test files
COPY --chown=locust:locust . .

# Create results directory
RUN mkdir -p results && chown locust:locust results

USER locust

# Default to master mode (web UI)
ENTRYPOINT ["locust"]
