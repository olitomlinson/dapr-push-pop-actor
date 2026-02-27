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

### S1: Push-Only Workload (To Be Implemented)

**Purpose:** Measure pure write performance and PostgreSQL insert overhead

**File:** `scenarios/s1_push_only.py`

| Variant | Description | Target RPS | Key Metrics |
|---------|-------------|------------|-------------|
| **S1a** | Single queue, single priority (0), ramp 10→100 RPS | 10-100 | Push latency at various loads |
| **S1b** | 10 concurrent queues, single priority, 50 RPS total | 50 | Horizontal scaling validation |
| **S1c** | Single queue, 5 priorities (random), 50 RPS | 50 | Priority overhead measurement |

**Expected bottleneck:** PostgreSQL write throughput

**Implementation notes:**
- No pop operations - pure write workload
- Measures state store insert performance
- Queue depth grows indefinitely (cleanup needed after test)
- Use for establishing write-only baseline

### S2: Pop-Only Workload (To Be Implemented)

**Purpose:** Measure read performance and list slicing overhead

**File:** `scenarios/s2_pop_only.py`

**Requires:** `utils/queue_prepopulator.py` to pre-populate queues

| Variant | Setup | Description | Target RPS |
|---------|-------|-------------|------------|
| **S2a** | 10K items, 1 priority | Pop depth=1, ramp 10→100 RPS | 10-100 |
| **S2b** | 10K items, 3 priorities | Pop depth=10, 50 RPS | 50 |
| **S2c** | 10K items, 3 priorities | Pop depth=100 (max), 20 RPS | 20 |

**Expected bottleneck:** CPU (list slicing), PostgreSQL reads

**Implementation notes:**
- Pre-populate queue before test starts
- Measures state retrieval + list manipulation overhead
- Pop across priorities tests worst-case complexity
- Queue depth decreases - monitor when empty

### S4: Concurrent Queue Scaling (To Be Implemented)

**Purpose:** Validate horizontal scalability across multiple actor IDs

**File:** `scenarios/s4_concurrent.py`

| Variant | Description | Total RPS | Metrics |
|---------|-------------|-----------|---------|
| **S4a** | 1 queue ID, balanced push/pop | 200 | Baseline single queue |
| **S4b** | 10 queue IDs, balanced push/pop | 200 | 10x actors, same total load |
| **S4c** | 50 queue IDs, balanced push/pop | 200 | 50x actors |
| **S4d** | 100 queue IDs, balanced push/pop | 200 | 100x actors |

**Expected behavior:** Linear scaling up to resource limits (CPU, DB connections)

**Implementation notes:**
- Each user targets different queue ID
- Measures actor activation overhead
- Tests Dapr placement service under load
- Monitor PostgreSQL connection count

### S5: Queue Depth Impact (To Be Implemented)

**Purpose:** Measure latency degradation with large queues

**File:** `scenarios/s5_queue_depth.py`

| Variant | Pre-population | Test Operation | Expected Result |
|---------|----------------|----------------|-----------------|
| **S5a** | 0 items | Pop depth=10, 50 RPS | Baseline (empty queue) |
| **S5b** | 1K items | Pop depth=10, 50 RPS | Slight increase |
| **S5c** | 10K items | Pop depth=10, 50 RPS | Moderate increase |
| **S5d** | 100K items | Pop depth=10, 50 RPS | Significant increase |

**Expected bottleneck:** List slicing operations (O(n) complexity)

**Implementation notes:**
- Pre-populate queues with varying depths
- Measure pop latency at each depth
- Tests memory and serialization overhead
- Useful for capacity planning

### S6: Burst Traffic (To Be Implemented)

**Purpose:** Test performance under spiky/irregular load

**File:** `scenarios/s6_burst.py`

| Variant | Pattern | Description |
|---------|---------|-------------|
| **S6a** | Sine wave | Smooth oscillation 10→200→10 RPS over 5 min |
| **S6b** | Square wave | Alternate 30s at 200 RPS, 30s at 10 RPS |
| **S6c** | Spike pattern | 4 min at 50 RPS, 1 min spike to 500 RPS |

**Expected behavior:**
- Latency spikes during burst
- Recovery during calm periods
- No memory leaks over time

**Implementation notes:**
- Uses Locust's LoadTestShape for custom patterns
- Measures latency variance and recovery time
- Tests actor garbage collection
- Validates system stability under irregular load

### S7: Failure Scenarios (To Be Implemented)

**Purpose:** Measure error handling and recovery

**File:** `scenarios/s7_failure.py`

| Variant | Failure Type | Expected Behavior |
|---------|--------------|-------------------|
| **S7a** | Invalid payloads (non-dict items) | 400 errors, no crashes |
| **S7b** | Negative priorities | 400 errors, validation works |
| **S7c** | Pop depth > 100 | 400 errors, enforces limit |
| **S7d** | PostgreSQL restart | 500 errors, then recovery |
| **S7e** | Dapr sidecar restart | Connection errors, auto-reconnect |

**Expected behavior:** Graceful degradation, no data loss

**Implementation notes:**
- Mix valid and invalid requests
- Use `catch_response` to track error types
- Verify error messages are descriptive
- Test recovery after service restart

## Implementation Roadmap

