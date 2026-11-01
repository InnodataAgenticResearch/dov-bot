"""
Pure dependency-injected Linear GraphQL client (`LinearOverviewManager`) for Dov-Bot.

Targets the Innodata Linear workspace (`https://linear.app/innodata-ai/team/INN/overview`,
team key `INN`, ID `829852d8-8a12-4875-93bd-5d1d1e08fe0b`):
- Audits active projects, team members, project board statuses, and `INN-*` issues.
- Detects missing items (projects without overview docs, active work missing Beads/Linear links,
  unowned P0/P1 issues, stale in-progress items) so Dov asks why they aren't on the board.
- Builds and updates the Linear Project/Team Overview markdown digest.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from dov_bot.bear_alarm import BEAR_EMOJI, BEAR_LEVEL_LABELS

LINEAR_GRAPHQL_URL = "https://api.linear.app/graphql"
INNODATA_TEAM_KEY = "INN"
INNODATA_TEAM_ID = "829852d8-8a12-4875-93bd-5d1d1e08fe0b"
INNODATA_TEAM_OVERVIEW_URL = "https://linear.app/innodata-ai/team/INN/overview"
_BEADS_ID_RE = re.compile(r"\b(makor-[a-z0-9]+(?:\.[a-z0-9]+)*)\b", re.IGNORECASE)


def extract_beads_id(text: str) -> str | None:
    """Extract a `makor-*` Beads identifier from an issue title or description."""
    match = _BEADS_ID_RE.search(text)
    return match.group(1).lower() if match else None


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
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
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
class LinearMember:
    """Team member on the Innodata (`INN`) Linear board."""

    member_id: str
    name: str
    email: str
    active: bool = True


@dataclass(frozen=True)
class LinearProject:
    """Project tracked on the Innodata (`INN`) Linear board."""

    project_id: str
    name: str
    state: str
    overview_markdown: str
    lead_name: str | None = None
    updated_at: str = ""


@dataclass(frozen=True)
class LinearIssue:
    """Issue tracked on the Innodata (`INN`) Linear board."""

    identifier: str
    title: str
    state_name: str
    priority: int
    assignee_name: str | None = None
    project_name: str | None = None
    beads_id: str | None = None
    hours_since_update: float = 0.0
    created_at: str = "2026-11-01T00:00:00Z"
    started_at: str | None = None
    completed_at: str | None = None
    updated_at: str = ""
    parent_identifier: str | None = None

    @property
    def is_closed(self) -> bool:
        """Return True if the issue is in a completed or canceled state."""
        return self.state_name.strip().lower() in {"done", "completed", "closed", "canceled"}


@dataclass(frozen=True)
class BoardAuditFinding:
    """A board hygiene gap detected by Dov (The Bear) with a direct TPM question."""

    category: str
    target: str
    question: str
    recommended_bear_level: int


@dataclass(frozen=True)
class BoardAuditReport:
    """Structured audit report of the Innodata (`INN`) Linear team board."""

    team_key: str
    team_id: str
    overview_url: str
    active_projects: tuple[LinearProject, ...]
    team_members: tuple[LinearMember, ...]
    issues: tuple[LinearIssue, ...]
    findings: tuple[BoardAuditFinding, ...]
    max_bear_level: int


class LinearOverviewManager:
    """Dependency-injected Linear GraphQL client and TPM board hygiene auditor."""

    def __init__(
        self,
        api_key: str = "",
        *,
        team_key: str = INNODATA_TEAM_KEY,
        team_id: str = INNODATA_TEAM_ID,
        graphql_url: str = LINEAR_GRAPHQL_URL,
        transport: HttpTransport | None = None,
        timeout: float = 15.0,
    ) -> None:
        self.api_key = api_key.strip()
        self.team_key = team_key
        self.team_id = team_id
        self.graphql_url = graphql_url
        self.transport: HttpTransport = UrllibHttpTransport() if transport is None else transport
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = self.api_key
        return headers

    def fetch_team_snapshot(
        self,
    ) -> tuple[list[LinearProject], list[LinearMember], list[LinearIssue]]:
        """Query the Linear GraphQL API for team `INN` projects, members, and issues."""
        query = """
        query TeamOverview($teamId: String!) {
          team(id: $teamId) {
            id
            key
            members {
              nodes { id name email active }
            }
            projects(first: 100) {
              nodes {
                id
                name
                state
                description
                updatedAt
                lead { name }
              }
            }
            issues(first: 250) {
              nodes {
                identifier
                title
                description
                priority
                createdAt
                startedAt
                completedAt
                canceledAt
                updatedAt
                state { name }
                assignee { name }
                project { name }
                parent { identifier }
              }
            }
          }
        }
        """
        resp = self.transport.post_json(
            self.graphql_url,
            payload={"query": query, "variables": {"teamId": self.team_id}},
            headers=self._headers(),
            timeout=self.timeout,
        )
        if resp.status_code >= 400:
            raise RuntimeError(
                f"Linear GraphQL request failed with HTTP {resp.status_code}: {resp.body[:200]}"
            )
        body = resp.json()
        if "errors" in body and body["errors"]:
            raise RuntimeError(f"Linear GraphQL returned errors: {body['errors']}")

        team_node = body.get("data", {}).get("team") or {}
        projects: list[LinearProject] = []
        for p in team_node.get("projects", {}).get("nodes", []):
            lead = p.get("lead") or {}
            projects.append(
                LinearProject(
                    project_id=str(p.get("id", "")),
                    name=str(p.get("name", "")),
                    state=str(p.get("state", "started")),
                    overview_markdown=str(p.get("description") or ""),
                    lead_name=str(lead["name"]) if lead.get("name") else None,
                    updated_at=str(p.get("updatedAt") or ""),
                )
            )

        members: list[LinearMember] = []
        for m in team_node.get("members", {}).get("nodes", []):
            members.append(
                LinearMember(
                    member_id=str(m.get("id", "")),
                    name=str(m.get("name", "")),
                    email=str(m.get("email", "")),
                    active=bool(m.get("active", True)),
                )
            )

        issues: list[LinearIssue] = []
        for item in team_node.get("issues", {}).get("nodes", []):
            state_obj = item.get("state") or {}
            assignee_obj = item.get("assignee") or {}
            project_obj = item.get("project") or {}
            parent_obj = item.get("parent") or {}
            title_str = str(item.get("title", ""))
            desc_str = str(item.get("description") or "")
            explicit_bead = str(item["beadsId"]) if item.get("beadsId") else None
            inferred_bead = explicit_bead or extract_beads_id(f"{title_str} {desc_str}")
            created_str = str(item.get("createdAt") or "2026-11-01T00:00:00Z")
            started_str = str(item["startedAt"]) if item.get("startedAt") else None
            done_raw = item.get("completedAt") or item.get("canceledAt")
            completed_str = str(done_raw) if done_raw else None
            updated_str = str(item.get("updatedAt") or "")
            issues.append(
                LinearIssue(
                    identifier=str(item.get("identifier", "")),
                    title=title_str,
                    state_name=str(state_obj.get("name", "Todo")),
                    priority=int(item.get("priority", 0)),
                    assignee_name=str(assignee_obj["name"]) if assignee_obj.get("name") else None,
                    project_name=str(project_obj["name"]) if project_obj.get("name") else None,
                    beads_id=inferred_bead,
                    hours_since_update=float(item.get("hoursSinceUpdate", 0.0)),
                    created_at=created_str,
                    started_at=started_str,
                    completed_at=completed_str,
                    updated_at=updated_str,
                    parent_identifier=str(parent_obj["identifier"])
                    if parent_obj.get("identifier")
                    else None,
                )
            )

        return projects, members, issues

    def audit_board(
        self,
        *,
        projects: Sequence[LinearProject],
        members: Sequence[LinearMember],
        issues: Sequence[LinearIssue],
        active_local_workstreams: Sequence[str] = (),
        stale_threshold_hours: float = 24.0,
    ) -> BoardAuditReport:
        """
        Audit projects, members, issues, and local workstreams for TPM hygiene gaps.
        """
        findings: list[BoardAuditFinding] = []

        for proj in projects:
            if not proj.overview_markdown.strip():
                findings.append(
                    BoardAuditFinding(
                        category="missing_project_overview",
                        target=proj.name,
                        question=(
                            f"Why does active Linear project '{proj.name}' have no overview "
                            f"document on the {self.team_key} board?"
                        ),
                        recommended_bear_level=2,
                    )
                )

        corpus = " ".join(
            [p.name.lower() for p in projects]
            + [p.overview_markdown.lower() for p in projects]
            + [i.title.lower() for i in issues]
        )
        compact_corpus = re.sub(r"[\s_-]+", "", corpus)
        for ws in active_local_workstreams:
            clean_ws = ws.strip()
            compact_ws = re.sub(r"[\s_-]+", "", clean_ws.lower())
            if clean_ws and clean_ws.lower() not in corpus and compact_ws not in compact_corpus:
                findings.append(
                    BoardAuditFinding(
                        category="untracked_active_work",
                        target=clean_ws,
                        question=(
                            f"Why isn't active workstream '{clean_ws}' on the Linear board "
                            f"with an {self.team_key}-* issue and linked bd bead?"
                        ),
                        recommended_bear_level=1,
                    )
                )

        for issue in issues:
            if issue.is_closed:
                continue

            if not issue.beads_id:
                findings.append(
                    BoardAuditFinding(
                        category="missing_beads_link",
                        target=issue.identifier,
                        question=(
                            f"Why is active Linear issue {issue.identifier} ('{issue.title}') "
                            f"missing a linked local bd bead ID?"
                        ),
                        recommended_bear_level=1,
                    )
                )

            if issue.priority in (1, 2) and not issue.assignee_name:
                findings.append(
                    BoardAuditFinding(
                        category="unowned_high_priority",
                        target=issue.identifier,
                        question=(
                            f"Why is high-priority issue {issue.identifier} ('{issue.title}') "
                            f"on the board without an assigned owner?"
                        ),
                        recommended_bear_level=3,
                    )
                )

            if (
                issue.state_name.strip().lower() == "in progress"
                and issue.hours_since_update > stale_threshold_hours
            ):
                hrs = issue.hours_since_update
                findings.append(
                    BoardAuditFinding(
                        category="stale_in_progress",
                        target=issue.identifier,
                        question=(
                            f"Why has in-progress issue {issue.identifier} ('{issue.title}') "
                            f"gone {hrs:.1f}h without a commit or board update?"
                        ),
                        recommended_bear_level=2,
                    )
                )

        max_bear = max((f.recommended_bear_level for f in findings), default=0)
        return BoardAuditReport(
            team_key=self.team_key,
            team_id=self.team_id,
            overview_url=INNODATA_TEAM_OVERVIEW_URL,
            active_projects=tuple(projects),
            team_members=tuple(members),
            issues=tuple(issues),
            findings=tuple(findings),
            max_bear_level=max_bear,
        )

    def render_team_overview_digest(self, report: BoardAuditReport) -> str:
        """Render the canonical Linear Project/Team Overview markdown digest."""
        level = report.max_bear_level
        label = BEAR_LEVEL_LABELS[level]
        header_prefix = "" if level == 0 else f"{BEAR_EMOJI * level} "

        lines = [
            f"# {header_prefix}Innodata ({report.team_key}) Linear Team & Project Overview Digest",
            "",
            f"- **Linear Team Key:** `{report.team_key}` (`{report.team_id}`)",
            f"- **Team Overview URL:** {report.overview_url}",
            f"- **Bear Alarm Status:** `{level}` Bear(s) — **{label}**",
            f"- **Active Team Members:** `{sum(1 for m in report.team_members if m.active)}`",
            "",
            "## 1. Active Projects",
            "",
            "| Project | State | Lead | Overview Doc Status |",
            "| :--- | :--- | :--- | :--- |",
        ]
        for proj in report.active_projects:
            lead = proj.lead_name or "Unassigned"
            doc_status = "Present" if proj.overview_markdown.strip() else "MISSING"
            lines.append(f"| **{proj.name}** | `{proj.state}` | {lead} | `{doc_status}` |")

        lines.extend(
            [
                "",
                "## 2. Linear Issue & Beads (`bd`) Board Coverage",
                "",
                "| Issue | Title | State | Priority | Owner | Bead (`bd`) |",
                "| :--- | :--- | :--- | :--- | :--- | :--- |",
            ]
        )
        for issue in report.issues:
            owner = issue.assignee_name or "UNOWNED"
            bead = issue.beads_id or "MISSING"
            lines.append(
                f"| `{issue.identifier}` | {issue.title} | `{issue.state_name}` "
                f"| `P{issue.priority}` | {owner} | `{bead}` |"
            )

        lines.extend(
            [
                "",
                "## 3. Dov's TPM Board Hygiene Questions",
                "",
            ]
        )
        if not report.findings:
            lines.append(
                "- All active projects, `INN-*` issues, and `bd` beads are "
                "100% accounted for on the board."
            )
        else:
            for finding in report.findings:
                bears = BEAR_EMOJI * finding.recommended_bear_level
                lines.append(
                    f"- {bears} **[{finding.category}] (`{finding.target}`):** {finding.question}"
                )

        return "\n".join(lines) + "\n"

    def update_project_overview(
        self,
        project_id: str,
        overview_markdown: str,
    ) -> bool:
        """Update a Linear project's overview description via the `projectUpdate` mutation."""
        mutation = """
        mutation UpdateProjectOverview($projectId: String!, $description: String!) {
          projectUpdate(id: $projectId, input: { description: $description }) {
            success
          }
        }
        """
        resp = self.transport.post_json(
            self.graphql_url,
            payload={
                "query": mutation,
                "variables": {
                    "projectId": project_id,
                    "description": overview_markdown,
                },
            },
            headers=self._headers(),
            timeout=self.timeout,
        )
        if resp.status_code >= 400:
            raise RuntimeError(
                f"Linear projectUpdate mutation failed with HTTP {resp.status_code}: "
                f"{resp.body[:200]}"
            )
        body = resp.json()
        return bool(body.get("data", {}).get("projectUpdate", {}).get("success", False))


