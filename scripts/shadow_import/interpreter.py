"""Interpret closed raw evidence without changing or filling it."""

from __future__ import annotations

import json
import math
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any

from .gate import verify_closure
from .schema import SCHEMA_VERSION, atomic_json, file_digest, stable_digest, utc_now


INTERPRETER_VERSION = "1.1.0"


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, math.ceil(fraction * len(ordered)) - 1)
    return ordered[index]


def _variation(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"n": 0, "range": None, "sd": None, "mad": None, "cv": None}
    median = statistics.median(values)
    mad = statistics.median(abs(value - median) for value in values)
    return {
        "n": len(values),
        "range": max(values) - min(values),
        "sd": statistics.stdev(values) if len(values) > 1 else None,
        "mad": mad,
        "cv": statistics.stdev(values) / statistics.mean(values) if len(values) > 1 and statistics.mean(values) != 0 else None,
    }


def interpret(raw_dir: Path, derived_dir: Path) -> dict[str, Any]:
    closure = verify_closure(raw_dir)
    results = [json.loads(path.read_text(encoding="utf-8")) for path in sorted((raw_dir / "runs").glob("*/result.json"))]
    measured = [result for result in results if not result["configuration"]["warmup"]]
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for result in measured:
        groups[(result["source"]["id"], result["adapter"]["name"])].append(result)
    combinations = []
    for (document, adapter), runs in sorted(groups.items()):
        uncensored = [run for run in runs if run["outcome"] == "complete"]
        elapsed = [float(run["run"]["elapsed_seconds"]) for run in uncensored]
        page_times = [
            float(page["elapsed_seconds"])
            for run in uncensored for page in run["pages"]
            if isinstance(page.get("elapsed_seconds"), (int, float))
        ]
        combinations.append({
            "document_id": document,
            "split": runs[0]["source"]["split"],
            "adapter": adapter,
            "measured_run_count": len(runs),
            "uncensored_run_count": len(uncensored),
            "censored_run_count": sum(run["outcome"] == "censored_timeout" for run in runs),
            "elapsed_seconds": {
                "observations": elapsed,
                "p50": _percentile(elapsed, 0.50),
                "p95_empirical": _percentile(elapsed, 0.95) if len(elapsed) == 3 else None,
                "p95_n": len(elapsed),
                "p95_warning": "descriptive empirical order statistic; n=3 is unstable and is not inferential" if len(elapsed) == 3 else "not reported unless n=3 uncensored replicas",
                "variation_uncensored_only": _variation(elapsed),
            },
            "page_seconds": {"observations": page_times, "n": len(page_times)},
            "coverage": {
                state: sum(run["metrics"]["coverage"].get(state, 0) for run in runs)
                for state in ("included", "reference_only", "quarantined", "excluded", "unknown")
            },
            "accounting_failures": sum(bool(run["metrics"]["accounting_failure"]) for run in runs),
            "peak_rss": [
                {"value": run["run"]["peak_rss"], "unit": run["run"]["peak_rss_unit"], "method": run["run"]["measurement_method"]}
                for run in runs
            ],
            "artifact_bytes": [run["artifacts"]["json_bytes"] for run in runs],
            "review_disposition": "not_evaluable",
        })
    input_digests = [{"path": item["path"], "sha256": item["sha256"]} for item in closure["inputs"]]
    matrix = {
        "schema_version": SCHEMA_VERSION,
        "kind": "aulalista.shadow_import.comparison_matrix",
        "interpreter": {"version": INTERPRETER_VERSION, "configuration_sha256": stable_digest({"censored_variation": "excluded", "quality": "not_evaluable"})},
        "quality_status": "not_evaluable",
        "quality_reason": "independent-a has 56/56 schema-incompatible records and explicitly is not adjudication; no compatible dual annotation or adjudicated gold set exists",
        "quality_metrics": {},
        "censoring_policy": "timeouts display as >= deadline and are excluded from ordinary SD, MAD, and CV",
        "holdout_status": "C03/C04 are pre-observed holdout, not a genuinely blind reserved test",
        "combinations": combinations,
        "runs": measured,
        "input_digests": input_digests,
    }
    derived_dir.mkdir(parents=True, exist_ok=True)
    matrix_path = derived_dir / "comparison-matrix.json"
    atomic_json(matrix_path, matrix)
    receipt = {
        "schema_version": SCHEMA_VERSION,
        "kind": "aulalista.shadow_import.interpreter_receipt",
        "interpreter_version": INTERPRETER_VERSION,
        "created_at": utc_now(),
        "configuration": matrix["interpreter"],
        "raw_closure_sha256": file_digest(raw_dir / "RAW-CLOSED.json"),
        "input_digests": input_digests,
        "outputs": [{"path": "comparison-matrix.json", "sha256": file_digest(matrix_path)}],
    }
    atomic_json(derived_dir / "interpreter-receipt.json", receipt)
    return matrix
