# AGENT.md — Autonomous Agent Operating Guide & Custom ArtBOT Engineering Contract

This file governs autonomous coding agents (Hermes Agent, Claude Code, Codex) and engineers working in or deploying from the `dov-bot` repository.

`dov-bot` (**Dov — The Bear**) is a **Custom ArtBOT** built on top of the reusable upstream [`InnodataAgenticResearch/artbot`](https://github.com/InnodataAgenticResearch/artbot) foundation (`v0.1.0-artbot`). Dov operates as a **Google L6 Technical Program Manager (TPM)** governing Linear board hygiene (`https://linear.app/innodata-ai/team/INN/overview`), repository coding-style and cycle-time analytics (`DovAnalyticsStore`), cross-bot peer escalation with `@rox-bot` (`@ops-bot`), and the **0-to-5 Bear Alarm Urgency Protocol**.

---

## 1. Read First

- `README.md`: Overview of Dov-Bot's TPM capabilities, 0-to-5 Bear Alarm Urgency Protocol summary, Microsoft Teams Workflows webhook setup, and CLI execution commands.
- `BEAR_ALARM_HELP.md`: Full specification of the **0-to-5 Bear Alarm Urgency Protocol** (`0` bears = zero bear emojis; `1`–`5` bears = `🐻` to `🐻🐻🐻🐻🐻` **5-ALARM FIRE!**) and `@rox-bot` (`@ops-bot`) cross-bot escalation rules.
- `UPSTREAM_ARTBOT.json` & `checks/api_contract.star`: Upstream ArtBOT version pin (`v0.1.0-artbot`, commit `e28cf26c2b71e4f081ce17f3815fae31375a98d3`) and the public API surface lock enforced by `shac`.
- `config/PERSONA.md`: Dov-Bot's Google L6 TPM identity (`@dov-bot` / `@tpm-bot`), Linear (`INN-*`) + Beads (`bd`) auditing workflow, and `STANDARDS.md`.
- `checks/policy.star` & `shac.star`: Machine-enforced security, secret-hygiene, API-contract, and coding-standard gates.

---

## 2. How an Agent Sets Up or Clones an ArtBOT Instance

When asked by a human to provision `dov-bot` (or another custom Teams webhook bot extending upstream `artbot`) on a machine:

1. **Verify Upstream ArtBOT Pin (`UPSTREAM_ARTBOT.json` & `checks/api_contract.star`):**
   - `dov-bot` pins upstream `https://github.com/InnodataAgenticResearch/artbot` at tag `v0.1.0-artbot` (`e28cf26c2b71e4f081ce17f3815fae31375a98d3`) in `UPSTREAM_ARTBOT.json`.
   - Custom ArtBOT code under `src/dov_bot/` must import **only** from the top-level public `artbot` package (`from artbot import ArtbotConfig, HttpTransport, ...`) listed in `public_api_allowlist`.
   - `checks/api_contract.star` (`no_private_artbot_apis` and `upstream_artbot_pin_valid`) blocks any import of internal submodules (`from artbot.<submodule> import ...`) or private underscore-prefixed symbols (`from artbot import _...`), guaranteeing that upgrading to a newer tagged `artbot` release never breaks `dov-bot`.
   - Verify the pin at any time with:
     ```bash
     just upstream-status
     ```

2. **Create the Hermes Profile:**
   ```bash
   hermes profile create --clone dov-bot \
     --description "Dov-Bot (The Bear): Google L6 TPM, Linear Board Auditor & 0-to-5 Bear Alarm Protocol"
   ```

3. **Configure Environment Credentials (`~/.hermes/profiles/dov-bot/.env`):**
   - Never hardcode webhook URLs, bearer tokens, or Linear API keys in source files, tests, or git-tracked configs.
   - Copy `config/env.example` to `~/.hermes/profiles/dov-bot/.env` (`chmod 600`).
   - Populate `TEAMS_WEBHOOK_URL`, `LINEAR_API_KEY`, `LINEAR_TEAM_ID` (`829852d8-8a12-4875-93bd-5d1d1e08fe0b`), and generate a unique `API_SERVER_KEY`:
     ```bash
     python3 -c "import secrets; print('API_SERVER_KEY=' + secrets.token_urlsafe(32))" >> ~/.hermes/profiles/dov-bot/.env
     ```

4. **Run Linear Audits, Velocity Reports, and Bear Alarm Checks:**
   ```bash
   just audit-linear
   just velocity-report
   just help-page
   ```

---

## 3. Interaction & Behavioral Invariants

1. **Speak Only When Spoken To or Raising a 3+ Bear Alarm (`@dov-bot`, `@tpm-bot`, or `@artbot`):**
   - Mention detection checks for case-insensitive `@dov-bot\b`, `@tpm-bot\b`, or `@artbot\b` triggers.
   - Never post an outbound Teams webhook message for routine unmentioned chatter unless escalating a `3+` Bear Alarm delivery blocker.
2. **Strict 0-to-5 Bear Alarm Emoji Discipline (`src/dov_bot/bear_alarm.py`):**
   - At level `0` (all green / on track), messages contain **zero** `🐻` emojis so channel members never mistake a status update for an alarm.
   - Levels `1` through `5` prefix messages with `🐻` repeated `1` to `5` times, culminating in `🐻🐻🐻🐻🐻` (**5-ALARM FIRE!**).
3. **Always Reply In-Thread (Never Start New Root Chats):**
   - Outbound Adaptive Card payloads must attach `replyToId` and `messageId` whenever a parent `message_id` is present.
4. **Peer Coordination with `@rox-bot` (`@ops-bot`):**
   - When a `3+` bear blocker involves GCP VMs, systemd bridges, or infrastructure, Dov emits a structured handoff query to `@rox-bot` (`@ops-bot`) and ingests `@rox-bot` telemetry to recalculate delivery ETA risk.
5. **Never Commit Secrets or Hardcoded Webhook URLs:**
   - `checks/policy.star` blocks `.env`, `.pem`, `.key`, private keys, `.beads/`, and any hardcoded live Power Platform webhook URLs.

---

## 4. Engineering Standards (`STANDARDS.md`)

Every change to this repository must adhere to the following non-negotiable rules:

1. **100% Deterministic Line & Branch Coverage:**
   - Enforced by `pytest -p randomly --cov=dov_bot --cov-branch --cov-report=term-missing --cov-fail-under=100`.
   - Never lower `fail_under = 100`.
   - Every `# pragma: no cover` exclusion must have an inline `- <reason>` comment on the same line (e.g. `# pragma: no cover - module entrypoint`), enforced by `no_unexplained_pragma_or_disable` in `checks/policy.star`.
2. **Pure Dependency Injection (No `unittest.mock`):**
   - Inject `HttpTransport` (`FakeHttpTransport` in tests, `UrllibHttpTransport` in production), SQLite paths (`tmp_path`), `environ` mappings, and `io.StringIO` streams.
   - Importing `unittest.mock` inside `tests/` is forbidden by `no_unittest_mock_in_tests` in `checks/policy.star`.
   - The test suite must pass in random order (`-p randomly`) twice in a row.
3. **Public ArtBOT API Contract Lock (`checks/api_contract.star`):**
   - Never import private `artbot._*` symbols or internal `artbot.<submodule>` modules. Only import from top-level `artbot` symbols listed in `UPSTREAM_ARTBOT.json`.
4. **Zero Linter or Type Warnings:**
   - `ruff format --check .`
   - `ruff check .`
   - `mypy --strict src tests`
5. **No Runtime Heap-Limit Band-Aids (`--max-old-space-size`):**
   - Never paper over memory leaks or OOM crashes by inflating runtime heap limits (`NODE_OPTIONS=--max-old-space-size=...`), enforced by `no_heap_limit_bandaids` in `checks/policy.star`.
6. **Shac Policy & Starlark Tests:**
   - Every policy rule in `checks/policy.star` and `checks/api_contract.star` has a corresponding unit test in `checks/policy_test.star`.
   - Run `shac test` and `shac check --all` before every commit.

---

## 5. Verification (`just check`)

Before claiming any task is complete or pushing to `origin`, run:

```bash
just check
```

If running on a Nix-enabled host without global Python tools on `PATH`, run inside the repo's dev shell:

```bash
nix develop -c just check
```

Both local `just check` and `.github/workflows/ci.yml` execute the exact same sequence:
1. `ruff format --check .`
2. `ruff check .`
3. `mypy --strict src tests`
4. `shac test`
5. `shac check --all`
6. `pytest` (run twice in random order with `100%` line and branch coverage gate).
