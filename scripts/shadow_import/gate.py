"""Close and verify immutable raw benchmark evidence before interpretation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .schema import SCHEMA_VERSION, atomic_json, file_digest, utc_now


def _relative(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def close_raw(raw_dir: Path) -> dict[str, Any]:
    closure_path = raw_dir / "RAW-CLOSED.json"
    if closure_path.exists():
        raise RuntimeError("raw evidence is already closed")
    run_dirs = sorted(path for path in (raw_dir / "runs").glob("*") if path.is_dir())
    errors: list[str] = []
    findings: list[str] = []
    result_count = 0
    receipt_count = 0
    for run_dir in run_dirs:
        result_path = run_dir / "result.json"
        receipt_path = run_dir / "receipt.json"
        if not result_path.is_file():
            errors.append(f"missing result: {run_dir.name}")
            continue
        result_count += 1
        if not receipt_path.is_file():
            errors.append(f"missing receipt: {run_dir.name}")
            continue
        receipt_count += 1
        result = json.loads(result_path.read_text(encoding="utf-8"))
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        if result.get("schema_version") != SCHEMA_VERSION or receipt.get("schema_version") != SCHEMA_VERSION:
            errors.append(f"wrong schema: {run_dir.name}")
        if result.get("run_id") != receipt.get("run_id"):
            errors.append(f"run id mismatch: {run_dir.name}")
        if result.get("source", {}).get("path") != "local-only":
            errors.append(f"unsafe source path: {run_dir.name}")
        if result.get("outcome") != receipt.get("extraction_outcome"):
            errors.append(f"outcome mismatch: {run_dir.name}")
        if result.get("outcome") == "complete" and result.get("process_exit_status") != "exited_zero":
            errors.append(f"complete without zero process exit: {run_dir.name}")
        metrics = result.get("metrics", {})
        expected_order = list(range(1, int(metrics.get("expected_pages", 0)) + 1))
        observed_order = [page.get("page_number") for page in result.get("pages", [])]
        if (
            metrics.get("expected_pages") != metrics.get("accounted_pages")
            or metrics.get("silent_page_loss")
            or metrics.get("accounting_failure") is not False
            or observed_order != expected_order
        ):
            errors.append(f"page accounting failure: {run_dir.name}")
        pages = result.get("pages", [])
        if len(pages) != metrics.get("expected_pages"):
            errors.append(f"page ledger length mismatch: {run_dir.name}")
        if any(page.get("state") not in {"included", "reference_only", "quarantined", "excluded", "unknown"} for page in pages):
            errors.append(f"invalid page state: {run_dir.name}")
        if metrics.get("quality_status") != "not_evaluable" or metrics.get("quality_metrics") != {}:
            errors.append(f"quality gate violated: {run_dir.name}")
        if result.get("review_disposition") != "not_evaluable":
            errors.append(f"review disposition violated: {run_dir.name}")
        if file_digest(result_path) != receipt.get("result_sha256"):
            errors.append(f"result digest mismatch: {run_dir.name}")

    if result_count == 0:
        errors.append("no valid runs found: raw evidence is empty")

    if result_count != receipt_count:
        errors.append(f"receipt cardinality mismatch: {receipt_count}/{result_count}")
    for path in sorted(raw_dir.rglob("*")):
        if not path.is_file() or path == closure_path:
            continue
        if "/Users/" in path.read_text(encoding="utf-8", errors="replace"):
            findings.append(_relative(path, raw_dir))
    if findings:
        errors.append("absolute personal paths found")
    if errors:
        raise ValueError("raw gate failed: " + "; ".join(errors))

    input_paths = sorted(path for path in raw_dir.rglob("*") if path.is_file() and path != closure_path)
    inputs = [{"path": _relative(path, raw_dir), "sha256": file_digest(path), "bytes": path.stat().st_size} for path in input_paths]
    closure = {
        "schema_version": SCHEMA_VERSION,
        "kind": "aulalista.shadow_import.raw_closure",
        "closed_at": utc_now(),
        "gate_status": "passed",
        "result_count": result_count,
        "receipt_count": receipt_count,
        "expected_pages_accounted": True,
        "quality_status": "not_evaluable",
        "absolute_personal_path_findings": findings,
        "inputs": inputs,
    }
    atomic_json(closure_path, closure)
    return closure


def verify_closure(raw_dir: Path) -> dict[str, Any]:
    closure_path = raw_dir / "RAW-CLOSED.json"
    if not closure_path.is_file():
        raise ValueError("raw evidence is not closed")
    closure = json.loads(closure_path.read_text(encoding="utf-8"))
    if closure.get("gate_status") != "passed":
        raise ValueError("raw closure did not pass")
    expected = {item["path"]: item["sha256"] for item in closure["inputs"]}
    observed_paths = {
        path.relative_to(raw_dir).as_posix(): path
        for path in raw_dir.rglob("*")
        if path.is_file() and path != closure_path
    }
    if set(expected) != set(observed_paths):
        raise ValueError("raw file set changed after closure")
    changed = [relative for relative, digest in expected.items() if file_digest(observed_paths[relative]) != digest]
    if changed:
        raise ValueError("raw digests changed after closure: " + ", ".join(changed))
    return closure
