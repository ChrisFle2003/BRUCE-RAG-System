# BRUCE RAG Stress Benchmark Report 🔥
*Generated: 2026-03-03T07:40:11.000717*
*Duration: 96.3s*

## Overview

Comprehensive stress testing of the BRUCE RAG system to identify performance limits and breaking points.

**Test Strategy:**
- Load testing with increasing concurrency
- Complex/long query stress testing
- Edge case and security boundary testing
- Sustained load stability testing
- Peak concurrent load testing

## System Status

- API: http://localhost:9998

- Test Start: 2026-03-03T07:38:34.751027


## Test 1: Progressive Load Testing
*2026-03-03T07:38:34.751035*

Testing increasing levels of concurrency to find the optimal load and identify breaking points.


### Light (1 worker, 5 queries)
- **Total Queries:** 5
- **Successful:** 5
- **Failed:** 0
- **Success Rate %:** 100.000
- **Total Time (s):** 0.372
- **Throughput (q/s):** 13.435
- **Avg Latency (s):** 0.074
- **Min Latency (s):** 0.065
- **Max Latency (s):** 0.091
- **P95 Latency (s):** 0.100
- **Avg Quality:** 0.960

### Moderate (2 workers, 10 queries)
- **Total Queries:** 10
- **Successful:** 10
- **Failed:** 0
- **Success Rate %:** 100.000
- **Total Time (s):** 0.350
- **Throughput (q/s):** 28.577
- **Avg Latency (s):** 0.067
- **Min Latency (s):** 0.059
- **Max Latency (s):** 0.077
- **P95 Latency (s):** 0.077
- **Avg Quality:** 0.960

### Heavy (4 workers, 20 queries)
- **Total Queries:** 20
- **Successful:** 20
- **Failed:** 0
- **Success Rate %:** 100.000
- **Total Time (s):** 0.462
- **Throughput (q/s):** 43.306
- **Avg Latency (s):** 0.087
- **Min Latency (s):** 0.068
- **Max Latency (s):** 0.121
- **P95 Latency (s):** 0.120
- **Avg Quality:** 0.960

### Very Heavy (6 workers, 30 queries)
- **Total Queries:** 30
- **Successful:** 30
- **Failed:** 0
- **Success Rate %:** 100.000
- **Total Time (s):** 0.604
- **Throughput (q/s):** 49.683
- **Avg Latency (s):** 0.113
- **Min Latency (s):** 0.075
- **Max Latency (s):** 0.211
- **P95 Latency (s):** 0.179
- **Avg Quality:** 0.960

### Extreme (10 workers, 50 queries)
- **Total Queries:** 50
- **Successful:** 50
- **Failed:** 0
- **Success Rate %:** 100.000
- **Total Time (s):** 1.061
- **Throughput (q/s):** 47.111
- **Avg Latency (s):** 0.195
- **Min Latency (s):** 0.099
- **Max Latency (s):** 0.312
- **P95 Latency (s):** 0.253
- **Avg Quality:** 0.960

## Test 2: Complex Query Stress Test
*2026-03-03T07:38:37.601002*

Testing with longer, more complex queries to stress the system's processing capacity.


### Complex Query Test
- **Total Queries:** 6
- **Successful:** 6
- **Failed:** 0
- **Success Rate %:** 100.000
- **Total Time (s):** 0.190
- **Throughput (q/s):** 31.530
- **Avg Latency (s):** 0.085
- **Min Latency (s):** 0.065
- **Max Latency (s):** 0.102
- **P95 Latency (s):** 0.102
- **Avg Quality:** 0.960

## Test 3: Edge Cases & Security Boundary Testing
*2026-03-03T07:38:37.791414*

Testing boundary conditions and potential security issues.

### Edge Case Results


| Test Case | Query | Success | Error | Time (s) |
|---|---|---|---|---|
| empty | (empty) | ✗ | HTTP Error 422: Unprocessable Entity | 0.00 |
| whitespace |     | ✓ | assembled | 0.00 |
| very_long | AAAAAAAAAAAAAAAAAAAAAAAAA | ✓ | assembled | 0.00 |
| sql_injection | SELECT * FROM seiten; | ✓ | assembled | 0.00 |
| xss | <script>alert('xss')</scr | ✓ | assembled | 0.00 |
| unicode | üüüüüüüüüüüüüüüüüüüüüüüüü | ✓ | assembled | 0.00 |
| newlines | query


query | ✓ | assembled | 0.00 |
| special_chars | !@#$%^&*()[]{} | ✓ | assembled | 0.00 |

## Test 4: Sustained Load Stability Test (90 seconds)
*2026-03-03T07:38:38.799892*

Running continuous queries to test system stability under sustained load.


### 90-Second Sustained Load
- **Duration (s):** 90.004
- **Total Queries:** 1674
- **Successful:** 1674
- **Success Rate %:** 100.000
- **Avg Throughput (q/s):** 18.599
- **Avg Latency (s):** 0.082
- **Min Latency (s):** 0.056
- **Max Latency (s):** 0.968

## Test 5: Peak Concurrent Load Test
*2026-03-03T07:40:08.804618*

Maximal concurrent load to test the absolute limits of the system.


### Peak Concurrent Load
- **Total Queries:** 100
- **Successful:** 100
- **Failed:** 0
- **Success Rate %:** 100.000
- **Total Time (s):** 2.196
- **Throughput (q/s):** 45.544
- **Avg Latency (s):** 0.411
- **Min Latency (s):** 0.178
- **Max Latency (s):** 0.610
- **P95 Latency (s):** 0.524
- **Avg Quality:** 0.960

## Summary & Analysis
*2026-03-03T07:40:11.000677*
### Load Test Comparison


| Test | Concurrency | Queries | Success % | Avg Latency (s) | Throughput (q/s) |
|---|---|---|---|---|---|
| Light | (1 | 5 | 100.0 | 0.07 | 13.4 |
| Moderate | (2 | 10 | 100.0 | 0.07 | 28.6 |
| Heavy | (4 | 20 | 100.0 | 0.09 | 43.3 |
| Very Heavy | (6 | 30 | 100.0 | 0.11 | 49.7 |
| Extreme | (10 | 50 | 100.0 | 0.20 | 47.1 |

### Performance Analysis

✓ **System maintains high success rate across all load levels!**


### Bottleneck Analysis & Recommendations


**Current Performance Ceiling:** 49.7 queries/second

**Optimization Opportunities:**
1. **Embedding Service**: Pre-compute and cache frequent embeddings (20-30% speedup expected)
2. **Database Connection Pool**: Implement pgbouncer or sqlalchemy pool (15-25% speedup)
3. **Vector Index**: Verify HNSW index is active on vektoren table (10-40% speedup for retrieval)
4. **Async Polling**: Replace REST polling with WebSockets (50%+ latency reduction)
5. **Multi-instance Calc**: Deploy calc_bruce and calc_docs_de in replicas (linear scaling)
6. **Query Caching**: Implement Redis for identical query deduplication (variable based on patterns)
7. **Partition Pruning**: Verify seiten partitioning is working (10-20% speedup for large datasets)
8. **Batch Processing**: Support batch queries endpoint for bulk operations (3-5x throughput)


---
*Benchmark completed at 2026-03-03T07:40:11.000714*

