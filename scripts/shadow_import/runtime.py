"""Isolated worker and supervisor for one benchmark run."""

from __future__ import annotations

import json
import math
import os
import platform
import re
import signal
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from pypdf import PdfReader

from .adapters import extract_page, installed_versions
from .schema import SCHEMA_VERSION, atomic_json, file_digest, pending_page, sanitize_text, stable_digest, utc_now


TIME_RSS_PATTERN = re.compile(r"^\s*(\d+)\s+maximum resident set size\s*$", re.MULTILINE)


def _source_from_manifest(manifest_path: Path, source_id: str) -> tuple[dict[str, Any], Path]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    candidates = [item for item in manifest["documents"] if item.get("id") == source_id]
    if len(candidates) != 1:
        raise ValueError(f"source id must resolve exactly once: {source_id}")
    item = candidates[0]
    if item.get("runner_eligible") is not True:
        raise ValueError(f"source is not runner eligible: {source_id}")
    source_path = Path(str(item["path"])).expanduser()
    if not source_path.is_file():
        raise FileNotFoundError(f"local source is unavailable for {source_id}")
    observed_hash = file_digest(source_path)
    if observed_hash != item["sha256"]:
        raise ValueError(f"source hash mismatch for {source_id}")
    observed_pages = len(PdfReader(source_path).pages)
    if observed_pages != int(item["page_count"]):
        raise ValueError(f"source page count mismatch for {source_id}")
    declared_split = str(item["split"])

    # Partition isolation: check for duplicate sha256 across splits
    all_hashes_by_split = {}
    for doc in manifest["documents"]:
        doc_sha = doc.get("sha256", "")
        doc_split = doc.get("split", "")
        if doc_sha:
            all_hashes_by_split.setdefault(doc_sha, set()).add(doc_split)

    for sha, splits in all_hashes_by_split.items():
        if len(splits) > 1:
            raise ValueError(
                f"partition isolation violation: sha256 {sha[:16]}... appears in splits {sorted(splits)}"
            )

    # Family/template isolation: test families must not be shared with any other split
    all_families_by_split: dict[str, set[str]] = {}
    for doc in manifest.get("documents", []):
        doc_family = doc.get("family")
        doc_split = doc.get("split", "")
        if doc_family and doc_split:
            all_families_by_split.setdefault(doc_family, set()).add(doc_split)

    for fam, splits in all_families_by_split.items():
        if "test" in splits and len(splits) > 1:
            other_splits = sorted(splits - {"test"})
            raise ValueError(
                f"partition isolation violation: family '{fam}' shared between test and other splits {other_splits}"
            )
    split = "pre-observed_holdout" if declared_split == "test" else declared_split
    safe_source = {
        "id": source_id,
        "sha256": observed_hash,
        "page_count": observed_pages,
        "split": split,
        "manifest_split": declared_split,
        "path": "local-only",
    }
    return safe_source, source_path


def extraction_configuration(timeout_seconds: float, page_delay_seconds: float) -> dict[str, Any]:
    versions = installed_versions()
    comparable = {
        "timeout_seconds": timeout_seconds,
        "ocr": {"language": "spa", "dpi": 300, "routing": "native_then_empty_page_ocr"},
        "page_unit_processing": True,
        "page_delay_seconds": page_delay_seconds,
        "adapter_versions": versions,
        "cache_state": "unknown_not_controlled",
    }
    return {"sha256": stable_digest(comparable), **comparable}


def _run_id(
    source_id: str,
    source_sha256: str,
    adapter: str,
    adapter_version: str | None,
    configuration_sha256: str,
    warmup: bool,
    replica: int,
) -> str:
    role = "warmup" if warmup else f"replica-{replica}"
    version_sha256 = stable_digest(adapter_version)
    identity_sha256 = stable_digest({
        "source_sha256": source_sha256,
        "adapter": adapter,
        "adapter_version_sha256": version_sha256,
        "configuration_sha256": configuration_sha256,
    })
    return f"{source_id.lower()}-{adapter}-{role}-{identity_sha256[:16]}"


def _new_checkpoint(
    run_id: str, source: dict[str, Any], adapter: str, adapter_version: str | None,
    configuration_sha256: str,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "aulalista.shadow_import.checkpoint",
        "run_id": run_id,
        "source": {"id": source["id"], "sha256": source["sha256"], "path": "local-only"},
        "adapter": {"name": adapter, "version": adapter_version},
        "configuration_sha256": configuration_sha256,
        "expected_pages": source["page_count"],
        "completed_pages": [],
        "failed_pages": [],
        "page_results": {},
        "page_result_sha256": {},
        "updated_at": utc_now(),
    }


