"""Per-page shadow adapters; they extract evidence but never interpret curriculum."""

from __future__ import annotations

import importlib.metadata
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from pypdf import PdfReader, PdfWriter

from .schema import page_record, stable_digest


ADAPTER_NAMES = ("docling", "native_ocr", "pypdf")


def installed_versions() -> dict[str, str | None]:
    versions: dict[str, str | None] = {}
    for package in ("pypdf", "docling"):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = None
    for executable in ("pdftoppm", "tesseract"):
        versions[executable] = "available" if shutil.which(executable) else None
    return versions


def _unknown_text_region(text: str, page_number: int, method: str) -> dict[str, Any]:
    return {
        "region_id": f"p{page_number:04d}-r0001",
        "class": "unknown",
        "bbox": {"status": "not_available", "reason": "adapter_does_not_emit_reliable_geometry"},
        "reading_order": 1,
        "state": "quarantined",
        "reason": "semantic_class_and_geometry_not_adjudicated",
        "text": text,
        "extraction_method": method,
        "evidence": {
            "source_path": "local-only",
            "page": page_number,
            "bbox_resolvable": False,
            "provenance_status": "not_evaluable",
        },
    }


def _native_page(source_path: Path, page_number: int) -> tuple[float, float, str]:
    reader = PdfReader(source_path)
    page = reader.pages[page_number - 1]
    return float(page.mediabox.width), float(page.mediabox.height), (page.extract_text() or "").strip()


def _pypdf(source_path: Path, page_number: int, _: dict[str, Any]) -> dict[str, Any]:
    started = time.perf_counter()
    width, height, text = _native_page(source_path, page_number)
    regions = [_unknown_text_region(text, page_number, "native")] if text else []
    return page_record(
        page_number,
        state="included" if text else "quarantined",
        reason="native_text_extracted" if text else "no_native_text",
        width=width,
        height=height,
        elapsed_seconds=round(time.perf_counter() - started, 6),
        method="native",
        regions=regions,
    )


def _native_ocr(source_path: Path, page_number: int, configuration: dict[str, Any]) -> dict[str, Any]:
    started = time.perf_counter()
    width, height, text = _native_page(source_path, page_number)
    if text:
        result = page_record(
            page_number, state="included", reason="native_text_extracted", width=width,
            height=height, elapsed_seconds=0, method="native",
            regions=[_unknown_text_region(text, page_number, "native")],
        )
    elif not (shutil.which("pdftoppm") and shutil.which("tesseract")):
        result = page_record(
            page_number, state="quarantined", reason="ocr_runtime_unavailable_missing_pdftoppm",
            width=width, height=height, elapsed_seconds=0, method="not_available",
        )
    else:
        with tempfile.TemporaryDirectory(prefix="aulalista-shadow-ocr-") as directory:
            prefix = Path(directory) / "page"
            rendered = subprocess.run(
                [
                    "pdftoppm", "-f", str(page_number), "-l", str(page_number),
                    "-r", str(configuration["ocr"]["dpi"]), "-png", str(source_path), str(prefix),
                ],
                capture_output=True, text=True, check=False, timeout=60,
            )
            image = next(Path(directory).glob("page-*.png"), None)
            if rendered.returncode or image is None:
                result = page_record(
                    page_number, state="quarantined", reason="ocr_render_failed", width=width,
                    height=height, elapsed_seconds=0, method="ocr",
                )
            else:
                ocr = subprocess.run(
                    ["tesseract", str(image), "stdout", "-l", configuration["ocr"]["language"]],
                    capture_output=True, text=True, check=False, timeout=60,
                )
                ocr_text = ocr.stdout.strip()
                regions = [_unknown_text_region(ocr_text, page_number, "ocr")] if ocr_text else []
                result = page_record(
                    page_number,
                    state="included" if ocr.returncode == 0 and ocr_text else "quarantined",
                    reason="ocr_text_extracted" if ocr.returncode == 0 and ocr_text else "ocr_failed_or_empty",
                    width=width, height=height, elapsed_seconds=0, method="ocr", regions=regions,
                )
    result["elapsed_seconds"] = round(time.perf_counter() - started, 6)
    return result


def _docling(source_path: Path, page_number: int, _: dict[str, Any]) -> dict[str, Any]:
    started = time.perf_counter()
    width, height, _text = _native_page(source_path, page_number)
    try:
        from docling.document_converter import DocumentConverter  # type: ignore[import-not-found]
    except ImportError:
        return page_record(
            page_number, state="quarantined", reason="docling_not_installed", width=width,
            height=height, elapsed_seconds=round(time.perf_counter() - started, 6), method="not_available",
        )
    with tempfile.TemporaryDirectory(prefix="aulalista-shadow-docling-") as directory:
        one_page = Path(directory) / "source-page.pdf"
        reader = PdfReader(source_path)
        writer = PdfWriter()
        writer.add_page(reader.pages[page_number - 1])
        with one_page.open("wb") as stream:
            writer.write(stream)
        exported = DocumentConverter().convert(one_page).document.export_to_dict()
    result = page_record(
        page_number,
        state="quarantined",
        reason="docling_output_mapping_not_adjudicated",
        width=width,
        height=height,
        elapsed_seconds=round(time.perf_counter() - started, 6),
        method="docling",
    )
    result["adapter_evidence"] = {
        "export_sha256": stable_digest(exported),
        "document_keys": sorted(exported),
    }
    return result


def extract_page(adapter: str, source_path: Path, page_number: int, configuration: dict[str, Any]) -> dict[str, Any]:
    if adapter == "pypdf":
        return _pypdf(source_path, page_number, configuration)
    if adapter == "native_ocr":
        return _native_ocr(source_path, page_number, configuration)
    if adapter == "docling":
        return _docling(source_path, page_number, configuration)
    raise ValueError(f"unknown adapter: {adapter}")
