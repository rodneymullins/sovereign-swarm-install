#!/usr/bin/env python3
"""Pipeline metrics reporter. Shows key stats from pipeline operation."""
import json
import os
import sys

METRICS_FILE = os.path.expanduser("~/.hermes/state/pipeline_metrics.json")
LOG_FILE = os.path.expanduser("~/.hermes/logs/pipeline.log")


def show_metrics():
    """Display pipeline metrics in a readable format."""
    try:
        with open(METRICS_FILE) as f:
            m = json.load(f)
    except FileNotFoundError:
        print("No metrics data yet. Run some queries first.")
        return
    except json.JSONDecodeError:
        print("Metrics file corrupted. Reset with: rm ~/.hermes/state/pipeline_metrics.json")
        return

    total = m.get("total_queries", 0)
    if total == 0:
        print("No queries processed yet.")
        return

    print("=" * 50)
    print("  Pipeline Metrics Report")
    print("=" * 50)
    print(f"  Total queries:     {total}")
    print()

    # ── Domain Distribution ──
    print("  ── By Domain ──")
    by_domain = m.get("by_domain", {})
    for domain, count in sorted(by_domain.items(), key=lambda x: -x[1]):
        pct = count / total * 100
        bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
        print(f"    {domain:15s} {count:5d} ({pct:5.1f}%) {bar}")
    print()

    # ── Mode Distribution ──
    print("  ── By Mode ──")
    by_mode = m.get("by_mode", {})
    for mode, count in sorted(by_mode.items(), key=lambda x: -x[1]):
        pct = count / total * 100
        print(f"    {mode:15s} {count:5d} ({pct:5.1f}%)")
    print()

    # ── Distill Stats ──
    distill_success = m.get("distill_success", 0)
    distill_failure = m.get("distill_failure", 0)
    distill_total = distill_success + distill_failure
    if distill_total > 0:
        rate = distill_success / distill_total * 100
        print(f"  ── Distill ──")
        print(f"    Success rate:    {distill_success}/{distill_total} ({rate:.1f}%)")
        print(f"    Fallback used:   {m.get('distill_fallback_used', 0)} times")
        print()

    # ── Evaluator Stats ──
    eval_answered = m.get("evaluator_answered", 0)
    eval_passed = m.get("evaluator_passed", 0)
    eval_total = eval_answered + eval_passed
    if eval_total > 0:
        hit_rate = eval_answered / eval_total * 100
        savings = eval_answered * 0.02
        print(f"  ── Evaluator Gate ──")
        print(f"    Hit rate:        {eval_answered}/{eval_total} ({hit_rate:.1f}%)")
        print(f"    Est. savings:    ${savings:.2f}")
        print(f"    Fallback used:   {m.get('evaluator_fallback_used', 0)} times")
        print()

    # ── Latency ──
    latencies = m.get("latency_ms", [])
    if latencies:
        avg = sum(latencies) / len(latencies)
        p50 = sorted(latencies)[len(latencies) // 2]
        p95 = sorted(latencies)[int(len(latencies) * 0.95)]
        print(f"  ── Latency ──")
        print(f"    Average:         {avg:.0f} ms")
        print(f"    Median (P50):    {p50:.0f} ms")
        print(f"    P95:             {p95:.0f} ms")
        print(f"    Last 5:          {', '.join(f'{x:.0f}' for x in latencies[-5:])} ms")
        print()

    # ── Health & Circuit ──
    print(f"  ── Health ──")
    print(f"    Circuit opens:   {m.get('circuit_open_count', 0)}")
    print(f"    Health failures: {m.get('health_check_failures', 0)}")
    print(f"    Cache hits:      {m.get('cache_hits', 0)}")
    print(f"    Input rejects:   {m.get('input_validation_failures', 0)}")
    print()

    # ── Log tail ──
    print("  ── Last 5 Log Entries ──")
    try:
        with open(LOG_FILE) as f:
            lines = f.readlines()
        for line in lines[-5:]:
            print(f"    {line.strip()}")
    except FileNotFoundError:
        print("    (no log file yet)")
    print("=" * 50)


def show_live(interval=5, count=10):
    """Watch pipeline metrics live, updating every N seconds."""
    import time
    try:
        for i in range(count):
            os.system('clear')
            show_metrics()
            if i < count - 1:
                time.sleep(interval)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--live":
        interval = int(sys.argv[2]) if len(sys.argv) > 2 else 5
        count = int(sys.argv[3]) if len(sys.argv) > 3 else 10
        show_live(interval, count)
    elif len(sys.argv) > 1 and sys.argv[1] == "--reset":
        os.remove(METRICS_FILE)
        print("Metrics reset.")
    else:
        show_metrics()
