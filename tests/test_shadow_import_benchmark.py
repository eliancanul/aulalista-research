from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from pypdf import PdfWriter


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "shadow_import_curriculum.py"


def write_pdf(path: Path, pages: int = 3, *, width: int = 612) -> str:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=width, height=792)
    with path.open("wb") as stream:
        writer.write(stream)
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_manifest(path: Path, source: Path, digest: str, pages: int = 3) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "documents": [
                    {
                        "id": "T01",
                        "path": str(source),
                        "sha256": digest,
                        "page_count": pages,
                        "split": "calibration",
                        "runner_eligible": True,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def invoke(*arguments: str, timeout: float = 15) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CLI), *arguments],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )


def only_run_dir(raw: Path) -> Path:
    run_dirs = [path for path in (raw / "runs").iterdir() if path.is_dir()]
    assert len(run_dirs) == 1
    return run_dirs[0]


def test_timeout_receipt_and_resume_are_accounted_and_leakage_safe(tmp_path: Path) -> None:
    source = tmp_path / "private-fixture.pdf"
    manifest = tmp_path / "manifest.json"
    digest = write_pdf(source, pages=2)
    write_manifest(manifest, source, digest, pages=2)
    raw = tmp_path / "raw"

    interrupted = invoke(
        "run-one",
        "--manifest",
        str(manifest),
        "--source-id",
        "T01",
        "--adapter",
        "pypdf",
        "--raw-dir",
        str(raw),
        "--timeout-seconds",
        "0.65",
        "--page-delay-seconds",
        "0.4",
        "--replica",
        "1",
    )
    assert interrupted.returncode == 124, interrupted.stderr

    run_dir = only_run_dir(raw)
    receipt = json.loads((run_dir / "receipt.json").read_text(encoding="utf-8"))
    result = json.loads((run_dir / "result.json").read_text(encoding="utf-8"))
    checkpoint = json.loads((run_dir / "checkpoint.json").read_text(encoding="utf-8"))

    assert receipt["schema_version"] == "1.1.0"
    assert receipt["process_exit_status"] == "censored_timeout"
    assert receipt["extraction_outcome"] == "censored_timeout"
    assert receipt["partial_output_available"] is True
    assert receipt["resumable"] is True
    assert receipt["terminated_at"]
    assert receipt["termination_signal"] in {"SIGTERM", "SIGKILL"}
    assert result["source"]["path"] == "local-only"
    assert result["outcome"] == "censored_timeout"
    assert result["metrics"]["expected_pages"] == 2
    assert result["metrics"]["accounted_pages"] == 2
    assert result["metrics"]["silent_page_loss"] == []
    assert result["metrics"]["quality_status"] == "not_evaluable"
    assert len(checkpoint["completed_pages"]) == 1
    assert "/Users/" not in "\n".join(
        path.read_text(encoding="utf-8", errors="replace") for path in run_dir.iterdir() if path.is_file()
    )

    resumed = invoke(
        "run-one",
        "--manifest",
        str(manifest),
        "--source-id",
        "T01",
        "--adapter",
        "pypdf",
        "--raw-dir",
        str(raw),
        "--timeout-seconds",
        "0.65",
        "--page-delay-seconds",
        "0.4",
        "--replica",
        "1",
        "--resume",
    )
    assert resumed.returncode == 0, resumed.stderr
    resumed_result = json.loads((run_dir / "result.json").read_text(encoding="utf-8"))
    resumed_receipt = json.loads((run_dir / "receipt.json").read_text(encoding="utf-8"))
    assert resumed_receipt["process_exit_status"] == "exited_zero"
    assert resumed_receipt["extraction_outcome"] == "complete"
    assert resumed_result["outcome"] == "complete"
    assert resumed_result["checkpoint"]["resumed"] is True
    assert resumed_result["checkpoint"]["completed_pages"] == [1, 2]
    assert resumed_result["metrics"]["accounted_pages"] == 2


def test_changed_configuration_marks_old_checkpoint_stale(tmp_path: Path) -> None:
    source = tmp_path / "fixture.pdf"
    manifest = tmp_path / "manifest.json"
    write_manifest(manifest, source, write_pdf(source, pages=1), pages=1)
    raw = tmp_path / "raw"

    first = invoke(
        "run-one", "--manifest", str(manifest), "--source-id", "T01",
        "--adapter", "pypdf", "--raw-dir", str(raw), "--timeout-seconds", "2",
        "--page-delay-seconds", "0", "--replica", "1",
    )
    assert first.returncode == 0, first.stderr
    first_dir = only_run_dir(raw)
    first_run_id = first_dir.name

    changed = invoke(
        "run-one", "--manifest", str(manifest), "--source-id", "T01",
        "--adapter", "pypdf", "--raw-dir", str(raw), "--timeout-seconds", "3",
        "--page-delay-seconds", "0", "--replica", "1", "--resume",
    )
    assert changed.returncode == 0, changed.stderr
    run_dirs = sorted(path for path in (raw / "runs").iterdir() if path.is_dir())
    assert len(run_dirs) == 2
    assert any(path.name != first_run_id for path in run_dirs)
    newest = max(run_dirs, key=lambda path: path.stat().st_mtime_ns)
    payload = json.loads((newest / "result.json").read_text(encoding="utf-8"))
    assert any(event["code"] == "stale_checkpoint" for event in payload["events"])


