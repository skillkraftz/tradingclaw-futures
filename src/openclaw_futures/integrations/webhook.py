"""Optional webhook integration."""
from __future__ import annotations

import json
from urllib import error, parse, request

from openclaw_futures.config import AppConfig


def post_message(config: AppConfig, content: str) -> dict[str, object]:
    if not config.webhook_url:
        return _result(
            enabled=False,
            attempted=False,
            sent=False,
            reason_code="webhook_disabled",
            reason="webhook disabled: TRADINGCLAW_WEBHOOK_URL is not configured",
        )

    target_url = build_webhook_url(config.webhook_url, config.webhook_thread_id)
    payload = {"content": content}
    http_request = request.Request(
        target_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with request.urlopen(http_request, timeout=5) as response:
            return _result(
                enabled=True,
                attempted=True,
                sent=True,
                status=response.status,
                url=target_url,
                payload=payload,
            )
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace").strip()
        detail = f"HTTP {exc.code}"
        if body:
            detail = f"{detail}: {body[:240]}"
        reason_code = "invalid_thread_id" if "thread" in body.lower() and exc.code == 400 else "http_error"
        return _result(
            enabled=True,
            attempted=True,
            sent=False,
            status=exc.code,
            url=target_url,
            payload=payload,
            reason_code=reason_code,
            reason=detail,
        )
    except (error.URLError, OSError) as exc:
        return _result(
            enabled=True,
            attempted=True,
            sent=False,
            url=target_url,
            payload=payload,
            reason_code="transport_error",
            reason=str(exc),
        )


def build_webhook_url(base_url: str, thread_id: str) -> str:
    if not thread_id:
        return base_url
    parsed = parse.urlsplit(base_url)
    query = parse.parse_qsl(parsed.query, keep_blank_values=True)
    query.append(("thread_id", thread_id))
    return parse.urlunsplit(parsed._replace(query=parse.urlencode(query)))


def suppressed_result(*, config: AppConfig, reason_code: str, reason: str) -> dict[str, object]:
    return _result(
        enabled=bool(config.webhook_url),
        attempted=False,
        sent=False,
        url=build_webhook_url(config.webhook_url, config.webhook_thread_id) if config.webhook_url else None,
        reason_code=reason_code,
        reason=reason,
    )


def _result(
    *,
    enabled: bool,
    attempted: bool,
    sent: bool,
    reason_code: str | None = None,
    reason: str | None = None,
    status: int | None = None,
    url: str | None = None,
    payload: dict[str, object] | None = None,
) -> dict[str, object]:
    result: dict[str, object] = {
        "enabled": enabled,
        "attempted": attempted,
        "sent": sent,
    }
    if reason_code is not None:
        result["reason_code"] = reason_code
    if reason is not None:
        result["reason"] = reason
    if status is not None:
        result["status"] = status
    if url is not None:
        result["url"] = url
    if payload is not None:
        result["payload"] = payload
    return result
