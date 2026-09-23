"""Schema helpers for leakage-safe, product-independent benchmark evidence."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "1.1.0"
PERSONAL_PATH = re.compile(r"/Users/[^/\s\"']+(?:/[^\s\"']*)?")
PAGE_STATES = ("included", "reference_only", "quarantined", "excluded", "unknown")


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def stable_digest(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, path)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


def sanitize_text(value: str) -> str:
    return PERSONAL_PATH.sub("<LOCAL_PATH>", value)


def page_record(
    page_number: int,
    *,
    state: str,
    reason: str,
    width: float | None,
    height: float | None,
    elapsed_seconds: float | str,
    method: str,
    regions: list[dict[str, Any]] | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    if state not in PAGE_STATES:
        raise ValueError(f"unsupported page state: {state}")
    return {
        "page_number": page_number,
        "state": state,
        "reason": reason,
        "dimensions": {
            "width_points": width if width is not None else "not_available",
            "height_points": height if height is not None else "not_available",
        },
        "elapsed_seconds": elapsed_seconds,
        "extraction_method": method,
        "regions": regions or [],
        "checkpoint_bytes": "recorded_in_checkpoint_file",
        "error": error,
    }


def pending_page(page_number: int, reason: str) -> dict[str, Any]:
    return page_record(
        page_number,
        state="unknown",
        reason=reason,
        width=None,
        height=None,
        elapsed_seconds="not_available",
        method="not_available",
    )