def worker(
    *, source_path: Path, source: dict[str, Any], adapter: str, configuration: dict[str, Any],
    run_id: str, checkpoint_path: Path, resume: bool,
) -> int:
    versions = configuration["adapter_versions"]
    adapter_version = versions.get("docling" if adapter == "docling" else "pypdf")
    if resume and checkpoint_path.is_file():
        checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        identity_matches = (
            checkpoint.get("source", {}).get("sha256") == source["sha256"]
            and checkpoint.get("adapter", {}).get("name") == adapter
            and checkpoint.get("adapter", {}).get("version") == adapter_version
            and checkpoint.get("configuration_sha256") == configuration["sha256"]
        )
        if not identity_matches:
            raise ValueError("stale checkpoint supplied to worker")
    else:
        checkpoint = _new_checkpoint(run_id, source, adapter, adapter_version, configuration["sha256"])
        atomic_json(checkpoint_path, checkpoint)

    completed = {int(number) for number in checkpoint["completed_pages"]}
    failures = 0
    for page_number in range(1, int(source["page_count"]) + 1):
        if page_number in completed:
            continue
        if configuration["page_delay_seconds"]:
            time.sleep(float(configuration["page_delay_seconds"]))
        try:
            page = extract_page(adapter, source_path, page_number, configuration)
        except Exception as error:  # receipt and retryability are more important than a traceback here
            failures += 1
            page = pending_page(page_number, "adapter_page_failed_retryable")
            page["error"] = sanitize_text(f"{type(error).__name__}: {error}")
            checkpoint["failed_pages"] = sorted(set(checkpoint["failed_pages"]) | {page_number})
        else:
            completed.add(page_number)
            checkpoint["completed_pages"] = sorted(completed)
            checkpoint["failed_pages"] = [number for number in checkpoint["failed_pages"] if number != page_number]
        checkpoint["page_results"][str(page_number)] = page
        checkpoint["page_result_sha256"][str(page_number)] = stable_digest(page)
        checkpoint["updated_at"] = utc_now()
        atomic_json(checkpoint_path, checkpoint)
    return 3 if failures or checkpoint["failed_pages"] else 0


def _sanitize_log(path: Path) -> None:
    if path.is_file():
        safe = sanitize_text(path.read_text(encoding="utf-8", errors="replace"))
        path.write_text(safe, encoding="utf-8")


def _peak_rss(stderr_text: str) -> tuple[int | str, str, str]:
    match = TIME_RSS_PATTERN.search(stderr_text)
    if not match:
        return "not_available", "not_available", "not_available"
    return int(match.group(1)), "bytes", "/usr/bin/time -l maximum resident set size"


def _stale_checkpoint_exists(
    raw_dir: Path,
    source: dict[str, Any],
    adapter: str,
    adapter_version: str | None,
    warmup: bool,
    replica: int,
    current_sha: str,
) -> bool:
    for candidate in (raw_dir / "runs").glob("*/checkpoint.json"):
        try:
            checkpoint = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        name = candidate.parent.name
        role = "warmup" if warmup else f"replica-{replica}"
        if (
            checkpoint.get("source", {}).get("id") == source["id"]
            and checkpoint.get("adapter", {}).get("name") == adapter
            and role in name
            and (
                checkpoint.get("source", {}).get("sha256") != source["sha256"]
                or checkpoint.get("adapter", {}).get("version") != adapter_version
                or checkpoint.get("configuration_sha256") != current_sha
            )
        ):
            return True
    return False


