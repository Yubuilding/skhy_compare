#!/usr/bin/env python3
"""Build a GitHub Pages artifact with fresh market-data snapshots."""

import argparse
import json
import math
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from app import JsonHttpClient, STATIC_DIR, fetch_market_history, fetch_market_snapshot


PROJECT_DIR = Path(__file__).resolve().parent


def _write_json(path, payload):
    path.write_text(
        json.dumps(payload, ensure_ascii=False, allow_nan=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _validate_snapshot(snapshot):
    """Refuse to publish when the premium calculator lacks critical inputs."""
    quotes = snapshot.get("quotes") or {}
    missing = []
    for field in ("adr", "koreanShare", "fx"):
        price = (quotes.get(field) or {}).get("price")
        if not isinstance(price, (int, float)) or not math.isfinite(price) or price <= 0:
            missing.append(field)

    comparison = snapshot.get("comparison")
    if not isinstance(comparison, dict):
        missing.append("comparison")
    else:
        for field in ("fair_adr_usd", "premium_percent"):
            value = comparison.get(field)
            if not isinstance(value, (int, float)) or not math.isfinite(value):
                missing.append(f"comparison.{field}")

    if missing:
        raise RuntimeError(
            "Refusing to publish without critical market data: " + ", ".join(missing)
        )


def build_pages(output_dir, client=None):
    """Copy the frontend and generate static snapshot/history JSON files."""
    output = Path(output_dir).resolve()
    if output in {Path("/"), Path.home().resolve(), PROJECT_DIR.resolve()}:
        raise ValueError("Refusing to replace an unsafe Pages output directory")

    market_client = client or JsonHttpClient()
    with ThreadPoolExecutor(max_workers=2) as executor:
        snapshot_future = executor.submit(fetch_market_snapshot, market_client)
        history_future = executor.submit(fetch_market_history, market_client)
        snapshot = snapshot_future.result()
        history = history_future.result()

    _validate_snapshot(snapshot)

    if output.exists():
        shutil.rmtree(output)
    shutil.copytree(STATIC_DIR, output)

    index_path = output / "index.html"
    index = index_path.read_text(encoding="utf-8")
    local_marker = 'name="data-mode" content="local"'
    if local_marker not in index:
        raise ValueError("Frontend data-mode marker is missing")
    index_path.write_text(
        index.replace(local_marker, 'name="data-mode" content="static"', 1),
        encoding="utf-8",
    )

    data_dir = output / "data"
    data_dir.mkdir()
    _write_json(data_dir / "snapshot.json", snapshot)
    _write_json(data_dir / "history.json", history)
    return output


def main(argv=None):
    parser = argparse.ArgumentParser(description="Build the GitHub Pages site")
    parser.add_argument("--output", default="dist", help="Output directory (default: dist)")
    args = parser.parse_args(argv)
    output = build_pages(PROJECT_DIR / args.output)
    print(f"GitHub Pages artifact built at {output}")


if __name__ == "__main__":
    main()
