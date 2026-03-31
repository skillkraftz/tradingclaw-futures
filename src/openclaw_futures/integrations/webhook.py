"""Optional webhook integration."""
from __future__ import annotations

import json
from urllib import request

from openclaw_futures.config import AppConfig


def post_message(config: AppConfig, content: str) -> dict[str, object]:
    if not config.webhook_url:
        return {"enabled": False, "sent": False, "reason": "webhook not configured"}

    payload = {"content": content}
    if config.webhook_thread_id:
        payload["thread_id"] = config.webhook_thread_id

    http_request = request.Request(
        config.webhook_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(http_request, timeout=5) as response:
        return {"enabled": True, "sent": True, "status": response.status}
