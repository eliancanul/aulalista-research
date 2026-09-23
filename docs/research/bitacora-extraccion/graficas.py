"""Regenera las figuras de la bitácora a partir de corridas congeladas.

Solo usa la biblioteca estándar. No abre PDFs ni ejecuta extractores.
"""

from __future__ import annotations

import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from xml.sax.saxutils import escape


ROOT = Path(__file__).resolve().parent
COLORS = {"confidence": "#2662a6", "structural-semantic": "#11967f", "disagreement": "#9b58a4"}


def history() -> dict:
    data = json.loads((ROOT / "historial.json").read_text(encoding="utf-8"))
    if data.get("schema_version") != 1:
        raise ValueError("Versión de historial no reconocida")
    for run in data["runs"]:
        for artifact in run["artifacts"]:
            path = (ROOT / artifact["path"]).resolve()
            if not path.is_relative_to(ROOT) or not path.is_file():
                raise ValueError(f"Artefacto ausente o fuera de la bitácora: {path}")
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if digest != artifact["sha256"]:
                raise ValueError(f"Hash distinto en {path.name}; registra una nueva corrida")
    return data


def rows(run: dict, suffix: str) -> list[dict]:
    artifact = next(a for a in run["artifacts"] if a["path"].endswith(suffix))
    with (ROOT / artifact["path"]).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def wrap(title: str, body: str, width: int, height: int) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'role="img" aria-label="{escape(title)}">'
        '<style>text{font-family:Arial,Helvetica,sans-serif;fill:#17324d}'
        '.title{font-size:22px;font-weight:700}.label{font-size:14px}'
        '.small{font-size:12px;fill:#52677a}.value{font-size:13px;font-weight:700}</style>'
        f'<rect width="100%" height="100%" rx="18" fill="#f6f9fc"/>{body}</svg>\n'
    )


def timeline_svg(data: dict) -> str:
    runs = sorted(data["runs"], key=lambda item: item["date"])
    width = max(860, 360 + 250 * len(runs))
    line_end = width - 170
    body = f'<text x="34" y="42" class="title">Recorrido de la investigación</text>'
    body += f'<line x1="170" y1="102" x2="{line_end}" y2="102" stroke="#9bb7cb" stroke-width="4"/>'
    for index, run in enumerate(runs):
        x = 170 + index * (line_end - 170) / max(1, len(runs) - 1)
        body += f'<circle cx="{x}" cy="102" r="12" fill="#167f91"/>'
        body += f'<text x="{x}" y="83" text-anchor="middle" class="value">{escape(run["date"])}</text>'
        body += f'<text x="{x}" y="133" text-anchor="middle" class="small">Fase {escape(run["phase"])}</text>'
        body += f'<text x="{x}" y="155" text-anchor="middle" class="label">{escape(run.get("short_title", run["title"]))}</text>'
    body += '<text x="34" y="202" class="small">Fase II: objetivo y protocolo en preparación; aún sin corrida semántica evaluable.</text>'
    return wrap("Recorrido de la investigación", body, width, 230)