### Phase 1: Foundation (✅ Complete)
- [x] Base user class with custom metrics
- [x] S3 mixed workload scenarios (most important)
- [x] Docker integration
- [x] Warmup script

### Phase 2: Utility Tools (Next Priority)
- [ ] **`utils/queue_prepopulator.py`** - Required for S2 and S5
  - Async bulk population
  - Multi-priority support
  - Progress reporting
- [ ] **`utils/resource_monitor.py`** - System metrics collection
  - Docker stats collector
  - PostgreSQL query monitor
  - Timestamp synchronization
- [ ] **`scripts/analyze_results.py`** - Result analysis
  - Parse Locust CSV outputs
  - Calculate custom percentiles
  - Compare against baseline
  - Generate reports

### Phase 3: Write-Heavy Scenarios
- [ ] **S1a**: Push-only, single queue (simple)
- [ ] **S1b**: Push-only, concurrent queues (S4 dependency)
- [ ] **S1c**: Push-only, multi-priority

### Phase 4: Read-Heavy Scenarios (Requires Phase 2)
- [ ] **S2a**: Pop-only, depth=1
- [ ] **S2b**: Pop-only, depth=10
- [ ] **S2c**: Pop-only, depth=100

### Phase 5: Scaling Tests
- [ ] **S4a-d**: Concurrent queue scaling (1, 10, 50, 100 queues)
- [ ] **S5a-d**: Queue depth impact (0, 1K, 10K, 100K items)

### Phase 6: Advanced Patterns
- [ ] **S6a**: Burst traffic - sine wave
- [ ] **S6b**: Burst traffic - square wave
- [ ] **S6c**: Burst traffic - spike pattern
  - Requires custom LoadTestShape implementation

### Phase 7: Reliability Testing
- [ ] **S7a-c**: Validation error scenarios
- [ ] **S7d-e**: Service failure/recovery scenarios
  - May require orchestration scripts

### Dependencies

```
queue_prepopulator.py
    ├─→ S2 (Pop-only)
    └─→ S5 (Queue depth)

resource_monitor.py
    └─→ All scenarios (enhanced metrics)

analyze_results.py
    └─→ CI/CD integration

S4 (Concurrent)
    └─→ S1b (Multi-queue push test)
```

### Recommended Implementation Order

1. **`utils/queue_prepopulator.py`** - Enables S2 and S5
2. **S1 (Push-only)** - Simple, no dependencies
3. **S2 (Pop-only)** - Uses prepopulator
4. **`utils/resource_monitor.py`** - Adds depth to all tests
5. **S4 (Concurrent)** - Tests horizontal scaling
6. **S5 (Queue depth)** - Uses prepopulator
7. **`scripts/analyze_results.py`** - Automates comparison
8. **S6 (Burst)** - Advanced patterns
9. **S7 (Failure)** - Most complex

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
├── README.md                   # This file (comprehensive docs)
├── requirements.txt            # Python dependencies
├── Dockerfile                  # Locust container image
├── locustfile.py              # Entry point (imports scenarios)
│
├── scenarios/                 # Test scenario implementations
│   ├── base.py                # ✅ Base user class with custom metrics
│   ├── s1_push_only.py        # ⏳ Push-only workload
│   ├── s2_pop_only.py         # ⏳ Pop-only workload (requires prepopulator)
│   ├── s3_mixed.py            # ✅ Mixed push/pop (5 variants, implemented)
│   ├── s4_concurrent.py       # ⏳ Concurrent queue scaling
│   ├── s5_queue_depth.py      # ⏳ Queue depth impact tests
│   ├── s6_burst.py            # ⏳ Burst traffic patterns
│   └── s7_failure.py          # ⏳ Failure/error scenarios
│
├── utils/                     # Utility modules
│   ├── queue_prepopulator.py  # ⏳ Bulk queue loading (Priority 1)
│   ├── resource_monitor.py    # ⏳ System metrics collector (Priority 2)
│   └── metrics.py             # ⏳ Custom metric definitions
│
├── scripts/                   # Automation and analysis
│   ├── warmup.sh              # ✅ Health check and warm-up
│   ├── run_scenario.sh        # ⏳ Single scenario runner
│   ├── run_all_scenarios.sh   # ⏳ Full suite executor
│   └── analyze_results.py     # ⏳ Result analysis and comparison
│
└── results/                   # Test outputs (gitignored)
    ├── baseline.json          # Reference metrics
    └── {test_run}_*.csv       # Per-run results

Legend: ✅ Implemented | ⏳ To be implemented
```

## Scenario Quick Reference

| ID | Name | Status | File | Purpose |
|----|------|--------|------|---------|
| **S1** | Push-Only | ⏳ | `s1_push_only.py` | Write performance baseline |
| **S2** | Pop-Only | ⏳ | `s2_pop_only.py` | Read performance baseline |
| **S3** | Mixed Push/Pop | ✅ | `s3_mixed.py` | Realistic steady-state |
| **S4** | Concurrent Queues | ⏳ | `s4_concurrent.py` | Horizontal scaling |
| **S5** | Queue Depth | ⏳ | `s5_queue_depth.py` | Capacity planning |
| **S6** | Burst Traffic | ⏳ | `s6_burst.py` | Irregular load patterns |
| **S7** | Failure Testing | ⏳ | `s7_failure.py` | Error handling/recovery |

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
