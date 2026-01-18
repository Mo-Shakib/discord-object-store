"""Lightweight web UI server for Discord Object Store."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Dict, List

from aiohttp import web

from src.database import DEFAULT_DB_PATH, get_storage_stats, init_database, list_batches
from src.utils import DatabaseError

BASE_DIR = Path(__file__).resolve().parent
INDEX_PATH = BASE_DIR / "index.html"


def _format_stats(stats: Dict[str, int]) -> Dict[str, Any]:
    total_size = stats.get("total_size", 0)
    compressed_size = stats.get("compressed_size", 0)
    compression_ratio = None
    if total_size > 0:
        compression_ratio = round(compressed_size / total_size, 2)

    return {
        **stats,
        "compression_ratio": compression_ratio,
    }


def _load_batches() -> List[Dict[str, Any]]:
    return list_batches()


async def index(request: web.Request) -> web.Response:
    if not INDEX_PATH.exists():
        return web.Response(text="index.html not found", status=404)
    return web.FileResponse(INDEX_PATH)


async def api_stats(request: web.Request) -> web.Response:
    try:
        stats = get_storage_stats()
    except DatabaseError as exc:
        return web.json_response({"error": str(exc)}, status=500)
    return web.json_response(_format_stats(stats))


async def api_batches(request: web.Request) -> web.Response:
    try:
        batches = _load_batches()
    except DatabaseError as exc:
        return web.json_response({"error": str(exc)}, status=500)
    return web.json_response({"batches": batches})


def create_app() -> web.Application:
    init_database(DEFAULT_DB_PATH)
    app = web.Application()
    app.router.add_get("/", index)
    app.router.add_get("/api/stats", api_stats)
    app.router.add_get("/api/batches", api_batches)
    return app


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Discord Object Store Web UI")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind")
    parser.add_argument("--port", type=int, default=8080, help="Port to bind")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    app = create_app()
    web.run_app(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
