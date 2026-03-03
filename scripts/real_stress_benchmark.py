#!/usr/bin/env python3
"""
BRUCE RAG Stress Benchmark Suite v2
Real stress testing against live system.
"""

import concurrent.futures
import json
import statistics
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import URLError


class BenchmarkLogger:
    def __init__(self, output_file: str = "BENCHMARK.md"):
        self.output_file = Path(output_file)
        self.results = []
        self.start_time = datetime.now()

    def log_header(self, title: str, level: int = 2):
        """Log a section header"""
        prefix = "#" * level
        self.results.append(f"\n{prefix} {title}\n")
        self.results.append(f"*{datetime.now().isoformat()}*\n")

    def log_result(self, test_name: str, metrics: dict[str, Any]):
        """Log a test result"""
        self.results.append(f"\n### {test_name}\n")
        for key, value in metrics.items():
            if isinstance(value, float):
                self.results.append(f"- **{key}:** {value:.3f}\n")
            elif isinstance(value, int):
                self.results.append(f"- **{key}:** {value}\n")
            else:
                self.results.append(f"- **{key}:** {value}\n")

    def log_table(self, headers: list[str], rows: list[list]):
        """Log a markdown table"""
        self.results.append(f"\n| {' | '.join(headers)} |\n")
        self.results.append(f"|{'|'.join(['---'] * len(headers))}|\n")
        for row in rows:
            formatted = [str(v) if not isinstance(v, float) else f"{v:.2f}" for v in row]
            self.results.append(f"| {' | '.join(formatted)} |\n")

    def log_section(self, text: str):
        """Log arbitrary text"""
        self.results.append(f"{text}\n")

    def save(self, filepath: str | None = None):
        """Save results to file"""
        target = filepath or str(self.output_file)
        content = f"""# BRUCE RAG Stress Benchmark Report 🔥
*Generated: {datetime.now().isoformat()}*
*Duration: {(datetime.now() - self.start_time).total_seconds():.1f}s*

## Overview

Comprehensive stress testing of the BRUCE RAG system to identify performance limits and breaking points.

**Test Strategy:**
- Load testing with increasing concurrency
- Complex/long query stress testing
- Edge case and security boundary testing
- Sustained load stability testing
- Peak concurrent load testing

"""
        content += "".join(self.results)
        Path(target).write_text(content, encoding="utf-8")
        print(f"\n✓ Benchmark report saved to {target}")


# Test queries
SHORT_QUERIES = [
    "Was ist pgvector?",
    "Erkläre Bruce Router",
    "Wie funktioniert Assembler?",
    "Was ist Whitelist?",
    "Erkläre Hierarchical Guard",
]

LONG_QUERIES = [
    "Schreibe einen detaillierten Bericht über die komplette Architektur des Bruce Routers mit allen Komponenten, deren Funktionen und Wechselwirkungen",
    "Erkläre die gesamte Startup-Sequenz von Bruce RAG inklusive aller Validierungen und wie pgvector integriert wird",
    "Analysiere die Hierarchical Guard Konfidenzregeln detailliert und wie sie während der Query-Verarbeitung angewendet werden",
]

EDGE_CASES = [
    ("empty", ""),
    ("whitespace", "   "),
    ("very_long", "A" * 500),
    ("sql_injection", "SELECT * FROM seiten;"),
    ("xss", "<script>alert('xss')</script>"),
    ("unicode", "ü" * 30),
    ("newlines", "query\n\n\nquery"),
    ("special_chars", "!@#$%^&*()[]{}"),
]