def test_changed_source_hash_creates_new_run_and_marks_checkpoint_stale(tmp_path: Path) -> None:
    source = tmp_path / "fixture.pdf"
    manifest = tmp_path / "manifest.json"
    write_manifest(manifest, source, write_pdf(source, pages=1), pages=1)
    raw = tmp_path / "raw"
    first = invoke(
        "run-one", "--manifest", str(manifest), "--source-id", "T01",
        "--adapter", "pypdf", "--raw-dir", str(raw), "--timeout-seconds", "2",
        "--replica", "1",
    )
    assert first.returncode == 0, first.stderr
    first_run_id = only_run_dir(raw).name

    changed_digest = write_pdf(source, pages=1, width=613)
    write_manifest(manifest, source, changed_digest, pages=1)
    changed = invoke(
        "run-one", "--manifest", str(manifest), "--source-id", "T01",
        "--adapter", "pypdf", "--raw-dir", str(raw), "--timeout-seconds", "2",
        "--replica", "1", "--resume",
    )
    assert changed.returncode == 0, changed.stderr
    run_dirs = sorted(path for path in (raw / "runs").iterdir() if path.is_dir())
    assert len(run_dirs) == 2
    newest = max(run_dirs, key=lambda path: path.stat().st_mtime_ns)
    assert newest.name != first_run_id
    payload = json.loads((newest / "result.json").read_text(encoding="utf-8"))
    assert payload["source"]["sha256"] == changed_digest
    assert any(event["code"] == "stale_checkpoint" for event in payload["events"])


def test_raw_gate_closes_only_complete_leakage_safe_receipt_pairs(tmp_path: Path) -> None:
    source = tmp_path / "fixture.pdf"
    manifest = tmp_path / "manifest.json"
    write_manifest(manifest, source, write_pdf(source, pages=1), pages=1)
    raw = tmp_path / "raw"
    run = invoke(
        "run-one", "--manifest", str(manifest), "--source-id", "T01",
        "--adapter", "pypdf", "--raw-dir", str(raw), "--timeout-seconds", "2",
        "--replica", "1",
    )
    assert run.returncode == 0, run.stderr

    closed = invoke("close-raw", "--raw-dir", str(raw))
    assert closed.returncode == 0, closed.stderr
    closure = json.loads((raw / "RAW-CLOSED.json").read_text(encoding="utf-8"))
    assert closure["schema_version"] == "1.1.0"
    assert closure["gate_status"] == "passed"
    assert closure["result_count"] == closure["receipt_count"] == 1
    assert closure["absolute_personal_path_findings"] == []


def test_raw_gate_rejects_invalid_page_order_and_accounting_flag(tmp_path: Path) -> None:
    import hashlib

    source = tmp_path / "fixture.pdf"
    manifest = tmp_path / "manifest.json"
    write_manifest(manifest, source, write_pdf(source, pages=2), pages=2)
    raw = tmp_path / "raw"
    run = invoke(
        "run-one", "--manifest", str(manifest), "--source-id", "T01",
        "--adapter", "pypdf", "--raw-dir", str(raw), "--timeout-seconds", "2",
        "--replica", "1",
    )
    assert run.returncode == 0, run.stderr
    run_dir = only_run_dir(raw)
    result_path = run_dir / "result.json"
    receipt_path = run_dir / "receipt.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    result["pages"].reverse()
    result["metrics"]["accounting_failure"] = True
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["result_sha256"] = hashlib.sha256(result_path.read_bytes()).hexdigest()
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    closed = invoke("close-raw", "--raw-dir", str(raw))
    assert closed.returncode != 0
    assert "page accounting failure" in closed.stderr
    assert not (raw / "RAW-CLOSED.json").exists()


def test_interpreter_refuses_unclosed_raw_and_keeps_quality_not_evaluable(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    derived = tmp_path / "derived"
    raw.mkdir()
    refused = invoke("interpret", "--raw-dir", str(raw), "--derived-dir", str(derived))
    assert refused.returncode != 0

    source = tmp_path / "fixture.pdf"
    manifest = tmp_path / "manifest.json"
    write_manifest(manifest, source, write_pdf(source, pages=1), pages=1)
    assert invoke(
        "run-one", "--manifest", str(manifest), "--source-id", "T01",
        "--adapter", "pypdf", "--raw-dir", str(raw), "--timeout-seconds", "2",
        "--replica", "1",
    ).returncode == 0
    assert invoke("close-raw", "--raw-dir", str(raw)).returncode == 0
    interpreted = invoke("interpret", "--raw-dir", str(raw), "--derived-dir", str(derived))
    assert interpreted.returncode == 0, interpreted.stderr
    matrix = json.loads((derived / "comparison-matrix.json").read_text(encoding="utf-8"))
    assert matrix["quality_status"] == "not_evaluable"
    assert matrix["quality_metrics"] == {}
    assert matrix["input_digests"]
