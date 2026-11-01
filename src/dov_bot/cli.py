"""
Command-line interface for Dov-Bot (`dov-bot`).

Subcommands:
- `upstream-status`: Inspect the pinned upstream `artbot` release tag, commit SHA, and allowlist.
- `help-page`: Render (and optionally write) the 0-to-5 Bear Alarm Urgency Protocol help page.
- `bear-check`: Evaluate telemetry on the 0-to-5 Bear Alarm scale and emit `@rox-bot` handoffs.
- `velocity-report`: Generate coding-style, cycle-time velocity, and epic ETA reports from SQLite.
- `audit-linear`: Audit the Innodata (`INN`) Linear team board for missing overviews and blockers.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TextIO

from dov_bot.analytics import (
    DovAnalyticsStore,
    load_upstream_artbot_pin,
    seed_default_analytics,
)
from dov_bot.bear_alarm import (
    BearSignalInput,
    evaluate_bear_urgency,
    render_bear_help_page,
)
from dov_bot.linear_sync import (
    HttpTransport,
    LinearOverviewManager,
    default_linear_snapshot,
)


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser for `dov-bot`."""
    parser = argparse.ArgumentParser(
        prog="dov-bot",
        description=(
            "Dov-Bot (Custom ArtBOT): Dov (The Bear) — Google L6 Technical Program Manager, "
            "Linear Board Auditor, Velocity Forecaster, and 0-to-5 Bear Alarm Protocol."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    upstream = subparsers.add_parser(
        "upstream-status",
        help="Show pinned upstream ArtBOT release tag, commit hash, and public API allowlist.",
    )
    upstream.add_argument(
        "--pin-path",
        default="",
        help="Optional override path to UPSTREAM_ARTBOT.json.",
    )
    upstream.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON output.",
    )

    help_cmd = subparsers.add_parser(
        "help-page",
        help="Render the 0-to-5 Bear Alarm Urgency Protocol help page (BEAR_ALARM_HELP.md).",
    )
    help_cmd.add_argument(
        "--output",
        default="",
        help="Optional file path to write the rendered help page markdown.",
    )

    bear_cmd = subparsers.add_parser(
        "bear-check",
        help="Evaluate delivery & infrastructure signals on the 0-to-5 Bear Alarm scale.",
    )
    bear_cmd.add_argument("--untracked", type=int, default=0, help="Untracked workstreams count.")
    bear_cmd.add_argument("--stale", type=int, default=0, help="Stale (>24h) in-progress count.")
    bear_cmd.add_argument(
        "--missing-overviews", type=int, default=0, help="Projects missing overview docs."
    )
    bear_cmd.add_argument("--blockers", type=int, default=0, help="Active blockers count.")
    bear_cmd.add_argument("--unowned-p0-p1", type=int, default=0, help="Unowned P0/P1 issues.")
    bear_cmd.add_argument("--broken-ci", type=int, default=0, help="Broken CI pipeline count.")
    bear_cmd.add_argument(
        "--five-alarm",
        action="store_true",
        help="Trigger 5-ALARM FIRE (critical production/delivery outage).",
    )
    bear_cmd.add_argument(
        "--infra-anomaly",
        default="",
        help="Optional GCP VM or infrastructure service anomaly for @rox-bot peer escalation.",
    )
    bear_cmd.add_argument("--summary", default="", help="Optional context summary.")
    bear_cmd.add_argument("--issue-id", default="INN-235", help="Associated Linear issue ID.")
    bear_cmd.add_argument("--json", action="store_true", help="Emit JSON output.")

    vel_cmd = subparsers.add_parser(
        "velocity-report",
        help="Generate repository coding-style, cycle-time velocity, and epic ETA report.",
    )
    vel_cmd.add_argument(
        "--db",
        default=":memory:",
        help="SQLite database path (default: in-memory).",
    )
    vel_cmd.add_argument(
        "--seed",
        action="store_true",
        help="Seed baseline Innodata ArtBOT ecosystem metrics before reporting.",
    )
    vel_cmd.add_argument(
        "--epic",
        default="",
        help="Optional epic ID (e.g. INN-235) for deterministic ETA forecasting.",
    )
    vel_cmd.add_argument("--json", action="store_true", help="Emit JSON output.")

    linear_cmd = subparsers.add_parser(
        "audit-linear",
        help="Audit the Innodata (INN) Linear team board and active workstreams.",
    )
    linear_cmd.add_argument(
        "--live",
        action="store_true",
        help="Fetch live snapshot from Linear GraphQL API using LINEAR_API_KEY.",
    )
    linear_cmd.add_argument(
        "--api-key",
        default="",
        help="Explicit Linear API key (overrides LINEAR_API_KEY environment variable).",
    )
    linear_cmd.add_argument(
        "--workstream",
        action="append",
        default=[],
        help="Active local workstream name to verify against the Linear board (repeatable).",
    )
    linear_cmd.add_argument("--json", action="store_true", help="Emit JSON output.")

    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    transport: HttpTransport | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    """Execute the `dov-bot` CLI and return an exit status code."""
    env = os.environ if environ is None else environ
    out = sys.stdout if stdout is None else stdout
    err = sys.stderr if stderr is None else stderr

    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.command == "upstream-status":
        pin_path = Path(args.pin_path) if args.pin_path else None
        pin = load_upstream_artbot_pin(pin_path)
        if args.json:
            out.write(json.dumps(pin, indent=2, sort_keys=True) + "\n")
        else:
            allowlist = pin.get("public_api_allowlist", [])
            out.write(
                f"Upstream Repo: {pin.get('upstream_repo')}\n"
                f"Upstream Tag: {pin.get('upstream_tag')}\n"
                f"Upstream Commit: {pin.get('upstream_commit')}\n"
                f"Public API Symbols ({len(allowlist)}): {', '.join(allowlist)}\n"
            )
        return 0

    if args.command == "help-page":
        content = render_bear_help_page()
        if args.output:
            target = Path(args.output)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        out.write(content)
        return 0

    if args.command == "bear-check":
        infra = args.infra_anomaly.strip() or None
        signal = BearSignalInput(
            untracked_workstreams=args.untracked,
            stale_in_progress_count=args.stale,
            missing_overviews_count=args.missing_overviews,
            active_blockers_count=args.blockers,
            unowned_p0_p1_count=args.unowned_p0_p1,
            broken_ci_pipelines=args.broken_ci,
            production_outage_or_5_alarm=bool(args.five_alarm),
            infra_vm_anomaly=infra,
            summary=args.summary,
        )
        assessment = evaluate_bear_urgency(signal, issue_id=args.issue_id)
        if args.json:
            out.write(json.dumps(dataclasses.asdict(assessment), indent=2, sort_keys=True) + "\n")
        else:
            out.write(assessment.formatted_message + "\n")
        return 0

    if args.command == "velocity-report":
        store = DovAnalyticsStore(args.db)
        try:
            if args.seed:
                seed_default_analytics(store)
            epic_id = args.epic.strip() or None
            if args.json:
                summary = store.compute_velocity_summary()
                payload: dict[str, object] = {
                    "profiles": [dataclasses.asdict(p) for p in store.list_coding_style_profiles()],
                    "velocity_summary": dataclasses.asdict(summary),
                }
                if epic_id is not None:
                    payload["epic_forecast"] = dataclasses.asdict(store.forecast_epic_eta(epic_id))
                out.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
            else:
                out.write(store.render_velocity_report_markdown(epic_id=epic_id))
        finally:
            store.close()
        return 0

    # args.command == "audit-linear"
    api_key = (args.api_key or env.get("LINEAR_API_KEY", "")).strip()
    manager = LinearOverviewManager(api_key=api_key, transport=transport)
    if args.live:
        if not api_key:
            err.write("error: --live requires LINEAR_API_KEY or --api-key\n")
            return 2
        projects, members, issues = manager.fetch_team_snapshot()
    else:
        projects, members, issues = default_linear_snapshot()

    report = manager.audit_board(
        projects=projects,
        members=members,
        issues=issues,
        active_local_workstreams=args.workstream,
    )
    if args.json:
        out.write(json.dumps(dataclasses.asdict(report), indent=2, sort_keys=True) + "\n")
    else:
        out.write(manager.render_team_overview_digest(report))
    return 0


if __name__ == "__main__":  # pragma: no cover - module entrypoint
    raise SystemExit(main())
