#!/usr/bin/env python3
"""Run and validate isolated, read-only curriculum PDF benchmark evidence."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from shadow_import.adapters import ADAPTER_NAMES
from shadow_import.gate import close_raw
from shadow_import.interpreter import interpret
from shadow_import.runtime import run_one, worker


def _add_run_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--adapter", choices=ADAPTER_NAMES, required=True)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=float, required=True)
    parser.add_argument("--page-delay-seconds", type=float, default=0)
    parser.add_argument("--warmup", action="store_true")
    parser.add_argument("--replica", type=int, default=1)
    parser.add_argument("--order-index", type=int, default=0)
    parser.add_argument("--order-seed", type=int, default=20260902)
    parser.add_argument("--resume", action="store_true")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    run_parser = commands.add_parser("run-one", help="supervise one isolated extraction run")
    _add_run_arguments(run_parser)

    worker_parser = commands.add_parser("worker", help=argparse.SUPPRESS)
    worker_parser.add_argument("--source-path", type=Path, required=True)
    worker_parser.add_argument("--source-json", required=True)
    worker_parser.add_argument("--adapter", choices=ADAPTER_NAMES, required=True)
    worker_parser.add_argument("--configuration-json", required=True)
    worker_parser.add_argument("--run-id", required=True)
    worker_parser.add_argument("--checkpoint", type=Path, required=True)
    worker_parser.add_argument("--resume", action="store_true")

    close_parser = commands.add_parser("close-raw", help="verify and hash raw evidence")
    close_parser.add_argument("--raw-dir", type=Path, required=True)

    interpret_parser = commands.add_parser("interpret", help="read closed raw evidence")
    interpret_parser.add_argument("--raw-dir", type=Path, required=True)
    interpret_parser.add_argument("--derived-dir", type=Path, required=True)
    return parser


def main() -> int:
    arguments = build_parser().parse_args()
    try:
        if arguments.command == "worker":
            return worker(
                source_path=arguments.source_path,
                source=json.loads(arguments.source_json),
                adapter=arguments.adapter,
                configuration=json.loads(arguments.configuration_json),
                run_id=arguments.run_id,
                checkpoint_path=arguments.checkpoint,
                resume=arguments.resume,
            )
        if arguments.command == "run-one":
            return_code, run_dir = run_one(
                manifest_path=arguments.manifest,
                source_id=arguments.source_id,
                adapter=arguments.adapter,
                raw_dir=arguments.raw_dir,
                timeout_seconds=arguments.timeout_seconds,
                page_delay_seconds=arguments.page_delay_seconds,
                warmup=arguments.warmup,
                replica=arguments.replica,
                order_index=arguments.order_index,
                order_seed=arguments.order_seed,
                resume=arguments.resume,
            )
            print(json.dumps({"run_id": run_dir.name, "return_code": return_code}, ensure_ascii=False))
            return return_code
        if arguments.command == "close-raw":
            closure = close_raw(arguments.raw_dir)
            print(json.dumps({
                "gate_status": closure["gate_status"],
                "result_count": closure["result_count"],
                "receipt_count": closure["receipt_count"],
            }))
            return 0
        if arguments.command == "interpret":
            matrix = interpret(arguments.raw_dir, arguments.derived_dir)
            print(json.dumps({"quality_status": matrix["quality_status"], "combinations": len(matrix["combinations"])}))
            return 0
    except Exception as error:
        print(f"{type(error).__name__}: {error}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
