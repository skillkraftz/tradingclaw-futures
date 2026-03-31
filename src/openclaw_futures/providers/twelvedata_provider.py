"""Twelve Data live market-data provider for cached-bar sync."""
from __future__ import annotations

import json
from datetime import datetime
from itertools import groupby
from urllib import error, parse, request

from openclaw_futures.config import AppConfig, live_symbol_profile
from openclaw_futures.models import Bar


class TwelveDataError(RuntimeError):
    """Base provider error."""


class TwelveDataConfigurationError(TwelveDataError):
    """Configuration is missing or invalid."""


class TwelveDataUnsupportedIntervalError(TwelveDataError):
    """Provider does not support the requested interval."""


class TwelveDataEmptyResponseError(TwelveDataError):
    """Provider returned no bars."""


class TwelveDataMalformedResponseError(TwelveDataError):
    """Provider returned an unexpected payload."""


class TwelveDataProvider:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://api.twelvedata.com",
        symbol_map: dict[str, str] | None = None,
        timeout: int = 15,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.symbol_map = symbol_map or {"M6E": "EUR/USD"}
        self.timeout = timeout

    @classmethod
    def from_config(cls, config: AppConfig) -> "TwelveDataProvider":
        return cls(
            api_key=config.twelvedata_api_key,
            base_url=config.twelvedata_base_url,
            symbol_map={symbol: live_symbol_profile(symbol).provider_symbol for symbol in config.twelvedata_symbols},
        )

    def fetch_preferred_bars_many(
        self,
        *,
        symbols: list[str],
        start_times: dict[str, str | None],
        end_at: str | None = None,
        preferred_intervals: tuple[str, ...] | None = None,
    ) -> dict[str, dict[str, object]]:
        pending = list(symbols)
        results: dict[str, dict[str, object]] = {}
        errors: dict[str, str] = {}
        for interval in preferred_intervals or ("1min", "5min"):
            if not pending:
                break
            interval_pending: list[str] = []
            grouped = groupby(
                sorted(pending, key=lambda item: start_times.get(item) or ""),
                key=lambda item: start_times.get(item) or "",
            )
            for start_at, group in grouped:
                grouped_symbols = list(group)
                batch_results, batch_errors = self.fetch_bars_batch(
                    symbols=grouped_symbols,
                    interval=interval,
                    start_at=start_at or None,
                    end_at=end_at,
                )
                for symbol, bars in batch_results.items():
                    results[symbol] = {
                        "interval": interval,
                        "bars": bars,
                        "provider_symbol": self.resolve_symbol(symbol),
                    }
                for symbol, exc in batch_errors.items():
                    errors[symbol] = str(exc)
                    interval_pending.append(symbol)
            pending = interval_pending

        for symbol in pending:
            results[symbol] = {"error": errors.get(symbol, "no supported Twelve Data interval succeeded")}
        return results

    def fetch_preferred_bars(
        self,
        *,
        symbol: str,
        start_at: str | None = None,
        end_at: str | None = None,
        interval_override: str | None = None,
        preferred_intervals: tuple[str, ...] | None = None,
    ) -> tuple[str, list[Bar], str]:
        if interval_override:
            bars = self.fetch_bars(symbol=symbol, interval=interval_override, start_at=start_at, end_at=end_at)
            return interval_override, bars, self.resolve_symbol(symbol)

        errors: list[str] = []
        for interval in preferred_intervals or ("1min", "5min"):
            try:
                bars = self.fetch_bars(symbol=symbol, interval=interval, start_at=start_at, end_at=end_at)
                return interval, bars, self.resolve_symbol(symbol)
            except (TwelveDataUnsupportedIntervalError, TwelveDataEmptyResponseError, TwelveDataMalformedResponseError) as exc:
                errors.append(f"{interval}: {exc}")
                continue
        raise TwelveDataError("; ".join(errors) or "no supported Twelve Data interval succeeded")

    def fetch_bars(
        self,
        *,
        symbol: str,
        interval: str,
        start_at: str | None = None,
        end_at: str | None = None,
    ) -> list[Bar]:
        if not self.api_key:
            raise TwelveDataConfigurationError("TRADINGCLAW_TWELVEDATA_API_KEY is required for live sync")
        if interval not in {"1min", "5min"}:
            raise TwelveDataUnsupportedIntervalError(f"unsupported interval={interval!r}")

        payload = self._request_json(
            "/time_series",
            {
                "symbol": self.resolve_symbol(symbol),
                "interval": interval,
                "apikey": self.api_key,
                "format": "JSON",
                "timezone": "America/New_York",
                "order": "ASC",
                **({"start_date": start_at} if start_at else {}),
                **({"end_date": end_at} if end_at else {}),
            },
        )
        return self._parse_bars(payload)

    def fetch_bars_batch(
        self,
        *,
        symbols: list[str],
        interval: str,
        start_at: str | None = None,
        end_at: str | None = None,
    ) -> tuple[dict[str, list[Bar]], dict[str, Exception]]:
        if not symbols:
            return {}, {}
        if len(symbols) == 1:
            symbol = symbols[0]
            try:
                return {symbol: self.fetch_bars(symbol=symbol, interval=interval, start_at=start_at, end_at=end_at)}, {}
            except Exception as exc:  # noqa: BLE001
                return {}, {symbol: exc}
        payload = self._request_json(
            "/time_series",
            {
                "symbol": ",".join(self.resolve_symbol(symbol) for symbol in symbols),
                "interval": interval,
                "apikey": self.api_key,
                "format": "JSON",
                "timezone": "America/New_York",
                "order": "ASC",
                **({"start_date": start_at} if start_at else {}),
                **({"end_date": end_at} if end_at else {}),
            },
        )
        return self._parse_batch_payload(symbols, payload)

    def resolve_symbol(self, symbol: str) -> str:
        try:
            return self.symbol_map[symbol.upper()]
        except KeyError as exc:
            raise TwelveDataConfigurationError(f"unsupported live symbol={symbol!r}") from exc

    def _request_json(self, path: str, params: dict[str, str]) -> dict[str, object]:
        url = f"{self.base_url}{path}?{parse.urlencode(params)}"
        http_request = request.Request(
            url,
            headers={"User-Agent": "TradingClaw/0.1 (+local live sync)"},
            method="GET",
        )
        try:
            with request.urlopen(http_request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8", "replace")
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")
            raise TwelveDataError(f"Twelve Data HTTP {exc.code}: {body[:200] or exc.reason}") from exc
        except error.URLError as exc:
            raise TwelveDataError(f"Twelve Data request failed: {exc.reason}") from exc
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise TwelveDataMalformedResponseError("Twelve Data returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise TwelveDataMalformedResponseError("Twelve Data response must be a JSON object")
        if payload.get("status") == "error":
            code = str(payload.get("code", ""))
            message = str(payload.get("message", "unknown Twelve Data error"))
            if code in {"400", "401", "404"} and "interval" in message.lower():
                raise TwelveDataUnsupportedIntervalError(message)
            raise TwelveDataError(message)
        return payload

    def _parse_bars(self, payload: dict[str, object]) -> list[Bar]:
        values = payload.get("values")
        if not isinstance(values, list):
            raise TwelveDataMalformedResponseError("Twelve Data payload is missing 'values'")
        bars: list[Bar] = []
        for value in values:
            if not isinstance(value, dict):
                raise TwelveDataMalformedResponseError("Twelve Data bar rows must be objects")
            try:
                ts = _normalize_timestamp(str(value["datetime"]))
                bars.append(
                    Bar(
                        ts=ts,
                        open=float(value["open"]),
                        high=float(value["high"]),
                        low=float(value["low"]),
                        close=float(value["close"]),
                        volume=float(value.get("volume", 0.0) or 0.0),
                    )
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise TwelveDataMalformedResponseError("Twelve Data returned a malformed bar row") from exc
        if not bars:
            raise TwelveDataEmptyResponseError("Twelve Data returned no bars")
        return bars

    def _parse_batch_payload(
        self,
        symbols: list[str],
        payload: dict[str, object],
    ) -> tuple[dict[str, list[Bar]], dict[str, Exception]]:
        results: dict[str, list[Bar]] = {}
        errors: dict[str, Exception] = {}
        provider_to_internal = {self.resolve_symbol(symbol): symbol for symbol in symbols}

        if all(provider_symbol in payload for provider_symbol in provider_to_internal):
            for provider_symbol, symbol in provider_to_internal.items():
                try:
                    item = payload[provider_symbol]
                    if not isinstance(item, dict):
                        raise TwelveDataMalformedResponseError("batch payload entries must be objects")
                    results[symbol] = self._parse_bars(item)
                except Exception as exc:  # noqa: BLE001
                    errors[symbol] = exc
            return results, errors

        data_section = payload.get("data")
        if isinstance(data_section, dict):
            nested_payload: dict[str, object] = {}
            for provider_symbol in provider_to_internal:
                if provider_symbol in data_section:
                    nested_payload[provider_symbol] = data_section[provider_symbol]
            if nested_payload:
                return self._parse_batch_payload(symbols, nested_payload)

        raise TwelveDataMalformedResponseError("Twelve Data batch payload did not include per-symbol data")


def _normalize_timestamp(raw: str) -> str:
    if "T" in raw:
        return datetime.fromisoformat(raw).strftime("%Y-%m-%d %H:%M:%S")
    if len(raw) == 10:
        return f"{raw} 00:00:00"
    return raw
