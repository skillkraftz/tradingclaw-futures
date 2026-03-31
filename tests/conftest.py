from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from openclaw_futures.api.app import TradingClawApp
from openclaw_futures.config import AppConfig
from openclaw_futures.providers.file_provider import FileMarketDataProvider
from openclaw_futures.storage.db import connect


@pytest.fixture()
def fixture_dir() -> Path:
    return Path(__file__).parent / "fixtures"


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "tradingclaw.sqlite3"


@pytest.fixture()
def config(fixture_dir: Path, db_path: Path) -> AppConfig:
    return AppConfig(
        host="127.0.0.1",
        port=8787,
        data_dir=fixture_dir,
        default_provider="file",
        db_path=db_path,
        webhook_url="",
        webhook_thread_id="",
        room_label="test-room",
        log_level="INFO",
    )


@pytest.fixture()
def provider(fixture_dir: Path) -> FileMarketDataProvider:
    return FileMarketDataProvider(fixture_dir)


@pytest.fixture()
def connection(db_path: Path):
    connection = connect(db_path)
    yield connection
    connection.close()


@pytest.fixture()
def app(config: AppConfig) -> TradingClawApp:
    return TradingClawApp(config)


def call_app(
    app: TradingClawApp,
    method: str,
    path: str,
    payload: dict[str, object] | None = None,
    query_string: str = "",
) -> tuple[int, dict[str, object]]:
    raw = json.dumps(payload or {}).encode("utf-8")
    status_headers: dict[str, object] = {}

    def start_response(status: str, headers):
        status_headers["status"] = status
        status_headers["headers"] = headers

    environ = {
        "REQUEST_METHOD": method,
        "PATH_INFO": path,
        "QUERY_STRING": query_string,
        "CONTENT_LENGTH": str(len(raw) if method != "GET" else 0),
        "wsgi.input": io.BytesIO(raw),
    }
    body = b"".join(app(environ, start_response))
    return int(str(status_headers["status"]).split()[0]), json.loads(body.decode("utf-8"))
