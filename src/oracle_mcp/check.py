from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from .config import ConfigError, load_config
from .db import (
    list_procedures,
    list_tables,
    list_views,
    profile_summary,
    test_connection,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check Oracle MCP configuration and DB connectivity."
    )
    parser.add_argument(
        "--config",
        help="Path to profiles.yaml. Defaults to ORACLE_MCP_CONFIG or profiles.yaml.",
    )
    parser.add_argument("--profile", help="Profile name to connect to.")
    parser.add_argument(
        "--metadata",
        action="store_true",
        help="Also check table, view, and procedure metadata access.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    try:
        config = load_config(args.config)
        if not args.profile:
            emit({"ok": True, "profiles": profile_summary(config)})
            return

        result: dict[str, Any] = test_connection(config, args.profile)
        if args.metadata:
            result["metadata_checks"] = {
                "tables": compact_check(list_tables(config, args.profile, limit=5)),
                "views": compact_check(list_views(config, args.profile, limit=5)),
                "procedures": compact_check(
                    list_procedures(config, args.profile, limit=5)
                ),
            }
        emit({"ok": True, **result})
    except (ConfigError, Exception) as exc:
        emit(
            {
                "ok": False,
                "error_type": exc.__class__.__name__,
                "message": str(exc),
            }
        )
        raise SystemExit(1) from exc


def compact_check(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "row_count": result.get("row_count"),
        "truncated": result.get("truncated"),
        "elapsed_ms": result.get("elapsed_ms"),
        "sample_rows": result.get("rows", [])[:3],
    }


def emit(value: dict[str, Any]) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
