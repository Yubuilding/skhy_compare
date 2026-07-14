#!/usr/bin/env python3
"""Build a GitHub Pages artifact with fresh market-data snapshots."""

import argparse
import json
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


def build_pages(output_dir, client=None):
    """Copy the frontend and generate static snapshot/history JSON files."""
    output = Path(output_dir).resolve()
    if output in {Path("/"), Path.home().resolve(), PROJECT_DIR.resolve()}:
        raise ValueError("Refusing to replace an unsafe Pages output directory")
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

    market_client = client or JsonHttpClient()
    with ThreadPoolExecutor(max_workers=2) as executor:
        snapshot_future = executor.submit(fetch_market_snapshot, market_client)
        history_future = executor.submit(fetch_market_history, market_client)
        snapshot = snapshot_future.result()
        history = history_future.result()

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
