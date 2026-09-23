import json
import sys
import subprocess
from pathlib import Path
from pypdf import PdfWriter
import hashlib
import pytest

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "shadow_import_curriculum.py"

def write_pdf(path, pages=3, *, width=612):
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=width, height=792)
    with path.open("wb") as f:
        writer.write(f)
    return hashlib.sha256(path.read_bytes()).hexdigest()

def invoke(*arguments, timeout=15):
    return subprocess.run(
        [sys.executable, str(CLI), *arguments],
        cwd=ROOT, text=True, capture_output=True, timeout=timeout, check=False,
    )


class TestCloseRawEmptyFails:
    def test_close_raw_empty_directory_fails(self, tmp_path):
        """close_raw on empty raw dir must fail, not pass with result_count=0."""
        raw = tmp_path / "raw"
        raw.mkdir()
        (raw / "runs").mkdir()

        result = invoke("close-raw", "--raw-dir", str(raw))
        assert result.returncode != 0, (
            f"close-raw on empty dir should fail but returned 0. "
            f"stdout={result.stdout[:200]} stderr={result.stderr[:200]}"
        )
        assert not (raw / "RAW-CLOSED.json").exists()


class TestPartitionIsolation:
    def test_same_sha256_across_splits_rejected(self, tmp_path):
        """Same PDF hash appearing in both train and test splits must be rejected."""
        source = tmp_path / "fixture.pdf"
        digest = write_pdf(source, pages=1)

        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text(json.dumps({
            "schema_version": "1.0.0",
            "documents": [
                {
                    "id": "TRAIN-01",
                    "path": str(source),
                    "sha256": digest,
                    "page_count": 1,
                    "split": "train",
                    "runner_eligible": True,
                },
                {
                    "id": "TEST-01",
                    "path": str(source),
                    "sha256": digest,
                    "page_count": 1,
                    "split": "test",
                    "runner_eligible": True,
                },
            ],
        }), encoding="utf-8")

        raw = tmp_path / "raw"
        result = invoke(
            "run-one", "--manifest", str(manifest_path),
            "--source-id", "TRAIN-01", "--adapter", "pypdf",
            "--raw-dir", str(raw), "--timeout-seconds", "2",
            "--replica", "1",
        )
        # Should reject due to partition isolation violation
        assert result.returncode != 0, (
            f"Same sha256 in train+test should be rejected but returned 0. "
            f"stderr={result.stderr[:300]}"
        )

    def test_different_sha256_same_family_calibration_and_test_rejected(self, tmp_path):
        """Two PDFs with different SHA, same family, splits calibration and test -> resolution must fail explicitly for test."""
        from scripts.shadow_import.runtime import _source_from_manifest
        source_cal = tmp_path / "cal.pdf"
        source_test = tmp_path / "test.pdf"
        digest_cal = write_pdf(source_cal, pages=1, width=612)
        digest_test = write_pdf(source_test, pages=1, width=614)
        assert digest_cal != digest_test

        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text(json.dumps({
            "schema_version": "1.0.0",
            "documents": [
                {
                    "id": "CAL-01",
                    "path": str(source_cal),
                    "sha256": digest_cal,
                    "page_count": 1,
                    "split": "calibration",
                    "family": "shared_family_x",
                    "runner_eligible": True,
                },
                {
                    "id": "TEST-01",
                    "path": str(source_test),
                    "sha256": digest_test,
                    "page_count": 1,
                    "split": "test",
                    "family": "shared_family_x",
                    "runner_eligible": True,
                },
            ],
        }), encoding="utf-8")

        with pytest.raises(ValueError, match="partition isolation violation.*family"):
            _source_from_manifest(manifest_path, "TEST-01")

        # Also via CLI invoke
        raw = tmp_path / "raw"
        result = invoke(
            "run-one", "--manifest", str(manifest_path),
            "--source-id", "TEST-01", "--adapter", "pypdf",
            "--raw-dir", str(raw), "--timeout-seconds", "2",
            "--replica", "1",
        )
        assert result.returncode != 0, (
            f"Shared family between calibration and test should be rejected for TEST-01. "
            f"stdout={result.stdout[:200]} stderr={result.stderr[:200]}"
        )
        assert "partition isolation violation" in (result.stderr + result.stdout).lower()
