# Dov-Bot (Custom ArtBOT) — Dov (The Bear), Google L6 Technical Program Manager

**Dov-Bot** (`@dov-bot` / `@tpm-bot`) is a custom [ArtBOT](https://github.com/InnodataAgenticResearch/artbot) instance (`v0.2.0-artbot`) built for **Innodata Agentic Research**. Named **Dov** (Hebrew for *"The Bear"*), he operates as a **Google L6 Technical Program Manager (TPM)** governing the **Innodata Linear workspace** (`https://linear.app/innodata-ai/team/INN/overview`, team key `INN`, ID `829852d8-8a12-4875-93bd-5d1d1e08fe0b`), repository coding-style and cycle-time analytics, cross-bot coordination with `@rox-bot` (`@ops-bot`), and the [**0-to-5 Bear Alarm Urgency Protocol**](BEAR_ALARM_HELP.md).

## 1. Key Capabilities & Operating Invariants

1. **Upstream ArtBOT Public Contract Lock (`UPSTREAM_ARTBOT.json`):** Pins `InnodataAgenticResearch/artbot` at tag `v0.2.0-artbot` (`6c63513a9f92887aa13ddd7f562e82eb32e87873`). `checks/api_contract.star` forbids importing private `artbot` submodules or underscore-prefixed symbols.
2. **Isolated SQLite Velocity & Coding-Style Analytics (`src/dov_bot/analytics.py`):**
   - `DovAnalyticsStore` persists repository coding-style profiles (commit granularity, test-to-code ratio, pure dependency injection vs. mock usage, PR turnaround hours, and new-project scaffolding velocity vs. existing-repo iteration velocity).
   - Tracks Beads (`bd`) and Linear (`INN-*`) issue cycle times (`open` -> `in_progress` -> `closed`), completion velocity by priority (`P0`–`P4`) and phase, and deterministic ETA forecasts for open epics.
3. **Linear Project & Board Hygiene Auditor (`src/dov_bot/linear_sync.py`):**
   - Pure dependency-injected GraphQL client (`LinearOverviewManager`) for team `INN` (`829852d8-8a12-4875-93bd-5d1d1e08fe0b`).
   - Audits active projects, team members, project board statuses, and `INN-*` issues; detects projects without overview docs, untracked active workstreams, unowned `P0`/`P1` issues, and stale in-progress items (`>24h`), prompting Dov to ask directly why they aren't on the board.
4. **0-to-5 Bear Alarm Urgency Protocol & `@rox-bot` Peer Coordination (`src/dov_bot/bear_alarm.py`):**
   - Implements the 0-to-5 Bear Alarm scale (`0` bears = zero `🐻` emojis in text; `1` bear = `🐻` minor observation; `2` bears = `🐻🐻` emerging drift; `3` bears = `🐻🐻🐻` active blocker; `4` bears = `🐻🐻🐻🐻` delivery jeopardy; `5` bears = `🐻🐻🐻🐻🐻` **5-ALARM FIRE!**).
   - Formats peer handoff queries for `@rox-bot` (`@ops-bot`) on `3+` bear infrastructure blockers and recalculates delivery risk when `@rox-bot` reports GCP VM/service anomalies.

## 2. Creating a Microsoft Teams Workflows Webhook (Launch Your Own Bot)

To connect **Dov-Bot** to a Microsoft Teams channel without requiring Entra ID tenant-wide admin consent:

1. In Microsoft Teams, open the target channel, click **`...` (More options) -> Workflows**.
2. Select the **"Post to a channel when a webhook request is received"** template.
3. Name the workflow `Dov-Bot Adaptive Card Bridge`, authenticate with your M365 account, and select the target Team and Channel.
4. Copy the generated Power Automate HTTP POST URL and store it in your runtime `.env` file (never committed to git) as:
   ```bash
   TEAMS_WEBHOOK_URL="https://<tenant>.<region>.environment.api.powerplatform.com:443/powerautomate/automations/direct/workflows/..."
   ```
5. Open the workflow in [make.powerautomate.com](https://make.powerautomate.com) and set **"Who can trigger the flow"** to **Anyone** so the bridge can post Adaptive Cards using the signed URL.

## 3. End-to-End Setup & Configuration

1. Enter the reproducible Nix development environment:
   ```bash
   nix develop
   ```
2. Configure runtime environment variables in `~/.hermes/profiles/dov-bot/.env`:
   ```bash
   LINEAR_API_KEY="<your-linear-api-key>"
   TEAMS_WEBHOOK_URL="https://<tenant>.<region>.environment.api.powerplatform.com/..."
   DOV_ANALYTICS_DB_PATH="/var/lib/dov-bot/dov_analytics.sqlite3"
   ```
3. Verify upstream ArtBOT pin and render the Bear Alarm Help Page:
   ```bash
   PYTHONPATH=src python3 -m dov_bot.cli upstream-status
   PYTHONPATH=src python3 -m dov_bot.cli help-page
   ```

## 4. Runtime Execution

- **Evaluate a 0-to-5 Bear Alarm Urgency Signal:**
  ```bash
  PYTHONPATH=src python3 -m dov_bot.cli bear-check --blockers 1 --infra-anomaly "gcp-vm-makor: disk 95%"
  ```
- **Generate Velocity & Epic ETA Forecast Report:**
  ```bash
  PYTHONPATH=src python3 -m dov_bot.cli velocity-report --seed --epic INN-235
  ```
- **Audit the Innodata (`INN`) Linear Team Board:**
  ```bash
  # Deterministic offline audit:
  PYTHONPATH=src python3 -m dov_bot.cli audit-linear --workstream dov-bot

  # Live GraphQL audit when LINEAR_API_KEY is set:
  PYTHONPATH=src python3 -m dov_bot.cli audit-linear --live
  ```

## 5. Repository Structure

```text
dov-bot/
├── AGENT.md                                  # Operational guide for autonomous agents
├── BEAR_ALARM_HELP.md                        # 0-to-5 Bear Alarm Urgency Protocol spec
├── README.md                                 # Capabilities, webhook setup & CLI guide
├── STANDARDS.md                              # Engineering standards (100% coverage)
├── UPSTREAM_ARTBOT.json                      # Pinned upstream artbot tag & allowlist
├── config/
│   ├── PERSONA.md                            # Dov (The Bear) Google L6 TPM persona
│   └── env.example                           # Runtime environment template
├── checks/                                   # Starlark shac policy & contract rules
├── src/dov_bot/                              # Typed Python package (analytics, linear, bear, cli)
└── tests/                                    # 100% coverage deterministic test suite
```

## 6. Quality Gates & Testing (`just check`)

Every change is verified by `just check` (and GitHub Actions CI), running in strict order:

```bash
ruff format --check .
ruff check .
mypy --strict src tests
shac test
shac check --all
pytest
pytest
```
