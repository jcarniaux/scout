"""
CloudWatch Embedded Metric Format (EMF) helper.

Emits structured log lines that CloudWatch automatically parses into custom
metrics — no put_metric_data API calls, no extra latency, no extra cost.

Usage:
    from shared.metrics import emit_metric

    emit_metric("Scout/Enrichment", "JobsStored", 42, source="linkedin")
    emit_metric("Scout/Crawlers", "Errors", 1, source="indeed")
"""
import json
import logging
import os
import sys

logger = logging.getLogger()


def emit_metric(
    namespace: str,
    metric_name: str,
    value: float,
    unit: str = "Count",
    **dimensions: str,
) -> None:
    """
    Emit a single CloudWatch metric via Embedded Metric Format.

    Args:
        namespace:   CloudWatch namespace (e.g. "Scout/Enrichment")
        metric_name: Metric name (e.g. "JobsStored")
        value:       Numeric value
        unit:        CloudWatch unit (Count, Milliseconds, etc.)
        **dimensions: Key=value dimension pairs (e.g. source="linkedin")
    """
    dim_keys = list(dimensions.keys())

    emf = {
        "_aws": {
            "Timestamp": _now_millis(),
            "CloudWatchMetrics": [
                {
                    "Namespace": namespace,
                    "Dimensions": [dim_keys] if dim_keys else [[]],
                    "Metrics": [
                        {"Name": metric_name, "Unit": unit},
                    ],
                }
            ],
        },
        metric_name: value,
    }

    # Add dimensions as top-level keys (EMF requirement)
    for k, v in dimensions.items():
        emf[k] = v

    # EMF lines must go to stdout, not through the logging framework
    print(json.dumps(emf), flush=True)


def _now_millis() -> int:
    """Current UTC epoch in milliseconds."""
    import time
    return int(time.time() * 1000)
