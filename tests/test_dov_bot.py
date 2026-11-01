"""
Deterministic 100%-coverage unit tests for `dov_bot` (`analytics`, `bear_alarm`, `linear_sync`).
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from dov_bot import (
    BEAR_EMOJI,
    INNODATA_TEAM_ID,
    INNODATA_TEAM_KEY,
    BearSignalInput,
    CodingStyleProfile,
    DovAnalyticsStore,
    IssueCycleRecord,
    LinearIssue,
    LinearOverviewManager,
    UrllibHttpTransport,
    __version__,
    default_linear_snapshot,
    default_repo_root,
    default_upstream_pin_path,
    discover_default_repos,
    evaluate_bear_urgency,
    extract_beads_id,
    format_rox_bot_handoff,
    harvest_beads_jsonl,
    harvest_git_repo_profile,
    ingest_rox_bot_anomaly,
    linear_issue_to_cycle_record,
    load_upstream_artbot_pin,
    main,
    render_bear_help_page,
    seed_default_analytics,
)
from tests.fakes import FakeHttpTransport


def test_package_version_and_upstream_pin(tmp_path: Path) -> None:
    assert __version__ == "0.1.0"
    root = default_repo_root()
    assert (root / "UPSTREAM_ARTBOT.json").is_file()
    assert default_upstream_pin_path() == root / "UPSTREAM_ARTBOT.json"
    assert default_upstream_pin_path(tmp_path) == tmp_path / "UPSTREAM_ARTBOT.json"

    pin = load_upstream_artbot_pin()
    assert pin["upstream_tag"] == "v0.1.0-artbot"
    assert pin["upstream_commit"] == "e28cf26c2b71e4f081ce17f3815fae31375a98d3"

    custom_pin = tmp_path / "custom_pin.json"
    custom_pin.write_text('{"upstream_tag": "v0.1.0-artbot"}', encoding="utf-8")
    assert load_upstream_artbot_pin(custom_pin)["upstream_tag"] == "v0.1.0-artbot"


def test_coding_style_profile_properties_and_sqlite_roundtrip(tmp_path: Path) -> None:
    db_file = tmp_path / "nested" / "dov_analytics.sqlite3"
    store = DovAnalyticsStore(db_file)
    try:
        assert store.get_coding_style_profile("missing/repo") is None

        compliant = CodingStyleProfile(
            repo_name="InnodataAgenticResearch/dov-bot",
            recorded_at="2026-11-01T00:00:00Z",
            avg_commit_lines=120.0,
            test_to_code_ratio=1.5,
            di_fakes_count=4,
            mock_usage_count=0,
            avg_pr_turnaround_hours=1.0,
            scaffolding_commits_per_day=10.0,
            iteration_commits_per_day=5.0,
        )
        assert compliant.is_di_compliant is True
        assert compliant.scaffolding_to_iteration_ratio == 2.0

        non_compliant = CodingStyleProfile(
            repo_name="legacy/mock-heavy",
            recorded_at="2026-11-01T00:00:00Z",
            avg_commit_lines=450.0,
            test_to_code_ratio=0.4,
            di_fakes_count=0,
            mock_usage_count=3,
            avg_pr_turnaround_hours=18.0,
            scaffolding_commits_per_day=2.0,
            iteration_commits_per_day=0.0,
        )
        assert non_compliant.is_di_compliant is False
        assert non_compliant.scaffolding_to_iteration_ratio == 0.0

        store.upsert_coding_style_profile(compliant)
        store.upsert_coding_style_profile(non_compliant)

        loaded = store.get_coding_style_profile("InnodataAgenticResearch/dov-bot")
        assert loaded == compliant
        all_profiles = store.list_coding_style_profiles()
        assert len(all_profiles) == 2
    finally:
        store.close()


def test_issue_cycle_records_velocity_and_epic_forecast() -> None:
    store = DovAnalyticsStore(":memory:")
    try:
        assert store.get_issue_record("INN-999") is None

        # Empty epic forecast
        empty_eta = store.forecast_epic_eta("INN-EMPTY")
        assert empty_eta.remaining_issues == 0
        assert empty_eta.confidence == "HIGH"

        # Seed default records and add edge-case records
        seed_default_analytics(store)
        closed_without_in_progress = IssueCycleRecord(
            issue_id="INN-239",
            source="linear",
            title="Direct close without in_progress timestamp",
            priority="P2",
            phase="verification",
            status="closed",
            opened_at="2026-11-01T00:00:00Z",
            in_progress_at=None,
            closed_at="2026-11-01T03:00:00Z",
            epic_id="INN-235",
            owner=None,
        )
        store.upsert_issue_record(closed_without_in_progress)
        assert closed_without_in_progress.lead_time_hours == 3.0
        assert closed_without_in_progress.active_cycle_hours == 3.0

        open_p4 = IssueCycleRecord(
            issue_id="INN-240",
            source="linear",
            title="Unscheduled P4 task",
            priority="P4",
            phase="rollout",
            status="open",
            opened_at="2026-11-01T00:00:00Z",
            epic_id="EPIC-LOW",
        )
        store.upsert_issue_record(open_p4)
        assert open_p4.lead_time_hours is None
        assert open_p4.active_cycle_hours is None

        fetched = store.get_issue_record("INN-239")
        assert fetched == closed_without_in_progress

        # Filter combinations
        assert len(store.list_issue_records(status="closed")) == 3
        assert len(store.list_issue_records(priority="P1")) == 2
        assert len(store.list_issue_records(epic_id="INN-235")) == 5

        summary = store.compute_velocity_summary(observation_days=7.0)
        assert summary.total_issues == 6
        assert summary.closed_issues == 3
        assert summary.in_progress_issues == 1
        assert summary.open_issues == 2
        assert summary.avg_cycle_hours_by_priority["P0"] == 2.5
        assert summary.avg_cycle_hours_by_priority["P1"] == 2.0
        assert summary.avg_cycle_hours_by_priority["P2"] == 3.0
        assert summary.avg_cycle_hours_by_priority["P4"] == 0.0

        # High confidence forecast (all remaining items in INN-235 have P0/P1 historical avg)
        high_eta = store.forecast_epic_eta("INN-235")
        assert high_eta.remaining_issues == 2
        assert high_eta.confidence == "HIGH"
        assert high_eta.estimated_remaining_hours == 4.5

        # Low confidence forecast (EPIC-LOW has only P4 with 0 historical avg)
        low_eta = store.forecast_epic_eta("EPIC-LOW", default_issue_hours=4.0)
        assert low_eta.remaining_issues == 1
        assert low_eta.confidence == "LOW"
        assert low_eta.estimated_remaining_hours == 4.0

        # Medium confidence forecast (1 item with historical avg, 1 item without -> 50% hit ratio)
        store.upsert_issue_record(
            IssueCycleRecord(
                issue_id="INN-241",
                source="linear",
                title="P1 task in EPIC-LOW",
                priority="P1",
                phase="rollout",
                status="open",
                opened_at="2026-11-01T01:00:00Z",
                epic_id="EPIC-LOW",
            )
        )
        med_eta = store.forecast_epic_eta("EPIC-LOW")
        assert med_eta.remaining_issues == 2
        assert med_eta.confidence == "MEDIUM"

        # Add a non-compliant profile and render markdown both with and without epic_id
        store.upsert_coding_style_profile(
            CodingStyleProfile(
                repo_name="experimental/non-di",
                recorded_at="2026-11-01T03:00:00Z",
                avg_commit_lines=200.0,
                test_to_code_ratio=0.8,
                di_fakes_count=0,
                mock_usage_count=2,
                avg_pr_turnaround_hours=6.0,
                scaffolding_commits_per_day=3.0,
                iteration_commits_per_day=2.0,
            )
        )
        md_no_epic = store.render_velocity_report_markdown()
        assert "Dov-Bot TPM Engineering Velocity" in md_no_epic
        assert "| `experimental/non-di` |" in md_no_epic
        assert "NO |" in md_no_epic
        assert "Deterministic Epic ETA Forecast" not in md_no_epic

        md_with_epic = store.render_velocity_report_markdown(epic_id="INN-235")
        assert "Deterministic Epic ETA Forecast (`INN-235`)" in md_with_epic
    finally:
        store.close()


def test_bear_alarm_0_to_5_protocol_and_rox_bot_coordination() -> None:
    # Level 0: zero bear emojis anywhere in text
    a0 = evaluate_bear_urgency(BearSignalInput())
    assert a0.level == 0
    assert a0.emoji_prefix == ""
    assert BEAR_EMOJI not in a0.formatted_message
    assert a0.rox_bot_handoff is None

    # Level 1: untracked workstream
    a1 = evaluate_bear_urgency(BearSignalInput(untracked_workstreams=1, summary="new repo"))
    assert a1.level == 1
    assert a1.emoji_prefix == BEAR_EMOJI
    assert "(new repo)" in a1.formatted_message

    # Level 2: stale in-progress & missing overviews
    a2_stale = evaluate_bear_urgency(BearSignalInput(stale_in_progress_count=2))
    assert a2_stale.level == 2
    assert a2_stale.emoji_prefix == BEAR_EMOJI * 2
    a2_missing = evaluate_bear_urgency(BearSignalInput(missing_overviews_count=1))
    assert a2_missing.level == 2

    # Level 3: active blocker, unowned P0/P1, and infra anomaly
    a3 = evaluate_bear_urgency(
        BearSignalInput(
            active_blockers_count=1,
            unowned_p0_p1_count=1,
            infra_vm_anomaly="gcp-vm-makor",
        )
    )
    assert a3.level == 3
    assert a3.emoji_prefix == BEAR_EMOJI * 3
    assert a3.rox_bot_handoff is not None
    assert "@rox-bot (@ops-bot)" in a3.rox_bot_handoff

    # Level 3 without infra anomaly
    a3_no_infra = evaluate_bear_urgency(BearSignalInput(active_blockers_count=1))
    assert a3_no_infra.level == 3
    assert a3_no_infra.rox_bot_handoff is None

    # Level 4: broken CI
    a4 = evaluate_bear_urgency(BearSignalInput(broken_ci_pipelines=1))
    assert a4.level == 4
    assert a4.emoji_prefix == BEAR_EMOJI * 4

    # Level 5: 5-ALARM FIRE
    a5 = evaluate_bear_urgency(
        BearSignalInput(
            production_outage_or_5_alarm=True,
            infra_vm_anomaly="teams-bridge-prod",
            summary="bridge down",
        )
    )
    assert a5.level == 5
    assert a5.emoji_prefix == BEAR_EMOJI * 5
    assert "5-ALARM FIRE!" in a5.formatted_message
    assert a5.rox_bot_handoff is not None
    assert "bridge down" in a5.rox_bot_handoff

    # Direct format_rox_bot_handoff without detail
    handoff_plain = format_rox_bot_handoff(2, vm_or_service="vm-test")
    assert handoff_plain.startswith(BEAR_EMOJI * 3)

    # Ingest @rox-bot anomalies across all severity levels
    r_warn = ingest_rox_bot_anomaly(
        service_name="vm-1",
        severity="warning",
        detail="CPU 82%",
    )
    assert r_warn.level == 2

    r_crit = ingest_rox_bot_anomaly(
        service_name="vm-1",
        severity="critical",
        detail="Disk 97%",
        affected_epics=("INN-235", "INN-240"),
    )
    assert r_crit.level == 4
    assert "INN-235, INN-240" in r_crit.formatted_message

    r_outage = ingest_rox_bot_anomaly(
        service_name="vm-1",
        severity="outage",
        detail="Kernel panic",
    )
    assert r_outage.level == 5

    r_other = ingest_rox_bot_anomaly(
        service_name="vm-1",
        severity="degraded",
        detail="Packet loss",
    )
    assert r_other.level == 3

    # Verify BEAR_ALARM_HELP.md on disk matches render_bear_help_page()
    help_md = render_bear_help_page()
    disk_md = (default_repo_root() / "BEAR_ALARM_HELP.md").read_text(encoding="utf-8")
    assert help_md == disk_md


def test_linear_overview_manager_graphql_and_audit() -> None:
    fake = FakeHttpTransport()
    # Test FakeHttpTransport default empty queue paths
    assert fake.get("https://example.com", headers={}, timeout=1.0).status_code == 200
    assert (
        fake.post_json("https://example.com", payload={}, headers={}, timeout=1.0).status_code
        == 200
    )
    fake.queue_get_response(200, '{"ok": true}')
    assert fake.get("https://example.com", headers={}, timeout=1.0).json() == {"ok": True}

    # Default transport instantiation
    default_mgr = LinearOverviewManager()
    assert isinstance(default_mgr.transport, UrllibHttpTransport)
    assert "Authorization" not in default_mgr._headers()

    mgr = LinearOverviewManager(api_key="lin_api_fake_token", transport=fake)
    assert mgr.team_key == INNODATA_TEAM_KEY
    assert mgr.team_id == INNODATA_TEAM_ID

    # 1. HTTP 500 error in fetch_team_snapshot
    fake.queue_post_response(500, "Internal Server Error")
    with pytest.raises(RuntimeError, match="HTTP 500"):
        mgr.fetch_team_snapshot()

    # 2. GraphQL errors array in fetch_team_snapshot
    fake.queue_post_response(200, json.dumps({"errors": [{"message": "Unauthorized"}]}))
    with pytest.raises(RuntimeError, match="Linear GraphQL returned errors"):
        mgr.fetch_team_snapshot()

    # 3. Valid GraphQL snapshot response
    graphql_payload = {
        "data": {
            "team": {
                "id": INNODATA_TEAM_ID,
                "key": INNODATA_TEAM_KEY,
                "members": {
                    "nodes": [
                        {
                            "id": "m1",
                            "name": "Danny Rosen",
                            "email": "drosen@innodata.com",
                            "active": True,
                        }
                    ]
                },
                "projects": {
                    "nodes": [
                        {
                            "id": "p1",
                            "name": "ArtBOT Fleet",
                            "state": "started",
                            "description": "",
                            "updatedAt": "2026-11-01T00:00:00Z",
                            "lead": None,
                        },
                        {
                            "id": "p2",
                            "name": "Dov-Bot TPM",
                            "state": "started",
                            "description": "Full TPM spec.",
                            "updatedAt": "2026-11-01T01:00:00Z",
                            "lead": {"name": "Danny Rosen"},
                        },
                    ]
                },
                "issues": {
                    "nodes": [
                        {
                            "identifier": "INN-235",
                            "title": "Unowned urgent issue",
                            "priority": 1,
                            "state": {"name": "In Progress"},
                            "assignee": None,
                            "project": None,
                            "hoursSinceUpdate": 30.0,
                        },
                        {
                            "identifier": "INN-236",
                            "title": "Completed issue",
                            "priority": 2,
                            "state": {"name": "Done"},
                            "assignee": {"name": "Danny Rosen"},
                            "project": {"name": "Dov-Bot TPM"},
                            "beadsId": "makor-80w.6",
                            "hoursSinceUpdate": 48.0,
                        },
                        {
                            "identifier": "INN-242",
                            "title": "Medium priority todo",
                            "priority": 3,
                            "state": {"name": "Todo"},
                            "assignee": None,
                            "project": {"name": "Dov-Bot TPM"},
                            "beadsId": "makor-80w.12",
                            "hoursSinceUpdate": 2.0,
                        },
                    ]
                },
            }
        }
    }
    fake.queue_post_response(200, json.dumps(graphql_payload))
    projects, members, issues = mgr.fetch_team_snapshot()
    assert len(projects) == 2
    assert len(members) == 1
    assert len(issues) == 3

    # Audit board with missing overview, untracked workstream, unowned P0, and stale in-progress
    report = mgr.audit_board(
        projects=projects,
        members=members,
        issues=issues,
        active_local_workstreams=["", "dov-bot", "mystery-untracked-repo"],
        stale_threshold_hours=24.0,
    )
    assert report.max_bear_level == 3
    categories = {f.category for f in report.findings}
    assert categories == {
        "missing_project_overview",
        "untracked_active_work",
        "missing_beads_link",
        "unowned_high_priority",
        "stale_in_progress",
    }
    digest_dirty = mgr.render_team_overview_digest(report)
    assert BEAR_EMOJI * 3 in digest_dirty
    assert "mystery-untracked-repo" in digest_dirty

    # Clean audit board (0 findings -> 0 bears)
    def_proj, def_mem, def_issues = default_linear_snapshot()
    clean_report = default_mgr.audit_board(
        projects=def_proj,
        members=def_mem,
        issues=def_issues,
        active_local_workstreams=["dov-bot"],
    )
    assert clean_report.max_bear_level == 0
    assert len(clean_report.findings) == 0
    digest_clean = default_mgr.render_team_overview_digest(clean_report)
    assert BEAR_EMOJI not in digest_clean
    assert "100% accounted for on the board" in digest_clean

    # update_project_overview success and error paths
    fake.queue_post_response(200, json.dumps({"data": {"projectUpdate": {"success": True}}}))
    assert mgr.update_project_overview("p1", "Updated overview") is True

    fake.queue_post_response(403, "Forbidden")
    with pytest.raises(RuntimeError, match="HTTP 403"):
        mgr.update_project_overview("p1", "Updated overview")


def test_cli_all_subcommands(tmp_path: Path) -> None:
    # 1. upstream-status text & JSON
    out = io.StringIO()
    assert main(["upstream-status"], stdout=out) == 0
    assert "v0.1.0-artbot" in out.getvalue()

    out_json = io.StringIO()
    assert main(["upstream-status", "--json"], stdout=out_json) == 0
    assert json.loads(out_json.getvalue())["upstream_tag"] == "v0.1.0-artbot"

    # 2. help-page stdout & --output file
    help_file = tmp_path / "docs" / "BEAR_ALARM_HELP.md"
    out_help = io.StringIO()
    assert main(["help-page", "--output", str(help_file)], stdout=out_help) == 0
    assert help_file.is_file()
    assert "5-ALARM FIRE!" in out_help.getvalue()

    out_help_stdout_only = io.StringIO()
    assert main(["help-page"], stdout=out_help_stdout_only) == 0
    assert "0-to-5 Bear Alarm" in out_help_stdout_only.getvalue()

    # 3. bear-check text & JSON
    out_bear = io.StringIO()
    assert (
        main(
            [
                "bear-check",
                "--blockers",
                "1",
                "--infra-anomaly",
                "gcp-vm-makor",
                "--summary",
                "disk pressure",
            ],
            stdout=out_bear,
        )
        == 0
    )
    assert "@rox-bot" in out_bear.getvalue()

    out_bear_json = io.StringIO()
    assert main(["bear-check", "--json"], stdout=out_bear_json) == 0
    assert json.loads(out_bear_json.getvalue())["level"] == 0

    # 4. velocity-report text & JSON (with and without --epic and --seed)
    out_vel = io.StringIO()
    assert main(["velocity-report", "--seed", "--epic", "INN-235"], stdout=out_vel) == 0
    assert "INN-235" in out_vel.getvalue()

    out_vel_json = io.StringIO()
    assert (
        main(
            ["velocity-report", "--seed", "--epic", "INN-235", "--json"],
            stdout=out_vel_json,
        )
        == 0
    )
    vel_data = json.loads(out_vel_json.getvalue())
    assert "epic_forecast" in vel_data

    out_vel_no_epic_json = io.StringIO()
    assert main(["velocity-report", "--json"], stdout=out_vel_no_epic_json) == 0
    assert "epic_forecast" not in json.loads(out_vel_no_epic_json.getvalue())

    # 5. audit-linear offline, --json, and --live (error & success)
    out_lin = io.StringIO()
    assert main(["audit-linear", "--workstream", "dov-bot"], stdout=out_lin) == 0
    assert "Innodata (INN) Linear Team" in out_lin.getvalue()

    out_lin_json = io.StringIO()
    assert main(["audit-linear", "--json"], stdout=out_lin_json) == 0
    assert json.loads(out_lin_json.getvalue())["team_key"] == "INN"

    err_live = io.StringIO()
    assert main(["audit-linear", "--live"], environ={}, stderr=err_live) == 2
    assert "requires LINEAR_API_KEY" in err_live.getvalue()

    fake = FakeHttpTransport()
    fake.queue_post_response(
        200,
        json.dumps(
            {
                "data": {
                    "team": {
                        "id": INNODATA_TEAM_ID,
                        "key": INNODATA_TEAM_KEY,
                        "members": {"nodes": []},
                        "projects": {"nodes": []},
                        "issues": {"nodes": []},
                    }
                }
            }
        ),
    )
    out_live = io.StringIO()
    assert (
        main(
            ["audit-linear", "--live", "--api-key", "lin_key"],
            transport=fake,
            stdout=out_live,
        )
        == 0
    )
    assert "Innodata (INN)" in out_live.getvalue()


def test_harvest_git_repo_beads_and_linear_conversion(tmp_path: Path) -> None:
    # 1. Real git repo harvest on default_repo_root()
    real_profile = harvest_git_repo_profile(default_repo_root())
    assert real_profile.repo_name.endswith("dov-bot")
    assert real_profile.di_fakes_count >= 1
    assert real_profile.mock_usage_count == 0

    # 2. Non-git directory with _run_git_command (covers non-zero git exit fallback)
    non_git_dir = tmp_path / "plain-dir"
    non_git_dir.mkdir()
    plain_profile = harvest_git_repo_profile(non_git_dir, recorded_at="2026-11-01T12:00:00Z")
    assert plain_profile.repo_name == "plain-dir"

    # 3. Synthetic repo covering Rust #[cfg(test)], Starlark, Python, ignored dirs, SSH remote
    synth_repo = tmp_path / "synth-repo"
    (synth_repo / "src").mkdir(parents=True)
    (synth_repo / "tests").mkdir(parents=True)
    (synth_repo / ".venv").mkdir(parents=True)
    (synth_repo / ".beads").mkdir(parents=True)

    (synth_repo / "src" / "app.py").write_text(
        "class Service(Protocol):\n    pass\n",
        encoding="utf-8",
    )
    (synth_repo / "src" / "lib.rs").write_text(
        "pub fn add(a: i32, b: i32) -> i32 { a + b }\n"
        "#[cfg(test)]\n"
        "mod tests {\n    #[test]\n    fn it_works() {}\n}\n",
        encoding="utf-8",
    )
    (synth_repo / "src" / "plain.rs").write_text(
        "pub fn noop() {}\n",
        encoding="utf-8",
    )
    (synth_repo / "tests" / "test_app.py").write_text(
        "import " + "unittest" + ".mock\nclass FakeService:\n    pass\n",
        encoding="utf-8",
    )
    (synth_repo / "tests" / "policy_test.star").write_text(
        "shac.test.context()\n",
        encoding="utf-8",
    )
    (synth_repo / ".venv" / "ignored.py").write_text("x = 1\n", encoding="utf-8")
    (synth_repo / "README.md").write_text("# Synth\n", encoding="utf-8")

    def fake_git_runner(args: object, cwd: Path) -> str:
        cmd = list(args) if isinstance(args, (list, tuple)) else []
        if "remote.origin.url" in cmd:
            return "git@github.com:InnodataAgenticResearch/synth-repo.git"
        return (
            "COMMIT|1700003600|feat: scaffold initial repo\n"
            "120\t30\tsrc/app.py\n"
            "-\t-\tbinary.dat\n"
            "\n"
            "COMMIT|1700000000|fix: tighten validation\n"
            "20\t10\tsrc/lib.rs\n"
        )

    synth_profile = harvest_git_repo_profile(
        synth_repo,
        recorded_at="2026-11-01T12:00:00Z",
        git_runner=fake_git_runner,
    )
    assert synth_profile.repo_name == "InnodataAgenticResearch/synth-repo"
    assert synth_profile.mock_usage_count == 1
    assert synth_profile.di_fakes_count >= 2
    assert synth_profile.avg_commit_lines == 90.0
    assert synth_profile.avg_pr_turnaround_hours == 1.0

    # Single-token remote URL edge case
    single_token_profile = harvest_git_repo_profile(
        non_git_dir,
        recorded_at="2026-11-01T12:00:00Z",
        git_runner=lambda args, cwd: "single-repo.git" if "remote.origin.url" in args else "",
    )
    assert single_token_profile.repo_name == "single-repo"

    # 4. harvest_beads_jsonl (missing file + open/in_progress/closed/blank line)
    assert harvest_beads_jsonl(tmp_path / "does-not-exist.jsonl") == []
    beads_path = synth_repo / ".beads" / "issues.jsonl"
    beads_path.write_text(
        "\n"
        + json.dumps(
            {
                "id": "makor-1.1",
                "title": "Bootstrap Phase 1 repo",
                "priority": 0,
                "status": "closed",
                "created_at": "2026-11-01T00:00:00Z",
                "updated_at": "2026-11-01T02:00:00Z",
                "closed_at": None,
                "parent": None,
                "assignee": "Danny Rosen",
            }
        )
        + "\n"
        + json.dumps(
            {
                "id": "makor-2",
                "title": "Verify coverage gates",
                "priority": 1,
                "status": "in_progress",
                "created_at": "2026-11-01T01:00:00Z",
                "updated_at": "2026-11-01T01:30:00Z",
                "parent": "makor-root",
            }
        )
        + "\n"
        + json.dumps(
            {
                "id": "makor-3",
                "title": "Deploy fleet rollout",
                "priority": 2,
                "status": "open",
                "created_at": "2026-11-01T01:00:00Z",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    bead_records = harvest_beads_jsonl(beads_path)
    assert len(bead_records) == 3
    assert bead_records[0].phase == "scaffolding"
    assert bead_records[0].epic_id == "makor-1"
    assert bead_records[1].phase == "verification"
    assert bead_records[1].status == "in_progress"
    assert bead_records[2].phase == "rollout"
    assert bead_records[2].status == "open"

    # 5. linear_issue_to_cycle_record & extract_beads_id
    assert extract_beads_id("[makor-tq2.3.1] Add fleet") == "makor-tq2.3.1"
    assert extract_beads_id("No bead here") is None

    lin_issue_closed = LinearIssue(
        identifier="INN-200",
        title="Implement core parser",
        state_name="Done",
        priority=2,
        assignee_name="Danny Rosen",
        project_name="Core",
        created_at="2026-11-01T00:00:00Z",
        updated_at="2026-11-01T03:00:00Z",
    )
    lin_closed = linear_issue_to_cycle_record(lin_issue_closed)
    assert lin_closed.status == "closed"
    assert lin_closed.phase == "implementation"
    assert lin_closed.priority == "P1"

    lin_issue_in_prog = LinearIssue(
        identifier="INN-201",
        title="Verify tests",
        state_name="In Review",
        priority=1,
        parent_identifier="INN-200",
        started_at="2026-11-01T01:00:00Z",
    )
    lin_in_prog = linear_issue_to_cycle_record(lin_issue_in_prog)
    assert lin_in_prog.status == "in_progress"
    assert lin_in_prog.epic_id == "INN-200"

    lin_issue_open = LinearIssue(
        identifier="INN-202",
        title="Backlog item",
        state_name="Todo",
        priority=0,
    )
    lin_open = linear_issue_to_cycle_record(lin_issue_open)
    assert lin_open.status == "open"
    assert lin_open.priority == "P4"

    # 6. discover_default_repos & store.sync_live_data
    base_repos = tmp_path / "fleet"
    (base_repos / "dov-bot").mkdir(parents=True)
    discovered = discover_default_repos(base_repos)
    assert discovered == [base_repos / "dov-bot"]
    assert isinstance(discover_default_repos(), list)

    store = DovAnalyticsStore(":memory:")
    try:
        sync_res = store.sync_live_data(
            repo_paths=[synth_repo],
            linear_issues=[lin_issue_closed, lin_issue_in_prog, lin_issue_open],
            linear_projects_count=2,
            recorded_at="2026-11-01T12:00:00Z",
            git_runner=fake_git_runner,
        )
        assert sync_res.repos_synced == ("InnodataAgenticResearch/synth-repo",)
        assert sync_res.beads_records_synced == 3
        assert sync_res.linear_issues_synced == 3
        assert len(store.list_issue_records()) == 6
    finally:
        store.close()


def test_cli_sync_live_and_bear_check_live(tmp_path: Path) -> None:
    repo_dir = tmp_path / "dov-bot"
    repo_dir.mkdir()
    db_file = tmp_path / "live.db"

    # 1. sync-live missing LINEAR_API_KEY without --skip-linear returns 2
    err_sync = io.StringIO()
    assert (
        main(
            ["sync-live", "--db", str(db_file), "--repo", str(repo_dir)],
            environ={},
            stderr=err_sync,
        )
        == 2
    )
    assert "requires LINEAR_API_KEY" in err_sync.getvalue()

    # 2. sync-live --skip-linear (text output)
    out_skip = io.StringIO()
    assert (
        main(
            [
                "sync-live",
                "--db",
                str(db_file),
                "--repo",
                str(repo_dir),
                "--skip-linear",
            ],
            stdout=out_skip,
        )
        == 0
    )
    assert "Synced 1 repositories" in out_skip.getvalue()

    # 3. sync-live with FakeHttpTransport & --json (and default repo discovery)
    fake = FakeHttpTransport()
    fake.queue_post_response(
        200,
        json.dumps(
            {
                "data": {
                    "team": {
                        "id": INNODATA_TEAM_ID,
                        "key": INNODATA_TEAM_KEY,
                        "members": {"nodes": []},
                        "projects": {"nodes": [{"id": "p1", "name": "ArtBOT", "state": "started"}]},
                        "issues": {
                            "nodes": [
                                {
                                    "identifier": "INN-250",
                                    "title": "[makor-c4s.1] Phase 1: Scaffold",
                                    "description": "Linked to makor-c4s.1",
                                    "priority": 1,
                                    "createdAt": "2026-11-01T00:00:00Z",
                                    "startedAt": "2026-11-01T01:00:00Z",
                                    "completedAt": "2026-11-01T02:00:00Z",
                                    "updatedAt": "2026-11-01T02:00:00Z",
                                    "state": {"name": "Done"},
                                    "assignee": {"name": "Danny Rosen"},
                                    "project": {"name": "ArtBOT"},
                                    "parent": {"identifier": "INN-249"},
                                }
                            ]
                        },
                    }
                }
            }
        ),
    )
    out_sync_json = io.StringIO()
    assert (
        main(
            ["sync-live", "--db", str(db_file), "--api-key", "lin_key", "--json"],
            transport=fake,
            stdout=out_sync_json,
        )
        == 0
    )
    sync_payload = json.loads(out_sync_json.getvalue())
    assert sync_payload["linear_issues_synced"] == 1
    assert sync_payload["linear_projects_count"] == 1

    # 4. bear-check --live missing API key returns 2
    err_bear_live = io.StringIO()
    assert main(["bear-check", "--live"], environ={}, stderr=err_bear_live) == 2
    assert "requires LINEAR_API_KEY" in err_bear_live.getvalue()

    # 5. bear-check --live with FakeHttpTransport (default summary and custom summary)
    for extra_args in ([], ["--summary", "Custom live summary"]):
        fake.queue_post_response(
            200,
            json.dumps(
                {
                    "data": {
                        "team": {
                            "id": INNODATA_TEAM_ID,
                            "key": INNODATA_TEAM_KEY,
                            "members": {"nodes": []},
                            "projects": {
                                "nodes": [{"id": "p1", "name": "ArtBOT", "state": "started"}]
                            },
                            "issues": {"nodes": []},
                        }
                    }
                }
            ),
        )
        out_bear_live = io.StringIO()
        assert (
            main(
                ["bear-check", "--live", "--api-key", "lin_key", *extra_args],
                transport=fake,
                stdout=out_bear_live,
            )
            == 0
        )
        assert "Bear(s)" in out_bear_live.getvalue()
