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
    headers = build_webhook_headers(config)
    http_request = request.Request(
        target_url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
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
                request_headers=_sanitized_headers(headers),
                response_headers=dict(response.headers.items()) if getattr(response, "headers", None) is not None else None,
            )
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace").strip()
        detail = f"HTTP {exc.code}"
        if body:
            detail = f"{detail}: {body[:240]}"
        reason_code = classify_webhook_failure(exc.code, body, target_url)
        return _result(
            enabled=True,
            attempted=True,
            sent=False,
            status=exc.code,
            url=target_url,
            payload=payload,
            body=body[:4000] if body else None,
            request_headers=_sanitized_headers(headers),
            response_headers=dict(exc.headers.items()) if exc.headers is not None else None,
            reason_code=reason_code,
            reason=_failure_reason(reason_code, detail),
        )
    except (error.URLError, OSError) as exc:
        return _result(
            enabled=True,
            attempted=True,
            sent=False,
            url=target_url,
            payload=payload,
            request_headers=_sanitized_headers(headers),
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


def build_webhook_headers(config: AppConfig) -> dict[str, str]:
    return {
        "User-Agent": config.webhook_user_agent,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def classify_webhook_failure(status: int, body: str, url: str) -> str:
    lowered = body.lower()
    if "cloudflare" in lowered or "error code 1010" in lowered or "access denied" in lowered:
        return "cloudflare_block"
    if status == 400 and "thread" in lowered:
        return "invalid_thread_id"
    if status == 404:
        return "invalid_webhook_url"
    if status in {401, 403}:
        return "forbidden"
    if status >= 400:
        return "http_error"
    return "transport_error"


def _failure_reason(reason_code: str, detail: str) -> str:
    labels = {
        "cloudflare_block": "Cloudflare/browser-signature block",
        "invalid_thread_id": "invalid thread_id",
        "invalid_webhook_url": "invalid webhook URL",
        "forbidden": "permissions/forbidden",
        "http_error": "HTTP error",
        "transport_error": "transport/network error",
    }
    prefix = labels.get(reason_code, reason_code)
    return f"{prefix}: {detail}"


def _sanitized_headers(headers: dict[str, str]) -> dict[str, str]:
    return dict(headers)


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
    body: str | None = None,
    request_headers: dict[str, str] | None = None,
    response_headers: dict[str, str] | None = None,
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
    if body is not None:
        result["body"] = body
    if request_headers is not None:
        result["request_headers"] = request_headers
    if response_headers is not None:
        result["response_headers"] = response_headers
    return result
