"""Configurable client for the local OpenClaw gateway."""
from __future__ import annotations

import json
from urllib import error, parse, request

from openclaw_futures.config import AppConfig


class OpenClawClient:
    def __init__(
        self,
        *,
        enabled: bool = False,
        base_url: str = "http://127.0.0.1:18789",
        reasoning_path: str = "",
        auth_token: str = "",
        auth_header: str = "Authorization",
        timeout: int = 10,
    ) -> None:
        self.enabled = enabled
        self.base_url = base_url.rstrip("/")
        self.reasoning_path = reasoning_path
        self.auth_token = auth_token
        self.auth_header = auth_header
        self.timeout = timeout

    @classmethod
    def from_config(cls, config: AppConfig) -> "OpenClawClient":
        return cls(
            enabled=config.openclaw_enabled,
            base_url=config.openclaw_base_url,
            reasoning_path=config.openclaw_reasoning_path,
            auth_token=config.openclaw_auth_token,
            auth_header=config.openclaw_auth_header,
        )

    def submit_reasoning(
        self,
        payload: dict[str, object],
        *,
        path: str | None = None,
    ) -> dict[str, object]:
        if not self.enabled:
            return {"enabled": False, "sent": False, "reason": "OpenClaw integration disabled"}

        target_path = path if path is not None else self.reasoning_path
        if not target_path:
            return {"enabled": True, "sent": False, "reason": "OpenClaw reasoning path not configured"}

        url = self._build_url(target_path)
        headers = {"Content-Type": "application/json"}
        if self.auth_token:
            headers[self.auth_header] = self.auth_token
        http_request = request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with request.urlopen(http_request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8", "replace")
                body = json.loads(raw) if raw else None
                return {
                    "enabled": True,
                    "sent": True,
                    "status": response.status,
                    "url": url,
                    "response": body,
                }
        except error.HTTPError as exc:
            raw = exc.read().decode("utf-8", "replace")
            return {
                "enabled": True,
                "sent": False,
                "status": exc.code,
                "url": url,
                "reason": raw or exc.reason,
            }
        except (error.URLError, OSError) as exc:
            return {
                "enabled": True,
                "sent": False,
                "url": url,
                "reason": str(exc),
            }

    def _build_url(self, path: str) -> str:
        if path.startswith("http://") or path.startswith("https://"):
            return path
        normalized = path if path.startswith("/") else f"/{path}"
        parsed = parse.urlsplit(self.base_url)
        return parse.urlunsplit((parsed.scheme, parsed.netloc, normalized, "", ""))
