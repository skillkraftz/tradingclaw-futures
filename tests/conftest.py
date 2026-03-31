from __future__ import annotations

from pathlib import Path

import pytest

from openclaw_futures.providers.file_provider import FileMarketDataProvider
from openclaw_futures.services import OpenClawService


@pytest.fixture()
def fixture_dir() -> Path:
    return Path(__file__).parent / "fixtures"


@pytest.fixture()
def provider(fixture_dir: Path) -> FileMarketDataProvider:
    return FileMarketDataProvider(fixture_dir)


@pytest.fixture()
def service(provider: FileMarketDataProvider) -> OpenClawService:
    return OpenClawService(provider)
