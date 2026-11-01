# Dov-Bot repository security, secret prevention, and engineering standards policies for shac.

_CURL_PIPE_SHELL = r"curl\b[^|\n]*\|\s*(sudo\s+)?(ba|z)?sh\b"
_LIVE_WEBHOOK_URL = r"https://default[a-z0-9]+\.[a-z0-9]+\.environment\.api\.powerplatform\.com"
_UNEXPLAINED_PRAGMA = r"#\s*(pragma:\s*no\s*cover|noqa(:[^\s-]+)?|type:\s*ignore(\[[^\]]+\])?)\s*$"
_UNITTEST_MOCK = r"\b(unittest\.mock|from\s+unittest\s+import\s+mock)\b"
_MAX_OLD_SPACE_SIZE = r"--max-old-space-size\b"
_MUTABLE_BRIDGE_SERVICE_RE = r"(PYTHONPATH=[^\n]*%h/artbot/src|ExecStart=/usr/bin/python3\s+-m\s+artbot\.bridge)"

_FORBIDDEN_FILES = {
    ".env": True,
    "id_ed25519": True,
    "id_rsa": True,
    "authorized_keys": True,
    "HERMES.md": True,
    ".hermes.md": True,
}

_README_REQUIRED_HEADERS = [
    "## 1. Key Capabilities & Operating Invariants",
    "## 2. Creating a Microsoft Teams Workflows Webhook (Launch Your Own Bot)",
    "## 3. End-to-End Setup & Configuration",
    "## 4. Runtime Execution",
    "## 5. Repository Structure",
    "## 6. Quality Gates & Testing (`just check`)",
]

_AGENT_REQUIRED_HEADERS = [
    "## 1. Read First",
    "## 2. How an Agent Sets Up or Clones an ArtBOT Instance",
    "## 3. Interaction & Behavioral Invariants",
    "## 4. Engineering Standards (`STANDARDS.md`)",
    "## 5. Verification (`just check`)",
]

_STANDARDS_REQUIRED_HEADERS = [
    "# Engineering standards for agentic engineers",
    "## 1. Tests: near-100% deterministic coverage",
    "## 2. Linters are essential",
    "## 3. One command proves it",
    "## 4. Documentation is a Docusaurus site with a documented server",
    "## 5. Working rules for agents",
]

def no_secrets_or_env_files(ctx):
    """Ensure no live secrets, credentials, or .env files are tracked in git."""
    for path in ctx.scm.all_files(include_symlinks = True):
        base = path.rpartition("/")[2]
        if base in _FORBIDDEN_FILES or path.endswith(".pem") or path.endswith(".key"):
            ctx.emit.finding(
                level = "error",
                filepath = path,
                message = "Forbidden secret or credential file '%s' must never be tracked in git." % path,
            )

def no_tracked_beads(ctx):
    """Beads are local-only and must never be committed."""
    for path in ctx.scm.all_files(include_symlinks = True):
        if path.startswith(".beads/") or path.startswith(".beads."):
            ctx.emit.finding(
                level = "error",
                filepath = path,
                message = "Local beads repository (.beads/) must not be committed.",
            )

def no_curl_pipe_shell(ctx):
    """No `curl | sh` in scripts or code: all tools and packages must be pinned."""
    for path in ctx.scm.all_files(include_symlinks = True):
        if path.endswith(".md") or path.startswith("checks/"):
            continue
        raw = str(ctx.io.read_file(path))
        for idx, line in enumerate(raw.splitlines()):
            if ctx.re.match(_CURL_PIPE_SHELL, line):
                ctx.emit.finding(
                    level = "error",
                    filepath = path,
                    line = idx + 1,
                    message = "Never pipe network downloads directly into a shell.",
                )

def no_hardcoded_webhook_urls(ctx):
    """Ensure no live tenant Power Platform webhook URLs are hardcoded in the repository."""
    for path in ctx.scm.all_files(include_symlinks = True):
        if path.startswith("checks/"):
            continue
        raw = str(ctx.io.read_file(path))
        for idx, line in enumerate(raw.splitlines()):
            if ctx.re.match(_LIVE_WEBHOOK_URL, line):
                ctx.emit.finding(
                    level = "error",
                    filepath = path,
                    line = idx + 1,
                    message = "Hardcoded live Power Platform webhook URL detected. Load from TEAMS_WEBHOOK_URL instead.",
                )

