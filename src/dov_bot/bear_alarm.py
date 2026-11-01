"""
Dov-Bot 0-to-5 Bear Alarm Urgency Protocol and `@rox-bot` (`@ops-bot`) peer coordination.

Implements:
- `0` bears (zero `🐻` emojis in text): All systems nominal; velocity and CI gates 100% on track.
- `1` bear (`🐻`): Minor observation (e.g., new repo started without a linked Linear issue yet).
- `2` bears (`🐻🐻`): Emerging drift (e.g., in-progress bead >24h or missing project overview).
- `3` bears (`🐻🐻🐻`): Active blocker or missing board coverage requiring TPM intervention today.
- `4` bears (`🐻🐻🐻🐻`): High-severity delivery jeopardy or broken CI gate across a critical path.
- `5` bears (`🐻🐻🐻🐻🐻`): **5-ALARM FIRE!** Critical blocker — all hands must swarm immediately.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

BEAR_EMOJI = "🐻"

BEAR_LEVEL_LABELS: dict[int, str] = {
    0: "All Clear / On Track",
    1: "Minor Observation",
    2: "Emerging Drift",
    3: "Active Blocker",
    4: "Delivery Jeopardy",
    5: "5-ALARM FIRE!",
}

BEAR_REQUIRED_ACTIONS: dict[int, str] = {
    0: "Continue execution; velocity, Linear board, and quality gates are 100% on track.",
    1: "Create and link the corresponding INN-* Linear issue and local bd bead in this session.",
    2: (
        "Post an async progress update, refresh the Linear project overview, "
        "or split the stale bead."
    ),
    3: (
        "Assign an owner immediately, document the unblock plan in Linear, "
        "and escalate infra bottlenecks to @rox-bot."
    ),
    4: (
        "Halt feature merges on the affected path and restore a green quality gate "
        "(just check) immediately."
    ),
    5: (
        "5-ALARM FIRE! All hands must swarm immediately to drive the blocker "
        "to completion and verify on Linear."
    ),
}


@dataclass(frozen=True)
class BearSignalInput:
    """Telemetry inputs evaluated by Dov's 0-to-5 Bear Alarm Urgency Protocol."""

    untracked_workstreams: int = 0
    stale_in_progress_count: int = 0
    missing_overviews_count: int = 0
    active_blockers_count: int = 0
    unowned_p0_p1_count: int = 0
    broken_ci_pipelines: int = 0
    production_outage_or_5_alarm: bool = False
    infra_vm_anomaly: str | None = None
    summary: str = ""


@dataclass(frozen=True)
class BearAssessment:
    """Result of evaluating delivery and operational telemetry on the 0-to-5 Bear scale."""

    level: int
    label: str
    emoji_prefix: str
    reasons: tuple[str, ...]
    required_action: str
    formatted_message: str
    rox_bot_handoff: str | None = None


def format_rox_bot_handoff(
    level: int,
    *,
    vm_or_service: str,
    issue_id: str = "INN-235",
    detail: str = "",
) -> str:
    """Format a cross-bot peer escalation query from `@dov-bot` to `@rox-bot` (`@ops-bot`)."""
    clamped = max(3, min(5, level))
    bears = BEAR_EMOJI * clamped
    detail_suffix = f" — {detail.strip()}" if detail.strip() else ""
    return (
        f"{bears} @rox-bot (@ops-bot) [TPM Peer Escalation | {issue_id} | {clamped}-Bear Alarm]: "
        f"Infrastructure/VM blocker detected on `{vm_or_service}`{detail_suffix}. "
        "Please run health diagnostics and report remediation ETA so Dov can "
        "update the Linear board."
    )


