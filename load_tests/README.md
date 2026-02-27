# Load Testing for Push-Pop Actor

Comprehensive load testing framework for benchmarking real-world latencies and performance characteristics of the push-pop-actor queue system.

## Overview

This framework uses [Locust](https://locust.io/) to measure:
- **Latency metrics** (p50, p95, p99) for push/pop operations
- **Throughput** (requests/sec, items/sec)
- **Error rates** under various load conditions
- **Queue depth impact** on performance
- **Priority queue performance**
- **Resource utilization** (CPU, memory, database)

## Quick Start

### 1. Start the Full Stack

```bash
# From project root
docker-compose up -d

# Wait for services to be healthy
./load_tests/scripts/warmup.sh
```

### 2. Access Locust Web UI

```bash
# Open browser to http://localhost:8089
open http://localhost:8089

# Or for Linux
xdg-open http://localhost:8089
```

In the web UI:
1. Select user class: `MixedWorkloadUser` (recommended to start)
2. Number of users: `50`
3. Spawn rate: `5` (users per second)
4. Host: `http://api-server:8000` (pre-filled)
5. Click "Start swarming"

### 3. Run Headless (CLI Mode)

```bash
# Run mixed workload test (most realistic)
docker-compose run --rm locust \
  -f /home/locust/scenarios/s3_mixed.py \
  --host http://api-server:8000 \
  --users 50 \
  --spawn-rate 5 \
  --run-time 5m \
  --headless \
  --csv /home/locust/results/mixed_test \
  --html /home/locust/results/mixed_test.html

# Results will be in ./results/
```

## Test Scenarios

### S3: Mixed Push/Pop (Production-Ready)

**Most important for realistic testing.**

| Variant | File | Description | Target RPS |
|---------|------|-------------|------------|
| **S3a** | `scenarios/s3_mixed.py` → `MixedWorkloadUser` | Balanced 50/50 push/pop | 50 |
| **S3b** | `scenarios/s3_mixed.py` → `ProducerHeavyUser` | 80% push, 20% pop (growing queue) | 100 |
| **S3c** | `scenarios/s3_mixed.py` → `ConsumerHeavyUser` | 20% push, 80% pop (draining queue) | 100 |
| **S3d** | `scenarios/s3_mixed.py` → `MultiPriorityMixedUser` | Multiple priorities (0-4) | 50 |
| **S3e** | `scenarios/s3_mixed.py` → `BalancedLargeItemsUser` | Medium/large payloads (~1-10KB) | 50 |

**Start here:** Use `MixedWorkloadUser` (S3a) for your first test.

### Other Scenarios (To Be Implemented)

- **S1**: Push-only workload (write performance)
- **S2**: Pop-only workload (read performance, requires pre-population)
- **S4**: Concurrent queue scaling (multiple actor IDs)
- **S5**: Queue depth impact (large queues)
- **S6**: Burst traffic patterns
- **S7**: Failure scenarios (error handling)

## Usage Modes

### Mode 1: Web UI (Interactive)

**Best for:** Experimentation, real-time monitoring, quick tests

```bash
# Start services
docker-compose up -d

# Access UI
open http://localhost:8089
```

**Features:**
- Real-time charts (RPS, latency, errors)
- Start/stop tests on demand
- Adjust user count during test
- Download CSV/HTML reports
- Multiple scenario selection

### Mode 2: Headless CLI (Automation)

**Best for:** CI/CD, baseline measurement, scripting

```bash
# Run specific scenario
docker-compose run --rm locust \
  -f /home/locust/scenarios/s3_mixed.py \
  --host http://api-server:8000 \
  --users 50 \
  --spawn-rate 5 \
  --run-time 5m \
  --headless \
  --csv /home/locust/results/test_run \
  --html /home/locust/results/test_run.html

# Results in ./results/test_run_*.csv
```

**Output files:**
- `test_run_stats.csv` - Request statistics
- `test_run_failures.csv` - Error details
- `test_run.html` - HTML report with charts

### Mode 3: Python Script

**Best for:** Custom orchestration, complex workflows

```bash
# Execute custom script inside container
docker-compose exec locust python /home/locust/scripts/my_custom_test.py
```

### Mode 4: Distributed (High Load)

**Best for:** Testing beyond single machine limits

First, add worker service to `docker-compose.yml` (see plan document).

```bash
# Start master + 4 workers
docker-compose up -d locust-master
docker-compose up -d --scale locust-worker=4

# Access master UI
open http://localhost:8089

# Workers automatically connect and distribute load
```

## Metrics Reference

### Latency Metrics

| Metric | Description | Target |
|--------|-------------|--------|
| **p50** (median) | Typical user experience | <30ms |
| **p95** | 95% of requests faster than this | <50ms |
| **p99** | 99% of requests faster than this | <100ms |
| **max** | Worst-case latency | <500ms |

### Throughput Metrics

- **Requests/second** - Total API requests (push + pop)
- **Items/second** - Actual items processed (pop depth matters)
- **Concurrent users** - Simulated users making requests

### Error Metrics

- **Error rate %** - Percentage of failed requests
- **Timeout rate %** - Requests exceeding threshold
- **Error types** - 400 (validation), 500 (server), timeouts

## Expected Baseline Performance

Based on architecture (PostgreSQL state store, no caching):

| Operation | p50 | p95 | p99 | Notes |
|-----------|-----|-----|-----|-------|
| **Push** | 15-25ms | 20-50ms | 30-80ms | PostgreSQL write latency |
| **Pop (depth=1)** | 20-30ms | 30-80ms | 50-120ms | Read + list slicing |
| **Pop (depth=10)** | 25-40ms | 40-100ms | 60-150ms | More list operations |
| **Pop (depth=100)** | 40-60ms | 60-150ms | 100-250ms | Significant CPU work |

**Note:** Actual performance depends on:
- Hardware resources
- PostgreSQL configuration
- Queue depth
- Number of priorities
- Concurrent actors

## Results Analysis

### View Results in Web UI

While test is running, charts show:
- Total requests per second
- Response times (median, 95th percentile)
- Number of users
- Failures

### Analyze CSV Output

```bash
# View statistics
cat results/test_run_stats.csv

# View failures
cat results/test_run_failures.csv

# Use analysis script (to be implemented)
python scripts/analyze_results.py results/test_run_stats.csv
```

### Key Metrics to Watch

1. **Response time trends**: Should be stable, not increasing
2. **Error rate**: Should be <1% under normal load
3. **Throughput saturation**: Point where latency spikes
4. **Resource utilization**: Check `docker stats` during test

## Troubleshooting

### Issue: "Connection refused" errors

**Cause:** Services not fully started

**Solution:**
```bash
# Run warmup script
./load_tests/scripts/warmup.sh

# Check service health
docker-compose ps
docker-compose logs api-server
docker-compose logs api-server-dapr
```

### Issue: High latency from start

**Cause:** Cold containers, need warm-up

**Solution:**
- Run warmup script first
- Ignore first 30-60 seconds of test data
- Use Locust's built-in warm-up period

### Issue: Tests show 0 RPS

**Cause:** Wrong host configuration

**Solution:**
```bash
# For web UI, use: http://api-server:8000 (internal Docker network)
# For local testing, use: http://localhost:8000

# Check Locust logs
docker-compose logs locust
```

### Issue: "No module named 'scenarios'"

**Cause:** Volume mount issue or Dockerfile not built

**Solution:**
```bash
# Rebuild Locust container
docker-compose build locust

# Restart
docker-compose restart locust
```

### Issue: Memory growing during test

**Cause:** Possible actor instance accumulation

**Solution:**
- Check `docker stats` during test
- Review Dapr actor idle timeout settings
- Limit test duration

## Advanced Topics

### Custom Metrics

Edit `scenarios/base.py` to add custom tracking:

```python
# Track custom metric
self.environment.events.request.fire(
    request_type="custom",
    name="queue_depth_check",
    response_time=duration_ms,
    response_length=queue_depth,
    exception=None
)
```

### Resource Monitoring

Run alongside load test to correlate performance:

```bash
# Docker stats
watch -n 5 docker stats

# PostgreSQL connections
docker exec postgres-db psql -U postgres -d actor_state -c \
  "SELECT count(*) FROM pg_stat_activity WHERE datname='actor_state';"
```

### Compare Against Baseline

```bash
# 1. Run baseline test
docker-compose run --rm locust \
  -f scenarios/s3_mixed.py \
  --users 50 --spawn-rate 5 --run-time 5m \
  --headless --csv results/baseline

# 2. Save baseline
cp results/baseline_stats.csv results/baseline_reference.csv

# 3. After code changes, run again and compare
# (Use analyze_results.py script - to be implemented)
```

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Load Test

on:
  pull_request:
    branches: [main]

jobs:
  load-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Start services
        run: docker-compose up -d

      - name: Wait for health
        run: ./load_tests/scripts/warmup.sh

      - name: Run load test
        run: |
          docker-compose run --rm locust \
            -f scenarios/s3_mixed.py \
            --users 50 --spawn-rate 5 --run-time 60s \
            --headless --csv results/ci_test

      - name: Check thresholds
        run: |
          # Fail if p95 > 100ms or error rate > 1%
          python scripts/check_thresholds.py results/ci_test_stats.csv

      - name: Upload results
        uses: actions/upload-artifact@v3
        with:
          name: load-test-results
          path: results/
```

## Project Structure

```
load_tests/
├── README.md                   # This file
├── requirements.txt            # Python dependencies
├── Dockerfile                  # Locust container image
├── locustfile.py              # Entry point (imports scenarios)
│
├── scenarios/
│   ├── base.py                # Base user class
│   └── s3_mixed.py            # Mixed workload (most important)
│
├── utils/                     # Utilities (to be implemented)
│   ├── queue_prepopulator.py
│   ├── resource_monitor.py
│   └── metrics.py
│
├── scripts/
│   ├── warmup.sh              # Health check script
│   ├── run_scenario.sh        # (to be implemented)
│   └── analyze_results.py     # (to be implemented)
│
└── results/                   # Test outputs (gitignored)
    ├── baseline.json
    └── {test_run}_*.csv
```

## Next Steps

1. **Run your first test**: Use S3a (MixedWorkloadUser) with 50 users
2. **Establish baseline**: Document p50/p95/p99 for your environment
3. **Implement additional scenarios**: S1, S2, S4-S7 as needed
4. **Add analysis scripts**: Automate result comparison
5. **Set up CI/CD**: Run smoke tests on every PR

## Resources

- [Locust Documentation](https://docs.locust.io/)
- [Dapr Performance Tuning](https://docs.dapr.io/operations/performance-and-scalability/)
- [PostgreSQL Performance](https://www.postgresql.org/docs/current/performance-tips.html)

## Support

For issues or questions:
- Check [troubleshooting section](#troubleshooting)
- Review [plan document](../.claude/plans/gleaming-gliding-wadler.md)
- Open GitHub issue with test results