def no_unexplained_pragma_or_disable(ctx):
    """Every inline exclusion (`# pragma: no cover - reason`) requires a reason comment on the same line (STANDARDS.md)."""
    for path in ctx.scm.all_files(glob = "*.py"):
        raw = str(ctx.io.read_file(path))
        for idx, line in enumerate(raw.splitlines()):
            if ctx.re.match(_UNEXPLAINED_PRAGMA, line):
                ctx.emit.finding(
                    level = "error",
                    filepath = path,
                    line = idx + 1,
                    message = "Inline exclusion or lint disable requires a '- <reason>' comment on the same line (STANDARDS.md).",
                )

def no_unittest_mock_in_tests(ctx):
    """Tests must use pure dependency injection and fakes, never unittest.mock (STANDARDS.md Section 1)."""
    for path in ctx.scm.all_files(glob = "tests/**/*.py"):
        raw = str(ctx.io.read_file(path))
        for idx, line in enumerate(raw.splitlines()):
            if ctx.re.match(_UNITTEST_MOCK, line):
                ctx.emit.finding(
                    level = "error",
                    filepath = path,
                    line = idx + 1,
                    message = "Use injected fakes (FakeHttpTransport, StringIO, tmp_path) instead of unittest.mock (STANDARDS.md).",
                )

def readme_and_agent_contract(ctx):
    """Enforce structured README.md, AGENT.md, STANDARDS.md, and config/PERSONA.md contract."""
    all_files = {f: True for f in ctx.scm.all_files(include_symlinks = True)}
    for doc_path, required_headers in [
        ("README.md", _README_REQUIRED_HEADERS),
        ("AGENT.md", _AGENT_REQUIRED_HEADERS),
        ("STANDARDS.md", _STANDARDS_REQUIRED_HEADERS),
        ("config/PERSONA.md", _STANDARDS_REQUIRED_HEADERS),
    ]:
        if doc_path not in all_files:
            ctx.emit.finding(
                level = "error",
                message = "%s is missing from the repository." % doc_path,
            )
            continue
        raw = str(ctx.io.read_file(doc_path))
        for header in required_headers:
            if raw.find(header) < 0:
                ctx.emit.finding(
                    level = "error",
                    filepath = doc_path,
                    message = "%s is missing required section '%s'." % (doc_path, header),
                )

def no_heap_limit_bandaids(ctx):
    """No `--max-old-space-size` workarounds in code or service units (STANDARDS.md)."""
    for path in ctx.scm.all_files(include_symlinks = True):
        if path.endswith(".md") or path.startswith("checks/"):
            continue
        raw = str(ctx.io.read_file(path))
        for idx, line in enumerate(raw.splitlines()):
            if ctx.re.match(_MAX_OLD_SPACE_SIZE, line):
                ctx.emit.finding(
                    level = "error",
                    filepath = path,
                    line = idx + 1,
                    message = "Do not inflate V8 heap limits with --max-old-space-size (STANDARDS.md). Fix the underlying memory retention or streaming bottleneck instead.",
                )

def no_mutable_bridge_systemd_units(ctx):
    """Forbid mutable PYTHONPATH=%h/artbot/src or ExecStart=/usr/bin/python3 -m artbot.bridge in *.service files."""
    for path in ctx.scm.all_files(include_symlinks = True):
        if not path.endswith(".service"):
            continue
        raw = str(ctx.io.read_file(path))
        for idx, line in enumerate(raw.splitlines()):
            if ctx.re.match(_MUTABLE_BRIDGE_SERVICE_RE, line):
                ctx.emit.finding(
                    level = "error",
                    filepath = path,
                    line = idx + 1,
                    message = "Systemd service units must use immutable %h/.nix-profile/bin/artbot-bridge instead of mutable PYTHONPATH=%h/artbot/src or /usr/bin/python3 -m artbot.bridge.",
                )

def register_policy_checks():
    for impl in [
        no_secrets_or_env_files,
        no_tracked_beads,
        no_curl_pipe_shell,
        no_hardcoded_webhook_urls,
        no_unexplained_pragma_or_disable,
        no_unittest_mock_in_tests,
        no_heap_limit_bandaids,
        no_mutable_bridge_systemd_units,
        readme_and_agent_contract,
    ]:
        shac.register_check(impl)
