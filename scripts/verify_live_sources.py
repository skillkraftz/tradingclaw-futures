#!/usr/bin/env python3
"""Verify legacy live-data sources without wiring them into TradingClaw.

This script reproduces the old morning-report fetch behavior where reasonable:
- single browser-style User-Agent header
- plain GET requests
- 20s timeout
- 3 total attempts with 1s/2s backoff on failures

It probes only the proxies relevant to TradingClaw:
- MCL proxy via CL / CL futures
- M6E proxy via EURUSD spot
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from typing import Callable

LEGACY_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)
REQUEST_TIMEOUT = 20
MAX_RETRIES = 3
ET_OFFSET = timedelta(hours=-5)


@dataclass(frozen=True)
class Probe:
    name: str
    symbol: str
    url: str
    headers: dict[str, str]
    parser: Callable[[str], dict[str, object]]
    notes: str


class KVParser(HTMLParser):
    """Collect consecutive table cell pairs as label/value mappings."""

    def __init__(self) -> None:
        super().__init__()
        self._in_cell = False
        self._cell_buf: list[str] = []
        self._current_row: list[str] = []
        self.rows: list[list[str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("td", "th"):
            self._in_cell = True
            self._cell_buf = []
        elif tag == "tr":
            self._current_row = []

    def handle_endtag(self, tag: str) -> None:
        if tag in ("td", "th"):
            self._in_cell = False
            self._current_row.append(" ".join(self._cell_buf).strip())
        elif tag == "tr":
            if any(self._current_row):
                self.rows.append(self._current_row[:])
            self._current_row = []

    def handle_data(self, data: str) -> None:
        if self._in_cell:
            chunk = data.strip()
            if chunk:
                self._cell_buf.append(chunk)


class FetchError(RuntimeError):
    def __init__(self, status: int | None, message: str) -> None:
        super().__init__(message)
        self.status = status


def fetch_text(url: str, headers: dict[str, str]) -> tuple[int | None, str]:
    """Mirror the legacy fetch wrapper: plain GET with retry/backoff."""
    last_exc: Exception | None = None
    for attempt in range(MAX_RETRIES):
        request = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
                return response.status, response.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")
            last_exc = FetchError(exc.code, f"HTTP {exc.code}: {body[:200] or exc.reason}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(2**attempt)
        except Exception as exc:  # noqa: BLE001
            last_exc = FetchError(None, str(exc))
            if attempt < MAX_RETRIES - 1:
                time.sleep(2**attempt)
    if last_exc is None:
        raise FetchError(None, f"Failed to fetch {url}")
    raise last_exc


def yahoo_ts_to_et_str(unix_ts: int) -> str:
    dt_utc = datetime.fromtimestamp(unix_ts, tz=timezone.utc)
    dt_et = dt_utc + ET_OFFSET
    return dt_et.strftime("%Y-%m-%d %H:%M:%S")


def parse_yahoo_bars(text: str) -> dict[str, object]:
    data = json.loads(text)
    result = data["chart"]["result"][0]
    timestamps = result["timestamp"]
    quote = result["indicators"]["quote"][0]
    opens = quote["open"]
    highs = quote["high"]
    lows = quote["low"]
    closes = quote["close"]

    bars: list[str] = []
    for idx, ts in enumerate(timestamps):
        values = (opens[idx], highs[idx], lows[idx], closes[idx])
        if any(value is None for value in values):
            continue
        bars.append(yahoo_ts_to_et_str(ts))

    if not bars:
        raise ValueError("Yahoo returned no parseable OHLC bars")

    return {
        "parse_succeeded": True,
        "bars_returned": len(bars),
        "timestamp_start": bars[0],
        "timestamp_end": bars[-1],
    }


def parse_stooq_intraday_csv(text: str) -> dict[str, object]:
    reader = csv.DictReader(io.StringIO(text))
    bars: list[str] = []
    for row in reader:
        try:
            ts = f"{row['Date'].strip()} {row['Time'].strip()}"
            float(row["Open"])
            float(row["High"])
            float(row["Low"])
            float(row["Close"])
        except (KeyError, ValueError, AttributeError):
            continue
        bars.append(ts)

    if not bars:
        raise ValueError("Stooq intraday response did not contain parseable bars")

    bars.sort()
    return {
        "parse_succeeded": True,
        "bars_returned": len(bars),
        "timestamp_start": bars[0],
        "timestamp_end": bars[-1],
    }


def parse_stooq_daily_csv(text: str) -> dict[str, object]:
    reader = csv.DictReader(io.StringIO(text))
    rows: list[str] = []
    for row in reader:
        try:
            day = row["Date"].strip()
            float(row["Open"])
            float(row["High"])
            float(row["Low"])
            float(row["Close"])
        except (KeyError, ValueError, AttributeError):
            continue
        rows.append(day)

    if not rows:
        raise ValueError("Stooq daily response did not contain parseable rows")

    rows.sort()
    return {
        "parse_succeeded": True,
        "bars_returned": len(rows),
        "timestamp_start": rows[0],
        "timestamp_end": rows[-1],
    }


def parse_finviz_cl(text: str) -> dict[str, object]:
    match = re.search(
        r'<script[^>]+id=["\']futures-init-data["\'][^>]*>(.*?)</script>',
        text,
        re.DOTALL,
    )
    if match:
        data = json.loads(match.group(1))
        tile = data["tiles"]["CL"]
        return {
            "parse_succeeded": True,
            "bars_returned": 0,
            "timestamp_start": None,
            "timestamp_end": None,
            "levels": {
                "last": tile.get("last"),
                "high": tile.get("high"),
                "low": tile.get("low"),
                "prevClose": tile.get("prevClose"),
            },
        }

    parser = KVParser()
    parser.feed(text)
    if not parser.rows:
        raise ValueError("Finviz page had no table rows and no futures-init-data JSON")
    return {
        "parse_succeeded": True,
        "bars_returned": 0,
        "timestamp_start": None,
        "timestamp_end": None,
        "levels": {},
    }


def build_probes(include_yahoo_1m_probe: bool) -> list[Probe]:
    headers = {"User-Agent": LEGACY_USER_AGENT}
    probes = [
        Probe(
            name="yahoo_5m_legacy",
            symbol="M6E",
            url="https://query1.finance.yahoo.com/v8/finance/chart/EURUSD=X?interval=5m&range=5d",
            headers=headers,
            parser=parse_yahoo_bars,
            notes="Legacy morning-report Yahoo path for EURUSD spot proxy.",
        ),
        Probe(
            name="yahoo_5m_legacy",
            symbol="MCL",
            url="https://query1.finance.yahoo.com/v8/finance/chart/CL=F?interval=5m&range=5d",
            headers=headers,
            parser=parse_yahoo_bars,
            notes="Legacy morning-report Yahoo path for CL futures proxy.",
        ),
        Probe(
            name="stooq_5m_legacy",
            symbol="M6E",
            url="https://stooq.com/q/i/l/?s=eurusd&i=5",
            headers=headers,
            parser=parse_stooq_intraday_csv,
            notes="Legacy morning-report Stooq intraday fallback for EURUSD spot proxy.",
        ),
        Probe(
            name="stooq_5m_legacy",
            symbol="MCL",
            url="https://stooq.com/q/i/l/?s=cl.f&i=5",
            headers=headers,
            parser=parse_stooq_intraday_csv,
            notes="Legacy morning-report Stooq intraday fallback for CL futures proxy.",
        ),
        Probe(
            name="stooq_daily_legacy",
            symbol="M6E",
            url="https://stooq.com/q/d/l/?s=eurusd&i=d",
            headers=headers,
            parser=parse_stooq_daily_csv,
            notes="Legacy morning-report daily EURUSD path used by forex levels.",
        ),
        Probe(
            name="finviz_cl_legacy",
            symbol="MCL",
            url="https://finviz.com/futures_charts.ashx?t=CL&p=d",
            headers=headers,
            parser=parse_finviz_cl,
            notes="Legacy morning-report crude daily levels source.",
        ),
    ]
    if include_yahoo_1m_probe:
        probes.extend(
            [
                Probe(
                    name="yahoo_1m_probe",
                    symbol="M6E",
                    url="https://query1.finance.yahoo.com/v8/finance/chart/EURUSD=X?interval=1m&range=1d",
                    headers=headers,
                    parser=parse_yahoo_bars,
                    notes="Capability probe only. Not used by the old code.",
                ),
                Probe(
                    name="yahoo_1m_probe",
                    symbol="MCL",
                    url="https://query1.finance.yahoo.com/v8/finance/chart/CL=F?interval=1m&range=1d",
                    headers=headers,
                    parser=parse_yahoo_bars,
                    notes="Capability probe only. Not used by the old code.",
                ),
            ]
        )
    return probes


def run_probe(probe: Probe) -> dict[str, object]:
    result: dict[str, object] = {
        "source": probe.name,
        "symbol": probe.symbol,
        "url": probe.url,
        "headers": probe.headers,
        "http_status": None,
        "parse_succeeded": False,
        "bars_returned": 0,
        "timestamp_start": None,
        "timestamp_end": None,
        "notes": probe.notes,
    }
    try:
        status, text = fetch_text(probe.url, probe.headers)
        result["http_status"] = status
        parsed = probe.parser(text)
        result.update(parsed)
    except FetchError as exc:
        result["http_status"] = exc.status
        result["error"] = str(exc)
    except Exception as exc:  # noqa: BLE001
        result["error"] = str(exc)
    return result


def print_result(result: dict[str, object]) -> None:
    print(f"=== {result['source']} :: {result['symbol']} ===")
    print(f"url: {result['url']}")
    print(f"headers: {json.dumps(result['headers'], sort_keys=True)}")
    print(f"http_status: {result['http_status']}")
    print(f"parse_succeeded: {result['parse_succeeded']}")
    print(f"bars_returned: {result['bars_returned']}")
    print(f"timestamp_start: {result['timestamp_start']}")
    print(f"timestamp_end: {result['timestamp_end']}")
    if "levels" in result:
        print(f"levels: {json.dumps(result['levels'], sort_keys=True)}")
    if "error" in result:
        print(f"error: {result['error']}")
    print(f"notes: {result['notes']}")
    print()


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify legacy live market-data sources from morning-report.",
    )
    parser.add_argument(
        "--symbol",
        action="append",
        choices=["MCL", "M6E"],
        help="Limit the run to one or more proxy symbols. Defaults to both.",
    )
    parser.add_argument(
        "--skip-yahoo-1m-probe",
        action="store_true",
        help="Skip the extra Yahoo 1-minute capability probe.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    wanted_symbols = set(args.symbol or ["MCL", "M6E"])
    probes = [
        probe
        for probe in build_probes(include_yahoo_1m_probe=not args.skip_yahoo_1m_probe)
        if probe.symbol in wanted_symbols
    ]
    for probe in probes:
        print_result(run_probe(probe))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
