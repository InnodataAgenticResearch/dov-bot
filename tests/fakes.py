"""
Deterministic in-memory HTTP transport fake for dov-bot unit tests.
"""

from __future__ import annotations

from typing import Any

from dov_bot.linear_sync import HttpResponse


class FakeHttpTransport:
    """In-memory `HttpTransport` implementation for deterministic testing."""

    def __init__(self) -> None:
        self.get_calls: list[dict[str, Any]] = []
        self.post_json_calls: list[dict[str, Any]] = []
        self.get_responses: list[HttpResponse] = []
        self.post_responses: list[HttpResponse] = []

    def queue_get_response(self, status_code: int, body: str = "{}") -> None:
        """Queue an HTTP response for the next `get` call."""
        self.get_responses.append(HttpResponse(status_code=status_code, body=body))

    def queue_post_response(self, status_code: int, body: str = "{}") -> None:
        """Queue an HTTP response for the next `post_json` call."""
        self.post_responses.append(HttpResponse(status_code=status_code, body=body))

    def get(
        self,
        url: str,
        *,
        headers: dict[str, str],
        timeout: float,
    ) -> HttpResponse:
        """Record a GET request and return the next queued `HttpResponse`."""
        self.get_calls.append(
            {
                "url": url,
                "headers": headers,
                "timeout": timeout,
            }
        )
        if not self.get_responses:
            return HttpResponse(status_code=200, body="{}")
        return self.get_responses.pop(0)

    def post_json(
        self,
        url: str,
        *,
        payload: dict[str, Any],
        headers: dict[str, str],
        timeout: float,
    ) -> HttpResponse:
        """Record a POST JSON request and return the next queued `HttpResponse`."""
        self.post_json_calls.append(
            {
                "url": url,
                "payload": payload,
                "headers": headers,
                "timeout": timeout,
            }
        )
        if not self.post_responses:
            return HttpResponse(status_code=200, body="{}")
        return self.post_responses.pop(0)
