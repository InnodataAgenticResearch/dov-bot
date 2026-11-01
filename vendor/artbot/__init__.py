"""
Pinned `v0.2.0-artbot` (`3cfa4e8d2ed6c30c51f03c7a92b58df0a694c781`) public API surface
for hermetic Nix sandbox and CI execution when `../artbot/src` is not mounted.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Protocol

__version__ = "0.2.0"

CUSTOMER_LABEL_KEY = "customer"

FLEET_NODES_REGISTRY: dict[str, dict[str, Any]] = {
    "avi-bot": {
        "user": "avi",
        "zone": "me-west1-c",
        "customer": "Innodata",
        "bridge_unit": "avibot-teams-bridge.service",
        "bridge_port": 8651,
    },
    "bijal-bot": {
        "user": "bijal",
        "zone": "me-west1-c",
        "customer": "Innodata",
        "bridge_unit": "bijalbot-teams-bridge.service",
        "bridge_port": 8649,
    },
    "jj-bot": {
        "user": "jj",
        "zone": "me-west1-c",
        "customer": "Innodata",
        "bridge_unit": "jjbot-teams-bridge.service",
        "bridge_port": 8650,
    },
    "michael-bot": {
        "user": "michael",
        "zone": "me-west1-c",
        "customer": "Innodata",
        "bridge_unit": "artbot-teams-bridge.service",
        "bridge_port": 8648,
    },
    "tim-bot": {
        "user": "tim",
        "zone": "me-west1-c",
        "customer": "Innodata",
        "bridge_unit": "timbot-teams-bridge.service",
        "bridge_port": 8653,
    },
    "vibhor-bot": {
        "user": "vibhor",
        "zone": "me-west1-c",
        "customer": "Innodata",
        "bridge_unit": "artbot-teams-bridge.service",
        "bridge_port": 8648,
    },
    "ops-bot": {
        "user": "ops",
        "zone": "me-west1-c",
        "customer": "SJJCC",
        "bridge_unit": "opsbot-teams-bridge.service",
        "bridge_port": 8654,
    },
    "people-bot": {
        "user": "people",
        "zone": "me-west1-c",
        "customer": "SJJCC",
        "bridge_unit": "peoplebot-teams-bridge.service",
        "bridge_port": 8655,
    },
    "mantle-bot": {
        "user": "mantle",
        "zone": "me-west1-c",
        "customer": "SJJCC",
        "bridge_unit": "mantlebot-teams-bridge.service",
        "bridge_port": 8657,
    },
    "sid-bot": {
        "user": "sid",
        "zone": "me-west1-c",
        "customer": "SJJCC",
        "bridge_unit": "sidbot-teams-bridge.service",
        "bridge_port": 8658,
    },
    "dov-tpm-bot": {
        "user": "dov",
        "zone": "me-west1-c",
        "customer": "Innodata",
        "bridge_unit": "dovbot-teams-bridge.service",
        "bridge_port": 8658,
    },
    "rox-ops-bot": {
        "user": "rox",
        "zone": "me-west1-c",
        "customer": "Innodata",
        "bridge_unit": "roxbot-teams-bridge.service",
        "bridge_port": 8659,
    },
    "marketing-bot": {
        "user": "marketing",
        "zone": "me-west1-c",
        "customer": "Innodata",
        "bridge_unit": "marketingbot-teams-bridge.service",
        "bridge_port": 8660,
    },
    "voice-bot": {
        "user": "voice",
        "zone": "me-west1-c",
        "customer": "Innodata",
        "bridge_unit": "voicebot-webrtc.service",
        "bridge_port": 8656,
    },
    "dev-bot": {
        "user": "dev",
        "zone": "me-west1-c",
        "customer": "Innodata",
        "bridge_unit": "devbot-teams-bridge.service",
        "bridge_port": 8657,
    },
}

PEER_AGENT_ROSTER: tuple[str, ...] = (
    "dannybot",
    "artbot",
    "bijalbot",
    "avibot",
    "vibhorbot",
    "michaelbot",
    "jjbot",
    "timbot",
    "opsbot",
    "peoplebot",
    "mantlebot",
    "sidbot",
    "dov-bot",
    "rox-bot",
    "marketing-bot",
    "voice-bot",
    "dev-bot",
)

_LABEL_INVALID_RE = re.compile(r"[^a-z0-9_-]+")


def normalize_gcp_label_value(raw_value: str) -> str:
    """Normalize a string into a valid GCE label value (`[a-z0-9_-]{0,63}`)."""
    cleaned = _LABEL_INVALID_RE.sub("-", raw_value.strip().lower()).strip("-")
    return cleaned[:63] or "unassigned"


@dataclass(frozen=True)
class HttpResponse:
    """Minimal HTTP response object for deterministic testing and transports."""

    status_code: int
    body: str

    def json(self) -> dict[str, Any]:
        """Parse JSON response body."""
        res: dict[str, Any] = json.loads(self.body)
        return res


class HttpTransport(Protocol):
    """Protocol for injectable HTTP transports."""

    def get(
        self,
        url: str,
        *,
        headers: dict[str, str],
        timeout: float,
    ) -> HttpResponse: ...  # pragma: no cover - protocol stub

    def post_json(
        self,
        url: str,
        *,
        payload: dict[str, Any],
        headers: dict[str, str],
        timeout: float,
    ) -> HttpResponse: ...  # pragma: no cover - protocol stub

    def patch_json(
        self,
        url: str,
        *,
        payload: dict[str, Any],
        headers: dict[str, str],
        timeout: float,
    ) -> HttpResponse: ...  # pragma: no cover - protocol stub


class UrllibHttpTransport:
    """Standard-library urllib transport implementing `HttpTransport`."""

    def get(
        self,
        url: str,
        *,
        headers: dict[str, str],
        timeout: float,
    ) -> HttpResponse:  # pragma: no cover - network transport boundary
        req = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return HttpResponse(
                    status_code=int(resp.status),
                    body=resp.read().decode("utf-8", errors="replace"),
                )
        except urllib.error.HTTPError as exc:
            return HttpResponse(
                status_code=int(exc.code),
                body=exc.read().decode("utf-8", errors="replace"),
            )

    def post_json(
        self,
        url: str,
        *,
        payload: dict[str, Any],
        headers: dict[str, str],
        timeout: float,
    ) -> HttpResponse:  # pragma: no cover - network transport boundary
        data = json.dumps(payload).encode("utf-8")
        req_headers = {"Content-Type": "application/json", **headers}
        req = urllib.request.Request(url, data=data, headers=req_headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return HttpResponse(
                    status_code=int(resp.status),
                    body=resp.read().decode("utf-8", errors="replace"),
                )
        except urllib.error.HTTPError as exc:
            return HttpResponse(
                status_code=int(exc.code),
                body=exc.read().decode("utf-8", errors="replace"),
            )

    def patch_json(
        self,
        url: str,
        *,
        payload: dict[str, Any],
        headers: dict[str, str],
        timeout: float,
    ) -> HttpResponse:  # pragma: no cover - network transport boundary
        data = json.dumps(payload).encode("utf-8")
        req_headers = {"Content-Type": "application/json", **headers}
        req = urllib.request.Request(url, data=data, headers=req_headers, method="PATCH")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return HttpResponse(
                    status_code=int(resp.status),
                    body=resp.read().decode("utf-8", errors="replace"),
                )
        except urllib.error.HTTPError as exc:
            return HttpResponse(
                status_code=int(exc.code),
                body=exc.read().decode("utf-8", errors="replace"),
            )


@dataclass(frozen=True)
class LoopDataBlock:
    """Structured agentic data block stored in a Loop canvas."""

    block_id: str
    schema: str
    owner_agent: str
    updated_at: str
    payload: dict[str, Any]
    version: int = 1


@dataclass(frozen=True)
class PeerBlackboardHandoff:
    """Multi-agent peer blackboard handoff task stored in a shared channel Loop canvas."""

    handoff_id: str
    source_agent: str
    target_agent: str
    status: str
    task_summary: str
    context: dict[str, Any]
    updated_at: str


def serialize_loop_data_block(block: LoopDataBlock) -> str:
    """Serialize a `LoopDataBlock` into canonical single-line JSON."""
    envelope = {
        "_loop_agent_store": "v1",
        "block_id": block.block_id,
        "schema": block.schema,
        "owner_agent": block.owner_agent,
        "version": block.version,
        "updated_at": block.updated_at,
        "payload": block.payload,
    }
    return json.dumps(envelope, sort_keys=True, separators=(",", ":"))


def build_peer_blackboard_block(
    handoff: PeerBlackboardHandoff,
    *,
    version: int = 1,
) -> LoopDataBlock:
    """Convert a `PeerBlackboardHandoff` into a `LoopDataBlock` (`schema='peer.blackboard.v1'`)."""
    return LoopDataBlock(
        block_id=f"handoff:{handoff.handoff_id.strip()}",
        schema="peer.blackboard.v1",
        owner_agent=handoff.source_agent.strip(),
        updated_at=handoff.updated_at,
        version=version,
        payload={
            "handoff_id": handoff.handoff_id.strip(),
            "source_agent": handoff.source_agent.strip(),
            "target_agent": handoff.target_agent.strip(),
            "status": handoff.status.strip() or "pending",
            "task_summary": handoff.task_summary,
            "context": handoff.context,
        },
    )


__all__ = [
    "CUSTOMER_LABEL_KEY",
    "FLEET_NODES_REGISTRY",
    "PEER_AGENT_ROSTER",
    "HttpResponse",
    "HttpTransport",
    "LoopDataBlock",
    "PeerBlackboardHandoff",
    "UrllibHttpTransport",
    "__version__",
    "build_peer_blackboard_block",
    "normalize_gcp_label_value",
    "serialize_loop_data_block",
]
