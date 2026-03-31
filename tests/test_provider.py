from __future__ import annotations

import pytest

from openclaw_futures.providers.file_provider import FileMarketDataProvider


def test_provider_loads_json_snapshot(fixture_dir) -> None:
    provider = FileMarketDataProvider(fixture_dir)
    snapshot = provider.get_snapshot("MCL")
    assert snapshot.symbol == "MCL"
    assert snapshot.overnight_high is not None


def test_provider_loads_csv_snapshot(tmp_path, fixture_dir) -> None:
    csv_path = tmp_path / "mcl_bars.csv"
    csv_path.write_text((fixture_dir / "mcl_bars.csv").read_text(encoding="utf-8"), encoding="utf-8")
    provider = FileMarketDataProvider(tmp_path)
    snapshot = provider.get_snapshot("MCL")
    assert snapshot.symbol == "MCL"
    assert snapshot.atr is not None


def test_malformed_fixture_raises_value_error(tmp_path) -> None:
    bad_snapshot = tmp_path / "mcl_snapshot.json"
    bad_snapshot.write_text('{"symbol":"MCL","bars":[{"ts":"x","open":"oops"}]}', encoding="utf-8")
    provider = FileMarketDataProvider(tmp_path)
    with pytest.raises(ValueError):
        provider.get_snapshot("MCL")
