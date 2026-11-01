"""
Isolated SQLite analytics database (`DovAnalyticsStore`) for Dov-Bot (The Bear — Google L6 TPM).

Tracks:
1. Coding-style profiles across repositories (commit granularity, test-to-code ratio, pure
   dependency injection vs. mock usage, PR turnaround, new-project scaffolding velocity vs.
   existing-repo iteration velocity).
2. Beads (`bd`) and Linear (`INN-*`) issue cycle times (`open` -> `in_progress` -> `closed`),
   completion velocity by priority (`P0`–`P4`) and phase, and deterministic ETA forecasting
   for open epics.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

PRIORITY_LEVELS: tuple[str, ...] = ("P0", "P1", "P2", "P3", "P4")


def default_repo_root() -> Path:
    """Return the root directory of the `dov-bot` repository."""
    return Path(__file__).resolve().parents[2]


def default_upstream_pin_path(repo_root: Path | None = None) -> Path:
    """Return the path to `UPSTREAM_ARTBOT.json`."""
    root = default_repo_root() if repo_root is None else repo_root
    return root / "UPSTREAM_ARTBOT.json"


def load_upstream_artbot_pin(path: Path | None = None) -> dict[str, Any]:
    """Load and validate `UPSTREAM_ARTBOT.json`."""
    pin_path = default_upstream_pin_path() if path is None else path
    raw: dict[str, Any] = json.loads(pin_path.read_text(encoding="utf-8"))
    return raw


def _parse_iso_utc(ts: str) -> datetime:
    """Parse an ISO-8601 UTC timestamp string (`YYYY-MM-DDTHH:MM:SSZ` or `+00:00`)."""
    normalized = ts.strip().replace("Z", "+00:00")
    return datetime.fromisoformat(normalized)


@dataclass(frozen=True)
class CodingStyleProfile:
    """Repository coding-style and engineering velocity telemetry profile."""

    repo_name: str
    recorded_at: str
    avg_commit_lines: float
    test_to_code_ratio: float
    di_fakes_count: int
    mock_usage_count: int
    avg_pr_turnaround_hours: float
    scaffolding_commits_per_day: float
    iteration_commits_per_day: float

    @property
    def is_di_compliant(self) -> bool:
        """Return True when the repository uses pure DI fakes and zero `unittest.mock`."""
        return self.mock_usage_count == 0 and self.di_fakes_count > 0

    @property
    def scaffolding_to_iteration_ratio(self) -> float:
        """Return the ratio of new-project scaffolding velocity to iteration velocity."""
        if self.iteration_commits_per_day <= 0.0:
            return 0.0
        return round(self.scaffolding_commits_per_day / self.iteration_commits_per_day, 2)


@dataclass(frozen=True)
class IssueCycleRecord:
    """Cycle-time record for a Linear (`INN-*`) issue or local Beads (`bd`) task."""

    issue_id: str
    source: str
    title: str
    priority: str
    phase: str
    status: str
    opened_at: str
    in_progress_at: str | None = None
    closed_at: str | None = None
    epic_id: str | None = None
    owner: str | None = None

    @property
    def lead_time_hours(self) -> float | None:
        """Return total hours from `opened_at` to `closed_at`, or `None` if not closed."""
        if self.closed_at is None:
            return None
        start = _parse_iso_utc(self.opened_at)
        end = _parse_iso_utc(self.closed_at)
        return round(max(0.0, (end - start).total_seconds() / 3600.0), 2)

    @property
    def active_cycle_hours(self) -> float | None:
        """Return active hours from `in_progress_at` (or `opened_at`) to `closed_at`."""
        if self.closed_at is None:
            return None
        baseline = self.in_progress_at if self.in_progress_at is not None else self.opened_at
        start = _parse_iso_utc(baseline)
        end = _parse_iso_utc(self.closed_at)
        return round(max(0.0, (end - start).total_seconds() / 3600.0), 2)


@dataclass(frozen=True)
class VelocitySummary:
    """Aggregated cycle-time and completion velocity across priorities (`P0`–`P4`) and phases."""

    total_issues: int
    closed_issues: int
    in_progress_issues: int
    open_issues: int
    avg_cycle_hours_by_priority: dict[str, float]
    completed_by_phase: dict[str, int]
    daily_throughput: float


@dataclass(frozen=True)
class EpicEtaForecast:
    """Deterministic completion ETA forecast for an open Linear/Beads epic."""

    epic_id: str
    remaining_issues: int
    estimated_remaining_hours: float
    estimated_completion_days: float
    confidence: str


class DovAnalyticsStore:
    """Isolated SQLite analytics store for coding-style profiles and issue cycle times."""

    def __init__(self, db_path: Path | str = ":memory:") -> None:
        self.db_path = str(db_path)
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        self._conn.close()

    def _init_schema(self) -> None:
        with self._conn:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS coding_style_profiles (
                    repo_name TEXT PRIMARY KEY,
                    recorded_at TEXT NOT NULL,
                    avg_commit_lines REAL NOT NULL,
                    test_to_code_ratio REAL NOT NULL,
                    di_fakes_count INTEGER NOT NULL,
                    mock_usage_count INTEGER NOT NULL,
                    avg_pr_turnaround_hours REAL NOT NULL,
                    scaffolding_commits_per_day REAL NOT NULL,
                    iteration_commits_per_day REAL NOT NULL
                )
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS issue_cycle_records (
                    issue_id TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    title TEXT NOT NULL,
                    priority TEXT NOT NULL,
                    phase TEXT NOT NULL,
                    status TEXT NOT NULL,
                    opened_at TEXT NOT NULL,
                    in_progress_at TEXT,
                    closed_at TEXT,
                    epic_id TEXT,
                    owner TEXT
                )
                """
            )

    def upsert_coding_style_profile(self, profile: CodingStyleProfile) -> None:
        """Insert or update a repository coding-style profile."""
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO coding_style_profiles (
                    repo_name,
                    recorded_at,
                    avg_commit_lines,
                    test_to_code_ratio,
                    di_fakes_count,
                    mock_usage_count,
                    avg_pr_turnaround_hours,
                    scaffolding_commits_per_day,
                    iteration_commits_per_day
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(repo_name) DO UPDATE SET
                    recorded_at = excluded.recorded_at,
                    avg_commit_lines = excluded.avg_commit_lines,
                    test_to_code_ratio = excluded.test_to_code_ratio,
                    di_fakes_count = excluded.di_fakes_count,
                    mock_usage_count = excluded.mock_usage_count,
                    avg_pr_turnaround_hours = excluded.avg_pr_turnaround_hours,
                    scaffolding_commits_per_day = excluded.scaffolding_commits_per_day,
                    iteration_commits_per_day = excluded.iteration_commits_per_day
                """,
                (
                    profile.repo_name,
                    profile.recorded_at,
                    profile.avg_commit_lines,
                    profile.test_to_code_ratio,
                    profile.di_fakes_count,
                    profile.mock_usage_count,
                    profile.avg_pr_turnaround_hours,
                    profile.scaffolding_commits_per_day,
                    profile.iteration_commits_per_day,
                ),
            )

    def get_coding_style_profile(self, repo_name: str) -> CodingStyleProfile | None:
        """Fetch a single repository coding-style profile by `repo_name`."""
        row = self._conn.execute(
            "SELECT * FROM coding_style_profiles WHERE repo_name = ?",
            (repo_name,),
        ).fetchone()
        if row is None:
            return None
        return CodingStyleProfile(
            repo_name=str(row["repo_name"]),
            recorded_at=str(row["recorded_at"]),
            avg_commit_lines=float(row["avg_commit_lines"]),
            test_to_code_ratio=float(row["test_to_code_ratio"]),
            di_fakes_count=int(row["di_fakes_count"]),
            mock_usage_count=int(row["mock_usage_count"]),
            avg_pr_turnaround_hours=float(row["avg_pr_turnaround_hours"]),
            scaffolding_commits_per_day=float(row["scaffolding_commits_per_day"]),
            iteration_commits_per_day=float(row["iteration_commits_per_day"]),
        )

    def list_coding_style_profiles(self) -> list[CodingStyleProfile]:
        """List all tracked repository coding-style profiles ordered by `repo_name`."""
        rows = self._conn.execute(
            "SELECT * FROM coding_style_profiles ORDER BY repo_name ASC"
        ).fetchall()
        return [
            CodingStyleProfile(
                repo_name=str(row["repo_name"]),
                recorded_at=str(row["recorded_at"]),
                avg_commit_lines=float(row["avg_commit_lines"]),
                test_to_code_ratio=float(row["test_to_code_ratio"]),
                di_fakes_count=int(row["di_fakes_count"]),
                mock_usage_count=int(row["mock_usage_count"]),
                avg_pr_turnaround_hours=float(row["avg_pr_turnaround_hours"]),
                scaffolding_commits_per_day=float(row["scaffolding_commits_per_day"]),
                iteration_commits_per_day=float(row["iteration_commits_per_day"]),
            )
            for row in rows
        ]

    def upsert_issue_record(self, record: IssueCycleRecord) -> None:
        """Insert or update a Beads (`bd`) or Linear (`INN-*`) issue cycle record."""
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO issue_cycle_records (
                    issue_id,
                    source,
                    title,
                    priority,
                    phase,
                    status,
                    opened_at,
                    in_progress_at,
                    closed_at,
                    epic_id,
                    owner
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(issue_id) DO UPDATE SET
                    source = excluded.source,
                    title = excluded.title,
                    priority = excluded.priority,
                    phase = excluded.phase,
                    status = excluded.status,
                    opened_at = excluded.opened_at,
                    in_progress_at = excluded.in_progress_at,
                    closed_at = excluded.closed_at,
                    epic_id = excluded.epic_id,
                    owner = excluded.owner
                """,
                (
                    record.issue_id,
                    record.source,
                    record.title,
                    record.priority,
                    record.phase,
                    record.status,
                    record.opened_at,
                    record.in_progress_at,
                    record.closed_at,
                    record.epic_id,
                    record.owner,
                ),
            )

    def get_issue_record(self, issue_id: str) -> IssueCycleRecord | None:
        """Fetch a single issue cycle record by `issue_id`."""
        row = self._conn.execute(
            "SELECT * FROM issue_cycle_records WHERE issue_id = ?",
            (issue_id,),
        ).fetchone()
        if row is None:
            return None
        return self._row_to_issue(row)

    def list_issue_records(
        self,
        *,
        status: str | None = None,
        priority: str | None = None,
        epic_id: str | None = None,
    ) -> list[IssueCycleRecord]:
        """List issue cycle records with optional status, priority, and epic filters."""
        clauses: list[str] = []
        params: list[str] = []
        if status is not None:
            clauses.append("status = ?")
            params.append(status)
        if priority is not None:
            clauses.append("priority = ?")
            params.append(priority)
        if epic_id is not None:
            clauses.append("epic_id = ?")
            params.append(epic_id)

        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self._conn.execute(
            f"SELECT * FROM issue_cycle_records {where_sql} ORDER BY issue_id ASC",
            tuple(params),
        ).fetchall()
        return [self._row_to_issue(row) for row in rows]

    @staticmethod
    def _row_to_issue(row: sqlite3.Row) -> IssueCycleRecord:
        return IssueCycleRecord(
            issue_id=str(row["issue_id"]),
            source=str(row["source"]),
            title=str(row["title"]),
            priority=str(row["priority"]),
            phase=str(row["phase"]),
            status=str(row["status"]),
            opened_at=str(row["opened_at"]),
            in_progress_at=str(row["in_progress_at"])
            if row["in_progress_at"] is not None
            else None,
            closed_at=str(row["closed_at"]) if row["closed_at"] is not None else None,
            epic_id=str(row["epic_id"]) if row["epic_id"] is not None else None,
            owner=str(row["owner"]) if row["owner"] is not None else None,
        )

    def compute_velocity_summary(self, *, observation_days: float = 7.0) -> VelocitySummary:
        """Compute completion velocity by priority (`P0`–`P4`) and phase."""
        records = self.list_issue_records()
        closed_count = sum(1 for r in records if r.status == "closed")
        in_progress_count = sum(1 for r in records if r.status == "in_progress")
        open_count = sum(1 for r in records if r.status == "open")

        avg_by_priority: dict[str, float] = {}
        for prio in PRIORITY_LEVELS:
            durations = [
                r.active_cycle_hours
                for r in records
                if r.priority == prio and r.active_cycle_hours is not None
            ]
            avg_by_priority[prio] = round(sum(durations) / len(durations), 2) if durations else 0.0

        completed_by_phase: dict[str, int] = {}
        for rec in records:
            if rec.status == "closed":
                completed_by_phase[rec.phase] = completed_by_phase.get(rec.phase, 0) + 1

        window = max(1.0, observation_days)
        throughput = round(closed_count / window, 2)
        return VelocitySummary(
            total_issues=len(records),
            closed_issues=closed_count,
            in_progress_issues=in_progress_count,
            open_issues=open_count,
            avg_cycle_hours_by_priority=avg_by_priority,
            completed_by_phase=completed_by_phase,
            daily_throughput=throughput,
        )

    def forecast_epic_eta(
        self,
        epic_id: str,
        *,
        default_issue_hours: float = 4.0,
        daily_focus_hours: float = 8.0,
    ) -> EpicEtaForecast:
        """
        Compute a deterministic ETA forecast for an open epic using historical priority cycle times.
        """
        summary = self.compute_velocity_summary()
        epic_issues = self.list_issue_records(epic_id=epic_id)
        remaining = [r for r in epic_issues if r.status != "closed"]

        if not remaining:
            return EpicEtaForecast(
                epic_id=epic_id,
                remaining_issues=0,
                estimated_remaining_hours=0.0,
                estimated_completion_days=0.0,
                confidence="HIGH",
            )

        total_hours = 0.0
        historical_hits = 0
        for item in remaining:
            hist = summary.avg_cycle_hours_by_priority.get(item.priority, 0.0)
            if hist > 0.0:
                total_hours += hist
                historical_hits += 1
            else:
                total_hours += default_issue_hours

        est_hours = round(total_hours, 2)
        focus = max(1.0, daily_focus_hours)
        est_days = round(est_hours / focus, 2)

        hit_ratio = historical_hits / len(remaining)
        if hit_ratio >= 0.75:
            confidence = "HIGH"
        elif hit_ratio >= 0.25:
            confidence = "MEDIUM"
        else:
            confidence = "LOW"

        return EpicEtaForecast(
            epic_id=epic_id,
            remaining_issues=len(remaining),
            estimated_remaining_hours=est_hours,
            estimated_completion_days=est_days,
            confidence=confidence,
        )

    def render_velocity_report_markdown(self, *, epic_id: str | None = None) -> str:
        """Render a markdown digest of coding-style profiles, cycle velocity, and epic ETA."""
        profiles = self.list_coding_style_profiles()
        summary = self.compute_velocity_summary()
        header_row = (
            "| Repository | Avg Commit Lines | Test:Code Ratio | DI Fakes | Mocks "
            "| PR Turnaround (h) | Scaffolding/Day | Iteration/Day | DI Compliant |"
        )
        lines = [
            "# Dov-Bot TPM Engineering Velocity & Coding-Style Report",
            "",
            "## 1. Repository Coding-Style & DI Compliance Profiles",
            "",
            header_row,
            "| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | :--- |",
        ]
        for prof in profiles:
            compliant = "YES" if prof.is_di_compliant else "NO"
            lines.append(
                f"| `{prof.repo_name}` | {prof.avg_commit_lines:.1f} "
                f"| {prof.test_to_code_ratio:.2f} | {prof.di_fakes_count} "
                f"| {prof.mock_usage_count} | {prof.avg_pr_turnaround_hours:.1f} "
                f"| {prof.scaffolding_commits_per_day:.1f} "
                f"| {prof.iteration_commits_per_day:.1f} | {compliant} |"
            )

        lines.extend(
            [
                "",
                "## 2. Issue & Bead Cycle-Time Velocity (`P0`–`P4`)",
                "",
                f"- **Total Tracked Items:** `{summary.total_issues}` "
                f"(`{summary.closed_issues}` closed, "
                f"`{summary.in_progress_issues}` in progress, "
                f"`{summary.open_issues}` open)",
                f"- **Daily Throughput:** `{summary.daily_throughput:.2f}` items/day",
                "",
                "| Priority | Avg Active Cycle Time (Hours) |",
                "| :--- | ---: |",
            ]
        )
        for prio in PRIORITY_LEVELS:
            lines.append(f"| `{prio}` | {summary.avg_cycle_hours_by_priority[prio]:.2f} |")

        if epic_id is not None:
            forecast = self.forecast_epic_eta(epic_id)
            rem_hrs = forecast.estimated_remaining_hours
            rem_days = forecast.estimated_completion_days
            lines.extend(
                [
                    "",
                    f"## 3. Deterministic Epic ETA Forecast (`{forecast.epic_id}`)",
                    "",
                    f"- **Remaining Open Items:** `{forecast.remaining_issues}`",
                    f"- **Estimated Remaining Effort:** `{rem_hrs:.2f}` hours",
                    f"- **Estimated Completion Window:** `{rem_days:.2f}` days",
                    f"- **Forecast Confidence:** `{forecast.confidence}`",
                ]
            )

        return "\n".join(lines) + "\n"