def submit_and_poll(api_base: str, query: str, max_poll_time: float = 45.0) -> dict[str, Any]:
    """Submit query and poll for result, return detailed metrics"""
    try:
        # Submit phase
        submit_start = time.perf_counter()
        payload = json.dumps({"query": query, "language": "de"}).encode("utf-8")
        req = urllib.request.Request(
            f"{api_base}/api/v1/queries",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=10) as response:
            result_data = json.loads(response.read().decode("utf-8"))
            query_id = result_data.get("query_id")
            submit_time = time.perf_counter() - submit_start

        if not query_id:
            return {
                "success": False,
                "error": "no_query_id",
                "submit_time_ms": round(submit_time * 1000, 1),
                "total_time_ms": round(submit_time * 1000, 1),
            }

        # Polling phase with adaptive sleep
        poll_start = time.perf_counter()
        deadline = poll_start + max_poll_time
        polls = 0
        status = "unknown"

        while time.perf_counter() < deadline:
            polls += 1
            try:
                with urllib.request.urlopen(
                    f"{api_base}/api/v1/queries/{query_id}", timeout=5
                ) as response:
                    poll_result = json.loads(response.read().decode("utf-8"))
                    status = poll_result.get("status")

                if status == "assembled":
                    poll_time = time.perf_counter() - poll_start
                    return {
                        "success": True,
                        "status": status,
                        "submit_time_ms": round(submit_time * 1000, 1),
                        "poll_time_ms": round(poll_time * 1000, 1),
                        "total_time_ms": round((submit_time + poll_time) * 1000, 1),
                        "polls": polls,
                        "quality": float((poll_result.get("result") or {}).get("quality") or 0.0),
                    }
            except Exception:
                pass

            # Adaptive polling: fast at first, slower later
            if polls <= 5:
                time.sleep(0.01)   # First 5 polls: every 10ms (0-50ms range)
            elif polls <= 20:
                time.sleep(0.05)   # Next 15 polls: every 50ms (50-800ms range)
            else:
                time.sleep(0.2)    # Danach: every 200ms (slow queries/timeouts)

        poll_time = time.perf_counter() - poll_start
        return {
            "success": False,
            "error": "timeout",
            "status": status,
            "submit_time_ms": round(submit_time * 1000, 1),
            "poll_time_ms": round(poll_time * 1000, 1),
            "total_time_ms": round((submit_time + poll_time) * 1000, 1),
            "polls": polls,
        }

    except Exception as e:
        total_time = time.perf_counter() - submit_start if 'submit_start' in locals() else 0
        return {
            "success": False,
            "error": str(e),
            "total_time_ms": round(total_time * 1000, 1),
        }


