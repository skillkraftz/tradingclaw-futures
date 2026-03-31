from __future__ import annotations

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