def evaluate_bear_urgency(
    signal: BearSignalInput,
    *,
    issue_id: str = "INN-235",
) -> BearAssessment:
    """
    Evaluate `BearSignalInput` into a deterministic `0`-to-`5` `BearAssessment`.

    At level `0`, `formatted_message` is guaranteed to contain zero `🐻` emojis.
    """
    level = 0
    reasons: list[str] = []

    if signal.untracked_workstreams > 0:
        level = max(level, 1)
        reasons.append(
            f"{signal.untracked_workstreams} active workstream(s) started "
            "without a linked Linear issue."
        )

    if signal.stale_in_progress_count > 0 or signal.missing_overviews_count > 0:
        level = max(level, 2)
        if signal.stale_in_progress_count > 0:
            reasons.append(
                f"{signal.stale_in_progress_count} in-progress issue(s)/bead(s) "
                ">24h without activity."
            )
        if signal.missing_overviews_count > 0:
            reasons.append(
                f"{signal.missing_overviews_count} active Linear project(s) "
                "missing an overview document."
            )

    if (
        signal.active_blockers_count > 0
        or signal.unowned_p0_p1_count > 0
        or signal.infra_vm_anomaly is not None
    ):
        level = max(level, 3)
        if signal.active_blockers_count > 0:
            reasons.append(
                f"{signal.active_blockers_count} active blocker(s) requiring "
                "TPM intervention today."
            )
        if signal.unowned_p0_p1_count > 0:
            reasons.append(
                f"{signal.unowned_p0_p1_count} unowned P0/P1 Linear issue(s) missing an assignee."
            )
        if signal.infra_vm_anomaly is not None:
            reasons.append(f"Infrastructure/VM blocker reported: {signal.infra_vm_anomaly}.")

    if signal.broken_ci_pipelines > 0:
        level = max(level, 4)
        reasons.append(
            f"{signal.broken_ci_pipelines} broken CI/quality gate pipeline(s) across critical path."
        )

    if signal.production_outage_or_5_alarm:
        level = 5
        reasons.append("Critical production/delivery blocker triggered 5-ALARM FIRE.")

    if not reasons:
        reasons.append("Velocity, Linear board coverage, and CI quality gates are 100% on track.")

    label = BEAR_LEVEL_LABELS[level]
    emoji_prefix = "" if level == 0 else BEAR_EMOJI * level
    required_action = BEAR_REQUIRED_ACTIONS[level]
    summary_text = f" ({signal.summary.strip()})" if signal.summary.strip() else ""

    rox_handoff: str | None = None
    if level >= 3 and signal.infra_vm_anomaly is not None:
        rox_handoff = format_rox_bot_handoff(
            level,
            vm_or_service=signal.infra_vm_anomaly,
            issue_id=issue_id,
            detail=signal.summary,
        )

    if level == 0:
        formatted = (
            f"[Dov TPM Status: 0 Bears — {label}]{summary_text} "
            f"{' '.join(reasons)} Action: {required_action}"
        )
    else:
        formatted = (
            f"{emoji_prefix} [Dov TPM Status: {level} Bear(s) — {label}]{summary_text} "
            f"{' '.join(reasons)} Action: {required_action}"
        )
        if rox_handoff is not None:
            formatted = f"{formatted}\n{rox_handoff}"

    return BearAssessment(
        level=level,
        label=label,
        emoji_prefix=emoji_prefix,
        reasons=tuple(reasons),
        required_action=required_action,
        formatted_message=formatted,
        rox_bot_handoff=rox_handoff,
    )


def ingest_rox_bot_anomaly(
    *,
    service_name: str,
    severity: str,
    detail: str,
    affected_epics: Sequence[str] = (),
) -> BearAssessment:
    """
    Recalculate project delivery risk when `@rox-bot` (`@ops-bot`) reports a GCP VM/service anomaly.

    Supported severities: `"warning"` (2 bears), `"critical"` (4 bears), `"outage"` (5 bears),
    or any other operational alert (defaults to 3 bears).
    """
    norm = severity.strip().lower()
    epics_label = ", ".join(affected_epics) if affected_epics else "INN-235"
    summary = f"@rox-bot anomaly on {service_name} affecting {epics_label}: {detail.strip()}"

    if norm == "warning":
        return evaluate_bear_urgency(
            BearSignalInput(
                stale_in_progress_count=1,
                summary=summary,
            ),
            issue_id=epics_label,
        )
    if norm == "critical":
        return evaluate_bear_urgency(
            BearSignalInput(
                broken_ci_pipelines=1,
                infra_vm_anomaly=service_name,
                summary=summary,
            ),
            issue_id=epics_label,
        )
    if norm == "outage":
        return evaluate_bear_urgency(
            BearSignalInput(
                production_outage_or_5_alarm=True,
                infra_vm_anomaly=service_name,
                summary=summary,
            ),
            issue_id=epics_label,
        )
    return evaluate_bear_urgency(
        BearSignalInput(
            active_blockers_count=1,
            infra_vm_anomaly=service_name,
            summary=summary,
        ),
        issue_id=epics_label,
    )