def run_load_test(api_base: str, queries: list[str], concurrency: int, name: str) -> dict:
    """Run concurrent load test"""
    print(f"\n▶ {name} ({concurrency} parallel, {len(queries)} queries)")

    start = time.perf_counter()
    results = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [executor.submit(submit_and_poll, api_base, q) for q in queries]

        for i, future in enumerate(concurrent.futures.as_completed(futures), 1):
            try:
                result = future.result()
                results.append(result)
                if i % max(1, len(queries) // 10) == 0:
                    print(f"  {i}/{len(queries)} completed")
            except Exception as e:
                results.append({"success": False, "error": str(e)})

    total_time = time.perf_counter() - start

    # Calculate metrics
    successful = sum(1 for r in results if r.get("success"))
    failed = len(results) - successful
    success_rate = 100 * successful / len(results) if results else 0

    metrics = {
        "Total Queries": len(results),
        "Successful": successful,
        "Failed": failed,
        "Success Rate %": success_rate,
        "Total Time (s)": total_time,
        "Throughput (q/s)": len(results) / total_time if total_time > 0 else 0,
    }

    if successful > 0:
        successful_results = [r for r in results if r.get("success")]
        latencies = [r["total_time_ms"] / 1000.0 for r in successful_results]
        metrics.update({
            "Avg Latency (s)": statistics.mean(latencies),
            "Min Latency (s)": min(latencies),
            "Max Latency (s)": max(latencies),
            "P95 Latency (s)": statistics.quantiles(latencies, n=20)[18] if len(latencies) > 1 else latencies[0],
            "Avg Quality": statistics.mean(r.get("quality", 0.9) for r in successful_results),
        })

    # Error breakdown
    errors = {}
    for r in results:
        if not r.get("success"):
            err = r.get("error", "unknown")
            errors[err] = errors.get(err, 0) + 1

    if errors:
        metrics["Errors"] = errors

    return metrics


def main():
    api_base = "http://localhost:9998"
    logger = BenchmarkLogger("BENCHMARK.md")

    # Check API is running
    print("🔍 Checking API health...")
    try:
        with urllib.request.urlopen(f"{api_base}/api/v1/health", timeout=5) as r:
            health = json.loads(r.read())
            print(f"✓ API is ready: {health}")
    except Exception as e:
        print(f"✗ API not responding: {e}")
        print("  Make sure to run: docker compose up -d")
        sys.exit(1)

    logger.log_section("## System Status\n")
    logger.log_section(f"- API: {api_base}\n")
    logger.log_section(f"- Test Start: {datetime.now().isoformat()}\n")

    # ===== TEST 1: Progressive Load =====
    logger.log_header("Test 1: Progressive Load Testing")
    logger.log_section("""
Testing increasing levels of concurrency to find the optimal load and identify breaking points.
""")

    load_configs = [
        (SHORT_QUERIES * 1, 1, "Light (1 worker, 5 queries)"),
        (SHORT_QUERIES * 2, 2, "Moderate (2 workers, 10 queries)"),
        (SHORT_QUERIES * 4, 4, "Heavy (4 workers, 20 queries)"),
        (SHORT_QUERIES * 6, 6, "Very Heavy (6 workers, 30 queries)"),
        (SHORT_QUERIES * 10, 10, "Extreme (10 workers, 50 queries)"),
    ]

    load_results = []
    for queries, concurrency, name in load_configs:
        metrics = run_load_test(api_base, queries, concurrency, name)
        logger.log_result(name, metrics)
        load_results.append((name, metrics))

    # ===== TEST 2: Complex Queries =====
    logger.log_header("Test 2: Complex Query Stress Test")
    logger.log_section("""
Testing with longer, more complex queries to stress the system's processing capacity.
""")

    long_test_queries = LONG_QUERIES * 2
    complex_metrics = run_load_test(api_base, long_test_queries, 3, "Complex Queries (3 workers, 6 long queries)")
    logger.log_result("Complex Query Test", complex_metrics)

    # ===== TEST 3: Edge Cases =====
    logger.log_header("Test 3: Edge Cases & Security Boundary Testing")
    logger.log_section("""
Testing boundary conditions and potential security issues.
""")

    edge_results = []
    print("\n▶ Edge Case Testing")

    for case_name, query in EDGE_CASES:
        result = submit_and_poll(api_base, query, max_poll_time=30.0)
        edge_results.append({
            "Test Case": case_name,
            "Query": query[:25] if query else "(empty)",
            "Success": "✓" if result.get("success") else "✗",
            "Error": result.get("error", result.get("status", "-")),
            "Time (s)": result.get("total_time", 0),
        })
        status = "✓" if result.get("success") else "✗"
        print(f"  {status} {case_name:20} → {result.get('error', result.get('status'))}")

    logger.log_section("### Edge Case Results\n")
    logger.log_table(
        ["Test Case", "Query", "Success", "Error", "Time (s)"],
        [[r["Test Case"], r["Query"], r["Success"], r["Error"], f"{r['Time (s)']:.2f}"] for r in edge_results],
    )

    # ===== TEST 4: Sustained Load =====
    logger.log_header("Test 4: Sustained Load Stability Test (90 seconds)")
    logger.log_section("""
Running continuous queries to test system stability under sustained load.
""")

    print("\n▶ Sustained Load Test (90 seconds, 2 workers)")
    sustained_start = time.perf_counter()
    sustained_results = []
    query_count = 0

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        futures = []

        while time.perf_counter() - sustained_start < 90:
            # Keep queue filled
            while len(futures) < 4 and time.perf_counter() - sustained_start < 90:
                query = SHORT_QUERIES[query_count % len(SHORT_QUERIES)]
                futures.append(executor.submit(submit_and_poll, api_base, query, 60.0))
                query_count += 1

            # Collect finished
            remaining = []
            for future in futures:
                if future.done():
                    try:
                        result = future.result()
                        sustained_results.append(result)
                    except:
                        sustained_results.append({"success": False})
                else:
                    remaining.append(future)

            futures = remaining
            time.sleep(0.1)

    sustained_time = time.perf_counter() - sustained_start
    sustained_successful = sum(1 for r in sustained_results if r.get("success"))

    sustained_metrics = {
        "Duration (s)": sustained_time,
        "Total Queries": len(sustained_results),
        "Successful": sustained_successful,
        "Success Rate %": 100 * sustained_successful / len(sustained_results) if sustained_results else 0,
        "Avg Throughput (q/s)": len(sustained_results) / sustained_time,
    }

    if sustained_successful > 0:
        sustained_latencies = [r["total_time_ms"] / 1000.0 for r in sustained_results if r.get("success")]
        sustained_metrics.update({
            "Avg Latency (s)": statistics.mean(sustained_latencies),
            "Min Latency (s)": min(sustained_latencies),
            "Max Latency (s)": max(sustained_latencies),
        })

    logger.log_result("90-Second Sustained Load", sustained_metrics)

    # ===== TEST 5: Peak Load =====
    logger.log_header("Test 5: Peak Concurrent Load Test")
    logger.log_section("""
Maximal concurrent load to test the absolute limits of the system.
""")

    peak_queries = SHORT_QUERIES * 20  # 100 queries
    peak_metrics = run_load_test(api_base, peak_queries, 20, "Peak Load (20 workers, 100 queries)")
    logger.log_result("Peak Concurrent Load", peak_metrics)

    # ===== Summary =====
    logger.log_header("Summary & Analysis")

    logger.log_section("### Load Test Comparison\n")
    logger.log_table(
        ["Test", "Concurrency", "Queries", "Success %", "Avg Latency (s)", "Throughput (q/s)"],
        [
            [
                name.split("(")[0].strip(),
                name.split("worker")[0].split()[-1],
                f"{metrics['Total Queries']}",
                f"{metrics['Success Rate %']:.1f}",
                f"{metrics.get('Avg Latency (s)', 0):.2f}",
                f"{metrics['Throughput (q/s)']:.1f}",
            ]
            for name, metrics in load_results
        ],
    )

    # Breaking point detection
    logger.log_section("\n### Performance Analysis\n")

    breaking_detected = False
    for name, metrics in load_results:
        if metrics["Success Rate %"] < 100:
            logger.log_section(f"⚠️ **{name}**: Success rate degraded to {metrics['Success Rate %']:.1f}%\n")
            breaking_detected = True

    if not breaking_detected:
        logger.log_section("✓ **System maintains high success rate across all load levels!**\n")

    # Bottleneck analysis
    logger.log_section("\n### Bottleneck Analysis & Recommendations\n")

    max_throughput = max(m["Throughput (q/s)"] for _, m in load_results)
    logger.log_section(f"""
**Current Performance Ceiling:** {max_throughput:.1f} queries/second

**Optimization Opportunities:**
1. **Embedding Service**: Pre-compute and cache frequent embeddings (20-30% speedup expected)
2. **Database Connection Pool**: Implement pgbouncer or sqlalchemy pool (15-25% speedup)
3. **Vector Index**: Verify HNSW index is active on vektoren table (10-40% speedup for retrieval)
4. **Async Polling**: Replace REST polling with WebSockets (50%+ latency reduction)
5. **Multi-instance Calc**: Deploy calc_bruce and calc_docs_de in replicas (linear scaling)
6. **Query Caching**: Implement Redis for identical query deduplication (variable based on patterns)
7. **Partition Pruning**: Verify seiten partitioning is working (10-20% speedup for large datasets)
8. **Batch Processing**: Support batch queries endpoint for bulk operations (3-5x throughput)

""")

    logger.log_section(f"---\n*Benchmark completed at {datetime.now().isoformat()}*\n")

    # Save report
    logger.save("BENCHMARK.md")

    print("\n" + "="*70)
    print("✓ Stress benchmark complete!")
    print(f"✓ Results saved to: BENCHMARK.md")
    print("="*70)


if __name__ == "__main__":
    main()
