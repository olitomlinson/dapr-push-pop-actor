FROM python:3.11-slim

# Create non-root user
RUN useradd -m -u 1000 locust

# Set working directory
WORKDIR /home/locust

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy test files
COPY . .

# Switch to non-root user
USER locust

# Expose Locust web UI port
EXPOSE 8089

# Default command
CMD ["locust"]