def render_bear_help_page() -> str:
    """Render the canonical `BEAR_ALARM_HELP.md` specification page."""
    lines = [
        "# Dov-Bot (The Bear) — 0-to-5 Bear Alarm Urgency Protocol (`BEAR_ALARM_HELP.md`)",
        "",
        '**Dov** (`@dov-bot` / `@tpm-bot`, Hebrew for *"The Bear"*) operates as a '
        "**Google L6 Technical Program Manager (TPM)** for **Innodata Agentic Research** "
        "(`https://linear.app/innodata-ai/team/INN/overview`, team key `INN`, "
        "ID `829852d8-8a12-4875-93bd-5d1d1e08fe0b`).",
        "",
        "Whenever Dov reports status, audits the Linear board, or escalates a delivery risk "
        "in Microsoft Teams, he classifies urgency using the "
        "**0-to-5 Bear Alarm Urgency Protocol**:",
        "",
        "| Bear Level | Prefix | Severity Name | Trigger Criteria "
        "| Required Engineering / TPM Action |",
        "| :--- | :--- | :--- | :--- | :--- |",
        "| **0 Bears** | *(No bear emoji)* | **All Clear / On Track** "
        "| Velocity, Linear board coverage (`INN-*`), Beads (`bd`) links, and `100%` coverage "
        "CI gates are completely green. "
        "| Continue execution; zero bear emojis appear anywhere in a `0`-bear status report. |",
        "| **1 Bear** | `🐻` | **Minor Observation** "
        "| A new repository or workstream started without a linked `INN-*` Linear issue "
        "or `bd` bead yet. "
        "| Create and link the corresponding `INN-*` issue and local bead within the "
        "current work session. |",
        "| **2 Bears** | `🐻🐻` | **Emerging Drift** "
        "| An in-progress bead (`bd`) or Linear issue has gone `>24h` without commit activity, "
        "or a project overview document is missing/outdated. "
        "| Post an async progress update, refresh the Linear project overview, "
        "or split the bead into smaller commits. |",
        "| **3 Bears** | `🐻🐻🐻` | **Active Blocker** "
        "| Active delivery blocker, unowned `P0`/`P1` Linear issue, or missing board coverage "
        "requiring TPM intervention today. "
        "| Assign an owner immediately, document the unblock plan in Linear, and escalate "
        "infra bottlenecks to `@rox-bot` (`@ops-bot`). |",
        "| **4 Bears** | `🐻🐻🐻🐻` | **Delivery Jeopardy** "
        "| High-severity delivery jeopardy or broken CI / quality gate "
        "(`just check`, `shac`, or `100%` coverage) across a critical path. "
        "| Halt feature merges on the affected path and prioritize restoring a "
        "green quality gate. |",
        "| **5 Bears** | `🐻🐻🐻🐻🐻` | **5-ALARM FIRE!** "
        "| Critical production or program-wide delivery blocker — service outage, "
        "data corruption risk, or hard deadline breach. "
        "| **ALL HANDS SWARM IMMEDIATELY** until the blocker is resolved, verified by "
        "`just check`, and closed on the Linear board. |",
        "",
        "## Cross-Bot Peer Coordination with `@rox-bot` (`@ops-bot`)",
        "",
        "1. **Outbound Escalation (`Dov -> @rox-bot`):**",
        "   - When Dov detects a `3+` bear blocker involving a GCP VM, systemd user bridge, "
        "or infrastructure endpoint, he appends a structured `@rox-bot` (`@ops-bot`) "
        "peer handoff block specifying the affected service, Linear issue (`INN-*`), "
        "and Bear Alarm level.",
        "2. **Inbound Telemetry (`@rox-bot -> Dov`):**",
        "   - When `@rox-bot` reports an infrastructure anomaly (`warning`, `critical`, "
        "or `outage`), Dov recalculates epic delivery risk and elevates the Bear Alarm level "
        "(`2` bears for `warning`, `4` bears for `critical`, `5` bears for `outage`).",
    ]
    return "\n".join(lines) + "\n"