def seed_default_analytics(store: DovAnalyticsStore) -> None:
    """Populate `store` with baseline Innodata ArtBOT ecosystem coding-style and issue records."""
    for profile in (
        CodingStyleProfile(
            repo_name="InnodataAgenticResearch/artbot",
            recorded_at="2026-11-01T00:00:00Z",
            avg_commit_lines=145.0,
            test_to_code_ratio=1.35,
            di_fakes_count=6,
            mock_usage_count=0,
            avg_pr_turnaround_hours=1.8,
            scaffolding_commits_per_day=8.5,
            iteration_commits_per_day=4.2,
        ),
        CodingStyleProfile(
            repo_name="InnodataAgenticResearch/marketing-bot",
            recorded_at="2026-11-01T01:00:00Z",
            avg_commit_lines=160.0,
            test_to_code_ratio=1.28,
            di_fakes_count=5,
            mock_usage_count=0,
            avg_pr_turnaround_hours=1.5,
            scaffolding_commits_per_day=9.0,
            iteration_commits_per_day=5.0,
        ),
        CodingStyleProfile(
            repo_name="InnodataAgenticResearch/dov-bot",
            recorded_at="2026-11-01T02:00:00Z",
            avg_commit_lines=150.0,
            test_to_code_ratio=1.40,
            di_fakes_count=7,
            mock_usage_count=0,
            avg_pr_turnaround_hours=1.2,
            scaffolding_commits_per_day=10.0,
            iteration_commits_per_day=5.5,
        ),
    ):
        store.upsert_coding_style_profile(profile)

    for issue in (
        IssueCycleRecord(
            issue_id="INN-235",
            source="linear",
            title="Implement Dov-Bot (The Bear — Google L6 TPM) Custom ArtBOT",
            priority="P0",
            phase="scaffolding",
            status="closed",
            opened_at="2026-10-31T18:00:00Z",
            in_progress_at="2026-10-31T19:00:00Z",
            closed_at="2026-10-31T21:30:00Z",
            epic_id="INN-235",
            owner="Danny Rosen",
        ),
        IssueCycleRecord(
            issue_id="INN-237",
            source="linear",
            title="DovAnalyticsStore SQLite coding-style and cycle-time engine",
            priority="P1",
            phase="implementation",
            status="closed",
            opened_at="2026-10-31T20:00:00Z",
            in_progress_at="2026-10-31T20:30:00Z",
            closed_at="2026-10-31T22:30:00Z",
            epic_id="INN-235",
            owner="Danny Rosen",
        ),
        IssueCycleRecord(
            issue_id="INN-238",
            source="linear",
            title="LinearOverviewManager GraphQL board hygiene auditor",
            priority="P1",
            phase="implementation",
            status="in_progress",
            opened_at="2026-11-01T00:00:00Z",
            in_progress_at="2026-11-01T01:00:00Z",
            closed_at=None,
            epic_id="INN-235",
            owner="Danny Rosen",
        ),
        IssueCycleRecord(
            issue_id="makor-80w.5",
            source="beads",
            title="0-to-5 Bear Alarm Urgency Protocol & @rox-bot peer escalation",
            priority="P0",
            phase="verification",
            status="open",
            opened_at="2026-11-01T01:30:00Z",
            in_progress_at=None,
            closed_at=None,
            epic_id="INN-235",
            owner="Danny Rosen",
        ),
    ):
        store.upsert_issue_record(issue)