def run_one(
    *, manifest_path: Path, source_id: str, adapter: str, raw_dir: Path,
    timeout_seconds: float, page_delay_seconds: float, warmup: bool, replica: int,
    order_index: int = 0, order_seed: int = 20260902, resume: bool = False,
) -> tuple[int, Path]:
    if (raw_dir / "RAW-CLOSED.json").exists():
        raise RuntimeError("raw evidence is closed and immutable")
    source, source_path = _source_from_manifest(manifest_path, source_id)
    configuration = extraction_configuration(timeout_seconds, page_delay_seconds)
    adapter_package = "docling" if adapter == "docling" else "pypdf"
    adapter_version = configuration["adapter_versions"].get(adapter_package)
    run_id = _run_id(
        source_id, source["sha256"], adapter, adapter_version,
        configuration["sha256"], warmup, replica,
    )
    run_dir = raw_dir / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = run_dir / "checkpoint.json"
    stale = resume and not checkpoint_path.exists() and _stale_checkpoint_exists(
        raw_dir, source, adapter, adapter_version, warmup, replica, configuration["sha256"]
    )
    completed_before: list[int] = []
    if resume and checkpoint_path.exists():
        completed_before = json.loads(checkpoint_path.read_text(encoding="utf-8")).get("completed_pages", [])

    stdout_path = run_dir / "stdout.log"
    stderr_path = run_dir / "stderr.log"
    safe_worker_config = run_dir / "worker-configuration.json"
    atomic_json(safe_worker_config, {
        "schema_version": SCHEMA_VERSION,
        "kind": "aulalista.shadow_import.worker_configuration",
        "run_id": run_id,
        "source": source,
        "adapter": adapter,
        "configuration": configuration,
    })
    worker_command = [
        sys.executable, str(Path(__file__).resolve().parents[1] / "shadow_import_curriculum.py"),
        "worker", "--source-path", str(source_path), "--source-json", json.dumps(source),
        "--adapter", adapter, "--configuration-json", json.dumps(configuration),
        "--run-id", run_id, "--checkpoint", str(checkpoint_path),
    ]
    if resume:
        worker_command.append("--resume")
    # BSD time's -l flag is specific to macOS; GNU time on Linux rejects it.
    timed_command = (
        ["/usr/bin/time", "-l", *worker_command]
        if platform.system() == "Darwin" and Path("/usr/bin/time").is_file()
        else worker_command
    )
    started_monotonic = time.monotonic()
    started_at_dt = datetime.now(UTC)
    started_at = started_at_dt.isoformat()
    deadline_at = (started_at_dt + timedelta(seconds=timeout_seconds)).isoformat()
    termination_signal: str | None = None
    with stdout_path.open("w", encoding="utf-8") as stdout, stderr_path.open("w", encoding="utf-8") as stderr:
        child = subprocess.Popen(timed_command, stdout=stdout, stderr=stderr, start_new_session=True)
        try:
            return_code = child.wait(timeout=timeout_seconds)
            terminated_at = datetime.now(UTC).isoformat()
            time_to_censor = None
            termination_seconds = None
        except subprocess.TimeoutExpired:
            time_to_censor = round(time.monotonic() - started_monotonic, 6)
            os.killpg(child.pid, signal.SIGTERM)
            termination_signal = "SIGTERM"
            termination_started = time.monotonic()
            try:
                return_code = child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                termination_signal = "SIGKILL"
                return_code = child.wait()
            termination_seconds = round(time.monotonic() - termination_started, 6)
            terminated_at = datetime.now(UTC).isoformat()
    elapsed = round(time.monotonic() - started_monotonic, 6)
    _sanitize_log(stdout_path)
    _sanitize_log(stderr_path)
    stderr_text = stderr_path.read_text(encoding="utf-8", errors="replace")
    peak_rss, rss_unit, measurement_method = _peak_rss(stderr_text)

    if termination_signal:
        process_exit_status = "censored_timeout"
        extraction_outcome = "censored_timeout"
    elif return_code == 0:
        process_exit_status = "exited_zero"
        extraction_outcome = "complete"
    elif return_code < 0:
        process_exit_status = "signaled"
        extraction_outcome = "partial" if checkpoint_path.exists() else "failed"
    else:
        process_exit_status = "exited_nonzero"
        extraction_outcome = "partial" if checkpoint_path.exists() else "failed"

    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8")) if checkpoint_path.exists() else _new_checkpoint(
        run_id, source, adapter, configuration["adapter_versions"].get("docling" if adapter == "docling" else "pypdf"), configuration["sha256"]
    )
    completed_after = checkpoint.get("completed_pages", [])
    pages = [
        checkpoint.get("page_results", {}).get(str(number), pending_page(
            number, "not_processed_before_timeout" if termination_signal else "not_processed_after_worker_exit"
        ))
        for number in range(1, int(source["page_count"]) + 1)
    ]
    if extraction_outcome == "complete" and len(completed_after) != int(source["page_count"]):
        extraction_outcome = "partial"
    page_numbers = [page["page_number"] for page in pages]
    expected = list(range(1, int(source["page_count"]) + 1))
    events = []
    if stale:
        events.append({"level": "warning", "code": "stale_checkpoint", "detail": "source, adapter version, or configuration changed; new run started"})
    if source["split"] == "pre-observed_holdout":
        events.append({"level": "warning", "code": "pre_observed_holdout", "detail": "previous artifacts exposed this corpus; a new corpus is required for future blind validation"})
    if adapter == "native_ocr" and configuration["adapter_versions"]["pdftoppm"] is None:
        events.append({"level": "warning", "code": "ocr_not_evaluable", "detail": "pdftoppm unavailable; no dependency installed and OCR configuration unchanged"})
    resumable = extraction_outcome in {"partial", "censored_timeout", "failed"}
    resume_effective = bool(completed_before) and len(completed_after) > len(completed_before)
    environment = {
        "host": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "logical_cpu_count": os.cpu_count(),
            "node_sha256": stable_digest(platform.node()),
        },
        "python": platform.python_version(),
        "measurement_method": measurement_method,
        "peak_rss_unit": rss_unit,
    }
    result = {
        "schema_version": SCHEMA_VERSION,
        "kind": "aulalista.shadow_import.run",
        "run_id": run_id,
        "source": source,
        "adapter": {"name": adapter, "version": configuration["adapter_versions"].get(adapter_package)},
        "configuration": {
            "sha256": configuration["sha256"],
            "timeout_seconds": timeout_seconds,
            "warmup": warmup,
            "replica": replica,
            "order_seed": order_seed,
            "order_index": order_index,
            "cache_state": configuration["cache_state"],
            "ocr": configuration["ocr"],
            "page_unit_processing": True,
        },
        "environment": environment,
        "outcome": extraction_outcome,
        "extraction_completion": "all_units_processed" if len(completed_after) == len(expected) else "incomplete_units",
        "review_disposition": "not_evaluable",
        "process_exit_status": process_exit_status,
        "run": {
            "started_at": started_at,
            "deadline_at": deadline_at,
            "terminated_at": terminated_at,
            "elapsed_seconds": elapsed,
            "time_to_censor_seconds": time_to_censor,
            "termination_seconds": termination_seconds,
            "cpu_seconds": "not_available",
            "peak_rss": peak_rss,
            "peak_rss_unit": rss_unit,
            "measurement_method": measurement_method,
            "exit_code": return_code,
            "signal": termination_signal,
        },
        "checkpoint": {
            "available": checkpoint_path.exists(),
            "path": f"runs/{run_id}/checkpoint.json",
            "completed_pages": completed_after,
            "pending_pages": sorted(set(expected) - set(completed_after)),
            "resumable": resumable,
            "resumed": resume,
            "resume_effective": resume_effective,
            "stale_checkpoint": stale,
        },
        "partial_output_available": bool(completed_after),
        "resumable": resumable,
        "pages": pages,
        "events": events,
        "metrics": {
            "expected_pages": len(expected),
            "accounted_pages": len(set(page_numbers)),
            "silent_page_loss": sorted(set(expected) - set(page_numbers)),
            "accounting_failure": page_numbers != expected,
            "coverage": {state: sum(page["state"] == state for page in pages) for state in ("included", "reference_only", "quarantined", "excluded", "unknown")},
            "quality_status": "not_evaluable",
            "quality_reason": "no two independent schema-compatible annotations and no adjudicated gold set",
            "quality_metrics": {},
        },
        "artifacts": {
            "json_bytes": 0,
            "stdout": f"runs/{run_id}/stdout.log",
            "stderr": f"runs/{run_id}/stderr.log",
            "logs": [],
        },
    }
    result_path = run_dir / "result.json"
    atomic_json(result_path, result)
    for _ in range(3):
        result["artifacts"]["json_bytes"] = result_path.stat().st_size
        atomic_json(result_path, result)

    receipt = {
        "schema_version": SCHEMA_VERSION,
        "kind": "aulalista.shadow_import.receipt",
        "run_id": run_id,
        "source_id": source_id,
        "adapter": adapter,
        "configuration_sha256": configuration["sha256"],
        "started_at": started_at,
        "deadline_at": deadline_at,
        "terminated_at": terminated_at,
        "timeout_seconds": timeout_seconds,
        "elapsed_seconds": elapsed,
        "time_to_censor_seconds": time_to_censor,
        "termination_seconds": termination_seconds,
        "termination_signal": termination_signal,
        "exit_code": return_code,
        "process_exit_status": process_exit_status,
        "extraction_outcome": extraction_outcome,
        "extraction_completion": result["extraction_completion"],
        "review_disposition": "not_evaluable",
        "partial_output_available": bool(completed_after),
        "resumable": resumable,
        "resume_requested": resume,
        "resume_effective": resume_effective,
        "command": ["python", "scripts/shadow_import_curriculum.py", "worker", "--source-id", source_id, "--adapter", adapter, "--source-path", "local-only"],
        "result_sha256": file_digest(result_path),
    }
    receipt_path = run_dir / "receipt.json"
    atomic_json(receipt_path, receipt)
    attempts_dir = run_dir / "attempts"
    attempt_number = len(list(attempts_dir.glob("attempt-*.receipt.json"))) + 1
    atomic_json(attempts_dir / f"attempt-{attempt_number:03d}.receipt.json", receipt)
    atomic_json(attempts_dir / f"attempt-{attempt_number:03d}.result.json", result)
    return (124 if termination_signal else return_code), run_dir