def default_linear_snapshot() -> tuple[list[LinearProject], list[LinearMember], list[LinearIssue]]:
    """Return a deterministic baseline snapshot of the Innodata (`INN`) Linear board."""
    projects = [
        LinearProject(
            project_id="proj-artbot-ecosystem",
            name="Custom ArtBOT Ecosystem (artbot, marketing-bot, dov-bot, rox-bot)",
            state="started",
            overview_markdown=(
                "Pinned v0.1.0-artbot fleet with 100% line & branch coverage, "
                "shac API contract locking, and automated CI gates."
            ),
            lead_name="Danny Rosen",
            updated_at="2026-11-01T03:30:00Z",
        ),
    ]
    members = [
        LinearMember(
            member_id="usr-danny-rosen",
            name="Danny Rosen",
            email="drosen@innodata.com",
            active=True,
        ),
        LinearMember(
            member_id="usr-dov-bot",
            name="Dov (The Bear — Google L6 TPM)",
            email="dov-bot@innodata.com",
            active=True,
        ),
    ]
    issues = [
        LinearIssue(
            identifier="INN-235",
            title="Implement Dov-Bot (The Bear — Google L6 TPM) Custom ArtBOT",
            state_name="In Progress",
            priority=1,
            assignee_name="Danny Rosen",
            project_name="Custom ArtBOT Ecosystem (artbot, marketing-bot, dov-bot, rox-bot)",
            beads_id="makor-80w.5",
            hours_since_update=1.0,
        ),
        LinearIssue(
            identifier="INN-237",
            title="DovAnalyticsStore SQLite coding-style and cycle-time engine",
            state_name="Done",
            priority=1,
            assignee_name="Danny Rosen",
            project_name="Custom ArtBOT Ecosystem (artbot, marketing-bot, dov-bot, rox-bot)",
            beads_id="makor-80w.7",
            hours_since_update=0.5,
        ),
        LinearIssue(
            identifier="INN-238",
            title="LinearOverviewManager GraphQL board hygiene auditor",
            state_name="Done",
            priority=2,
            assignee_name="Danny Rosen",
            project_name="Custom ArtBOT Ecosystem (artbot, marketing-bot, dov-bot, rox-bot)",
            beads_id="makor-80w.8",
            hours_since_update=0.5,
        ),
        LinearIssue(
            identifier="INN-239",
            title="0-to-5 Bear Alarm Urgency Protocol & BEAR_ALARM_HELP.md",
            state_name="Done",
            priority=1,
            assignee_name="Danny Rosen",
            project_name="Custom ArtBOT Ecosystem (artbot, marketing-bot, dov-bot, rox-bot)",
            beads_id="makor-80w.9",
            hours_since_update=0.5,
        ),
        LinearIssue(
            identifier="INN-240",
            title="Cross-bot peer coordination between @dov-bot and @rox-bot (@ops-bot)",
            state_name="Done",
            priority=2,
            assignee_name="Danny Rosen",
            project_name="Custom ArtBOT Ecosystem (artbot, marketing-bot, dov-bot, rox-bot)",
            beads_id="makor-80w.10",
            hours_since_update=0.5,
        ),
        LinearIssue(
            identifier="INN-241",
            title=(
                "Verify 100% coverage & green GitHub Actions CI for InnodataAgenticResearch/dov-bot"
            ),
            state_name="In Progress",
            priority=1,
            assignee_name="Danny Rosen",
            project_name="Custom ArtBOT Ecosystem (artbot, marketing-bot, dov-bot, rox-bot)",
            beads_id="makor-80w.11",
            hours_since_update=0.5,
        ),
    ]
    return projects, members, issues
