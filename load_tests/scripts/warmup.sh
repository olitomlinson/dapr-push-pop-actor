#!/bin/bash

# Warmup script for push-pop-actor load tests
# Ensures all services are healthy before starting load tests

set -e

# Configuration
API_HOST="${API_HOST:-http://localhost:8000}"
DAPR_HOST="${DAPR_HOST:-http://localhost:3500}"
MAX_RETRIES=30
RETRY_DELAY=2

echo "=== Push-Pop-Actor Load Test Warmup ==="
echo "API Host: $API_HOST"
echo "Dapr Host: $DAPR_HOST"
echo ""

# Function to check if a URL is responding
check_health() {
    local url=$1
    local name=$2
    local retries=0

    echo -n "Checking $name health... "

    while [ $retries -lt $MAX_RETRIES ]; do
        if curl -sf "$url" > /dev/null 2>&1; then
            echo "✓ OK"
            return 0
        fi

        retries=$((retries + 1))
        echo -n "."
        sleep $RETRY_DELAY
    done

    echo "✗ FAILED (timeout after $((MAX_RETRIES * RETRY_DELAY))s)"
    return 1
}

# Check API server health
if ! check_health "$API_HOST/health" "API Server"; then
    echo "ERROR: API server is not responding"
    exit 1
fi

# Check Dapr sidecar health
if ! check_health "$DAPR_HOST/v1.0/healthz" "Dapr Sidecar"; then
    echo "ERROR: Dapr sidecar is not responding"
    exit 1
fi

# Perform warm-up requests
echo ""
echo "=== Performing warm-up requests ==="

# Create a test queue and do some operations
TEST_QUEUE="warmup-queue-$$"

echo -n "Warm-up: Pushing test items... "
for i in {1..10}; do
    curl -sf -X POST "$API_HOST/queue/$TEST_QUEUE/push" \
        -H "Content-Type: application/json" \
        -d "{\"item\": {\"test\": \"warmup\", \"index\": $i}, \"priority\": 0}" \
        > /dev/null 2>&1 || {
            echo "✗ FAILED"
            exit 1
        }
done
echo "✓ OK (10 items)"

echo -n "Warm-up: Popping test items... "
curl -sf -X POST "$API_HOST/queue/$TEST_QUEUE/pop?depth=10" \
    > /dev/null 2>&1 || {
        echo "✗ FAILED"
        exit 1
    }
echo "✓ OK (10 items)"

# Test with priorities
echo -n "Warm-up: Testing priorities... "
for priority in {0..2}; do
    curl -sf -X POST "$API_HOST/queue/$TEST_QUEUE/push" \
        -H "Content-Type: application/json" \
        -d "{\"item\": {\"test\": \"priority\", \"priority\": $priority}, \"priority\": $priority}" \
        > /dev/null 2>&1 || {
            echo "✗ FAILED"
            exit 1
        }
done
curl -sf -X POST "$API_HOST/queue/$TEST_QUEUE/pop?depth=3" \
    > /dev/null 2>&1 || {
        echo "✗ FAILED"
        exit 1
    }
echo "✓ OK"

# Brief pause to let containers stabilize
echo ""
echo "Waiting 5 seconds for containers to stabilize..."
sleep 5

echo ""
echo "=== Warmup Complete ==="
echo "System is ready for load testing!"
echo ""
echo "Next steps:"
echo "  1. Start web UI:  docker-compose up -d locust && open http://localhost:8089"
echo "  2. Run headless:  docker-compose run --rm locust -f scenarios/s3_mixed.py --users 50 --spawn-rate 5 --run-time 5m --headless"
echo ""

exit 0