def cascade_svg(run: dict, document: str | None = None) -> str:
    selected = rows(run, ".csv")
    if document:
        selected = [row for row in selected if row["document"] == document]
        if not selected:
            raise ValueError(f"Documento no encontrado: {document}")
    totals = defaultdict(lambda: {"accepted": 0, "ambiguous": 0, "abstentions": 0})
    for row in selected:
        key = row["cascade"]
        totals[key]["accepted"] += int(row["relations_accepted"])
        totals[key]["ambiguous"] += int(row["relations_ambiguous"])
        totals[key]["abstentions"] += int(row["abstention_records"])
    if not totals:
        raise ValueError("Corrida sin filas de cascada")
    maximum = max(1, *(value["accepted"] + value["ambiguous"] for value in totals.values()))
    label = document or "D01–D04"
    body = f'<text x="34" y="42" class="title">Relaciones: aceptación técnica y ambigüedad · {escape(label)}</text>'
    body += '<text x="34" y="66" class="small">Conteos mecánicos; aceptación técnica no equivale a verdad curricular.</text>'
    order = [name for name in COLORS if name in totals] + sorted(set(totals) - set(COLORS))
    for index, name in enumerate(order):
        y = 105 + index * 62
        values = totals[name]
        accepted_width = 410 * values["accepted"] / maximum
        ambiguous_width = 410 * values["ambiguous"] / maximum
        body += f'<text x="34" y="{y + 17}" class="label">{escape(name)}</text>'
        body += f'<rect x="225" y="{y}" width="410" height="24" rx="5" fill="#e4edf3"/>'
        body += f'<rect x="225" y="{y}" width="{accepted_width:.1f}" height="24" rx="5" fill="{COLORS.get(name, "#2662a6")}"/>'
        body += f'<rect x="{225 + accepted_width:.1f}" y="{y}" width="{ambiguous_width:.1f}" height="24" fill="#e7ac50"/>'
        body += f'<text x="650" y="{y + 17}" class="value">{values["accepted"]} / {values["ambiguous"]} / {values["abstentions"]}</text>'
    body += '<text x="34" y="313" class="small">Columnas numéricas: relaciones aceptadas / ambiguas / registros de abstención.</text>'
    return wrap("Estados mecánicos por cascada", body, 810, 335)


def adapters_svg(run: dict) -> str:
    raw = rows(run, "adaptadores-2026-09-02.csv")
    protected = rows(run, "docling-protegido-2026-09-02.csv")
    first = {(r["documento"], r["adapter"]): r for r in raw if r["run"] == "run-1"}
    protected_map = {r["documento"]: r for r in protected}
    body = '<text x="34" y="42" class="title">Cobertura observada de adaptadores</text>'
    body += '<text x="34" y="66" class="small">pypdf y OCR: matriz histórica run-1 · Docling: recibos protegidos. No son tiempos comparables.</text>'
    names = [("pypdf", 185), ("native_ocr", 365), ("docling protegido", 545)]
    for name, x in names:
        body += f'<text x="{x}" y="101" class="value">{escape(name)}</text>'
    for index, document in enumerate(("C01", "C02", "C03", "C04")):
        y = 122 + index * 52
        body += f'<text x="43" y="{y + 22}" class="value">{document}</text>'
        for name, x in names:
            if name == "docling protegido":
                item = protected_map[document]
                state = item["receipt_status"]
                label = "≥120.35 s · censurado" if state == "censored_timeout" else state
            else:
                item = first[(document, name)]
                state = item["outcome"]
                label = f'{item["coverage_included"]} incl. · {item["coverage_quarantined"]} cuar.'
            color = "#fff1d8" if state in {"partial", "censored_timeout"} else "#dbf2e9"
            body += f'<rect x="{x - 12}" y="{y}" width="168" height="35" rx="7" fill="{color}"/>'
            body += f'<text x="{x}" y="{y + 22}" class="small">{escape(label)}</text>'
    body += '<text x="34" y="354" class="small">Todos los estados de calidad son not_evaluable; incluido no implica fidelidad semántica.</text>'
    return wrap("Cobertura observada de adaptadores", body, 770, 376)


def render() -> list[Path]:
    data = history()
    out = ROOT / "figuras"
    out.mkdir(exist_ok=True)
    files = []
    charts = {"recorrido.svg": timeline_svg(data)}
    for run in data["runs"]:
        if run["kind"] == "adapters":
            charts["adaptadores-actual.svg"] = adapters_svg(run)
        elif run["kind"] == "cascade_matrix":
            charts["cascadas-actual.svg"] = cascade_svg(run)
        else:
            raise ValueError(f'Tipo de corrida desconocido: {run["kind"]}')
    for name, svg in charts.items():
        path = out / name
        path.write_text(svg, encoding="utf-8")
        files.append(path)
    return files


if __name__ == "__main__":
    for path in render():
        print(path.relative_to(ROOT))
