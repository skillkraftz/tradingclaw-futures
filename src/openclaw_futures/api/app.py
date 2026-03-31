"""Minimal local HTTP API."""
from __future__ import annotations

import json
import re
import errno
import sys
from urllib import parse
from wsgiref.simple_server import make_server

from openclaw_futures.api import routes
from openclaw_futures.config import AppConfig
from openclaw_futures.providers.file_provider import FileMarketDataProvider
from openclaw_futures.services.scanner import ScannerService
from openclaw_futures.storage.db import connect


class TradingClawApp:
    def __init__(self, config: AppConfig | None = None):
        self.config = config or AppConfig.from_env()
        self.provider = FileMarketDataProvider(self.config.data_dir)
        self.connection = connect(self.config.db_path)
        self.scanner = ScannerService(self.config, self.connection)

    def __call__(self, environ, start_response):
        try:
            method = environ["REQUEST_METHOD"].upper()
            path = environ.get("PATH_INFO", "/")
            body = _read_body(environ)
            status_code, payload = self.dispatch(method, path, body)
        except json.JSONDecodeError as exc:
            status_code, payload = 400, {"error": f"invalid JSON body: {exc.msg}"}
        except ValueError as exc:
            status_code, payload = 400, {"error": str(exc)}
        except FileNotFoundError as exc:
            status_code, payload = 404, {"error": str(exc)}
        except Exception as exc:  # pragma: no cover
            status_code, payload = 500, {"error": str(exc)}

        response = json.dumps(payload).encode("utf-8")
        start_response(
            f"{status_code} {_reason(status_code)}",
            [("Content-Type", "application/json"), ("Content-Length", str(len(response)))],
        )
        return [response]

    def dispatch(self, method: str, path: str, body: dict[str, object]) -> tuple[int, dict[str, object]]:
        if method == "GET" and path == "/health":
            return 200, routes.health_handler(self, body)
        if method == "GET" and path == "/help":
            return 200, routes.help_handler(self, body)
        if method == "POST" and path == "/setups":
            return 200, routes.setups_handler(self, body)
        if method == "POST" and path == "/levels":
            return 200, routes.levels_handler(self, body)
        if method == "POST" and path == "/account":
            return 200, routes.account_handler(self, body)
        if method == "POST" and path == "/plan":
            return 200, routes.plan_handler(self, body)
        if method == "GET" and path == "/ideas":
            return 200, routes.ideas_handler(self, body)
        if method == "POST" and path == "/sync/run":
            return 200, routes.sync_run_handler(self, body)
        if method == "GET" and path == "/sync/status":
            return 200, routes.sync_status_handler(self, body)
        if method == "POST" and path == "/scan/run":
            return 200, routes.scan_run_handler(self, body)
        if method == "GET" and path == "/scan/status":
            return 200, routes.scan_status_handler(self, body)
        match = re.fullmatch(r"/ideas/(\d+)", path)
        if method == "GET" and match:
            return 200, routes.idea_handler(self, int(match.group(1)), body)
        if method == "GET" and path == "/stats":
            return 200, routes.stats_handler(self, body)
        if method == "POST" and path == "/reasoning-context":
            return 200, routes.reasoning_context_handler(self, body)

        match = re.fullmatch(r"/ideas/(\d+)/(take|skip|invalidate|result)", path)
        if method == "POST" and match:
            idea_id = int(match.group(1))
            action = match.group(2)
            if action == "take":
                return 200, routes.take_handler(self, idea_id, body)
            if action == "skip":
                return 200, routes.skip_handler(self, idea_id, body)
            if action == "invalidate":
                return 200, routes.invalidate_handler(self, idea_id, body)
            if action == "result":
                return 200, routes.result_handler(self, idea_id, body)

        return 404, {"error": f"unknown route {method} {path}"}


def create_app(config: AppConfig | None = None) -> TradingClawApp:
    return TradingClawApp(config=config)


def run_server(config: AppConfig | None = None) -> None:
    app = create_app(config)
    try:
        with make_server(app.config.host, app.config.port, app) as server:
            print(f"TradingClaw listening on http://{app.config.host}:{app.config.port}", flush=True)
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                print("TradingClaw stopped.", file=sys.stderr)
    except OSError as exc:
        if exc.errno == errno.EADDRINUSE:
            raise RuntimeError(
                f"port {app.config.port} is already in use on host {app.config.host}"
            ) from exc
        raise


def _read_body(environ) -> dict[str, object]:
    if environ["REQUEST_METHOD"].upper() == "GET":
        return _read_query_string(environ)
    content_length = int(environ.get("CONTENT_LENGTH") or 0)
    if content_length <= 0:
        return {}
    raw = environ["wsgi.input"].read(content_length)
    if not raw:
        return _read_query_string(environ)
    payload = json.loads(raw.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("JSON body must be an object")
    if environ.get("QUERY_STRING"):
        query = _read_query_string(environ)
        query.update(payload)
        return query
    return payload


def _read_query_string(environ) -> dict[str, object]:
    raw_query = environ.get("QUERY_STRING", "")
    if not raw_query:
        return {}
    parsed = parse.parse_qs(raw_query, keep_blank_values=True)
    query: dict[str, object] = {}
    for key, values in parsed.items():
        query[key] = values if len(values) > 1 else values[0]
    return query


def _reason(status_code: int) -> str:
    return {
        200: "OK",
        400: "Bad Request",
        404: "Not Found",
        500: "Internal Server Error",
    }[status_code]
