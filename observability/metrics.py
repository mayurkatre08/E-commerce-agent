"""
observability/metrics.py
In-process metrics store tracking:
  - Per-tool call latency (ms)
  - Tool success / failure counts
  - Escalation count vs total runs
  - p95 latency per tool
  - RAG retrieval groundedness proxy (chunk score avg)

All metrics are stored in-memory and can be dumped as a dict.
In production these would be pushed to Prometheus / CloudWatch.
"""

import time
import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class _ToolStats:
    latencies_ms: list = field(default_factory=list)
    success:      int  = 0
    failure:      int  = 0


class MetricsCollector:
    def __init__(self):
        self._tools:      dict[str, _ToolStats] = defaultdict(_ToolStats)
        self._runs:       int = 0          # total graph invocations
        self._escalated:  int = 0          # runs that ended in escalation
        self._rag_scores: list[float] = [] # chunk similarity scores (lower = more similar for L2)

    # ------------------------------------------------------------------
    # Context manager for timing a single tool call
    # ------------------------------------------------------------------

    class _Timer:
        def __init__(self, collector: "MetricsCollector", tool_name: str):
            self._collector  = collector
            self._tool_name  = tool_name
            self._start: float = 0.0
            self.success: bool = True   # caller sets this to False on error

        def __enter__(self):
            self._start = time.perf_counter()
            return self

        def __exit__(self, exc_type, *_):
            elapsed_ms = (time.perf_counter() - self._start) * 1000
            success    = exc_type is None and self.success
            self._collector._record(self._tool_name, elapsed_ms, success)

    def time_tool(self, tool_name: str) -> "_Timer":
        """Usage: with metrics.time_tool('policy_search') as t: ..."""
        return self._Timer(self, tool_name)

    # ------------------------------------------------------------------
    # Recording helpers
    # ------------------------------------------------------------------

    def _record(self, tool_name: str, latency_ms: float, success: bool):
        stats = self._tools[tool_name]
        stats.latencies_ms.append(latency_ms)
        if success:
            stats.success += 1
        else:
            stats.failure += 1

    def record_run(self, escalated: bool):
        """Call once per graph.ainvoke() completion."""
        self._runs += 1
        if escalated:
            self._escalated += 1

    def record_rag_scores(self, scores: list[float]):
        """Record chunk similarity scores from a policy_search call."""
        self._rag_scores.extend(scores)

    # ------------------------------------------------------------------
    # Computed metrics
    # ------------------------------------------------------------------

    def _p95(self, values: list[float]) -> Optional[float]:
        if not values:
            return None
        sorted_v = sorted(values)
        idx = max(0, int(len(sorted_v) * 0.95) - 1)
        return round(sorted_v[idx], 2)

    def tool_success_rate(self, tool_name: str) -> Optional[float]:
        s = self._tools.get(tool_name)
        if not s:
            return None
        total = s.success + s.failure
        return round(s.success / total, 4) if total else None

    def tool_p95_latency_ms(self, tool_name: str) -> Optional[float]:
        s = self._tools.get(tool_name)
        return self._p95(s.latencies_ms) if s else None

    def escalation_rate(self) -> Optional[float]:
        return round(self._escalated / self._runs, 4) if self._runs else None

    def avg_rag_groundedness(self) -> Optional[float]:
        """
        Proxy for retrieval groundedness: average chunk similarity score.
        Lower L2 distance = more grounded. Normalised to [0,1] where 1=best.
        """
        if not self._rag_scores:
            return None
        avg = statistics.mean(self._rag_scores)
        # Normalise: assume max meaningful L2 distance ~5000 for fake embeddings
        normalised = max(0.0, 1.0 - avg / 5000.0)
        return round(normalised, 4)

    # ------------------------------------------------------------------
    # Full report
    # ------------------------------------------------------------------

    def report(self) -> dict:
        tool_metrics = {}
        for name, stats in self._tools.items():
            total = stats.success + stats.failure
            tool_metrics[name] = {
                "calls":          total,
                "success":        stats.success,
                "failure":        stats.failure,
                "success_rate":   round(stats.success / total, 4) if total else None,
                "avg_latency_ms": round(statistics.mean(stats.latencies_ms), 2) if stats.latencies_ms else None,
                "p95_latency_ms": self._p95(stats.latencies_ms),
                "min_latency_ms": round(min(stats.latencies_ms), 2) if stats.latencies_ms else None,
                "max_latency_ms": round(max(stats.latencies_ms), 2) if stats.latencies_ms else None,
            }
        return {
            "total_runs":          self._runs,
            "escalated_runs":      self._escalated,
            "escalation_rate":     self.escalation_rate(),
            "avg_rag_groundedness": self.avg_rag_groundedness(),
            "tools":               tool_metrics,
        }

    def print_report(self):
        r = self.report()
        print("\n" + "=" * 55)
        print("  OBSERVABILITY REPORT")
        print("=" * 55)
        print(f"  Total runs       : {r['total_runs']}")
        print(f"  Escalated runs   : {r['escalated_runs']}")
        print(f"  Escalation rate  : {r['escalation_rate']}")
        print(f"  RAG groundedness : {r['avg_rag_groundedness']}")
        print("\n  Tool Metrics:")
        print(f"  {'Tool':<25} {'Calls':>5} {'SuccRate':>9} {'AvgMs':>8} {'p95Ms':>8}")
        print("  " + "-" * 53)
        for name, m in r["tools"].items():
            print(
                f"  {name:<25} {m['calls']:>5} "
                f"{str(m['success_rate']):>9} "
                f"{str(m['avg_latency_ms']):>8} "
                f"{str(m['p95_latency_ms']):>8}"
            )
        print("=" * 55 + "\n")


# Singleton — import and use anywhere
metrics = MetricsCollector()
