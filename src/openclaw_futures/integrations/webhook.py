"""Optional webhook integration."""
from __future__ import annotations

import json
from urllib import error, parse, request

from openclaw_futures.config import AppConfig


def post_message(config: AppConfig, content: str) -> dict[str, object]:
    if not config.webhook_url:
        return {"enabled": False, "sent": False, "reason": "webhook not configured"}

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
            return {
                "enabled": True,
                "sent": True,
                "status": response.status,
                "url": target_url,
                "payload": payload,
            }
    except (error.URLError, OSError) as exc:
        return {
            "enabled": True,
            "sent": False,
            "url": target_url,
            "payload": payload,
            "reason": str(exc),
        }


def build_webhook_url(base_url: str, thread_id: str) -> str:
    if not thread_id:
        return base_url
    parsed = parse.urlsplit(base_url)
    query = parse.parse_qsl(parsed.query, keep_blank_values=True)
    query.append(("thread_id", thread_id))
    return parse.urlunsplit(parsed._replace(query=parse.urlencode(query)))
