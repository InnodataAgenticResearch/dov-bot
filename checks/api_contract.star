# Custom ArtBOT Upstream Pinning & Public API Surface Lock (`checks/api_contract.star`).
#
# Prevents custom ArtBOT repositories from importing private modules (`artbot._*`),
# internal submodules (`from artbot.<submodule> import ...`), private underscore-prefixed
# symbols from `artbot`, or symbols not listed in `UPSTREAM_ARTBOT.json`'s `public_api_allowlist`.

_PRIVATE_ARTBOT_SUBMODULE_RE = r"^\s*(from\s+artbot\.[a-zA-Z0-9_]+|import\s+artbot\.[a-zA-Z0-9_]+)\b"
_HEX40_RE = r"^[0-9a-f]{40}$"

def _strip_comment(line):
    idx = line.find("#")
    if idx >= 0:
        return line[:idx]
    return line

def upstream_artbot_pin_valid(ctx):
    """Verify UPSTREAM_ARTBOT.json pins a valid upstream repo, release tag, and 40-char commit hash."""
    all_files = {f: True for f in ctx.scm.all_files(include_symlinks = True)}
    if "UPSTREAM_ARTBOT.json" not in all_files:
        ctx.emit.finding(
            level = "error",
            message = "UPSTREAM_ARTBOT.json is required in custom ArtBOT repositories to track the upstream tag and commit hash.",
        )
        return

    raw = str(ctx.io.read_file("UPSTREAM_ARTBOT.json"))
    data = json.decode(raw)
    if type(data) != "dict":
        ctx.emit.finding(
            level = "error",
            filepath = "UPSTREAM_ARTBOT.json",
            message = "UPSTREAM_ARTBOT.json must be a JSON object.",
        )
        return

    repo = data.get("upstream_repo", "")
    tag = data.get("upstream_tag", "")
    commit = data.get("upstream_commit", "")
    allowlist = data.get("public_api_allowlist", [])

    if not repo or not repo.endswith("/artbot"):
        ctx.emit.finding(
            level = "error",
            filepath = "UPSTREAM_ARTBOT.json",
            message = "UPSTREAM_ARTBOT.json must specify upstream_repo ending with '/artbot'.",
        )
    if not tag or not tag.startswith("v"):
        ctx.emit.finding(
            level = "error",
            filepath = "UPSTREAM_ARTBOT.json",
            message = "UPSTREAM_ARTBOT.json must specify a versioned upstream_tag starting with 'v' (e.g. 'v0.2.0-artbot').",
        )
    if not commit or not ctx.re.match(_HEX40_RE, str(commit)):
        ctx.emit.finding(
            level = "error",
            filepath = "UPSTREAM_ARTBOT.json",
            message = "UPSTREAM_ARTBOT.json must specify a full 40-character hex upstream_commit SHA.",
        )
    if type(allowlist) != "list" or len(allowlist) == 0:
        ctx.emit.finding(
            level = "error",
            filepath = "UPSTREAM_ARTBOT.json",
            message = "UPSTREAM_ARTBOT.json must declare a non-empty public_api_allowlist.",
        )

def no_private_artbot_apis(ctx):
    """Forbid importing internal artbot submodules, private underscore-prefixed symbols, or symbols outside public_api_allowlist."""
    all_files = {f: True for f in ctx.scm.all_files(include_symlinks = True)}
    allowed_symbols = None
    if "UPSTREAM_ARTBOT.json" in all_files:
        pin_data = json.decode(str(ctx.io.read_file("UPSTREAM_ARTBOT.json")))
        if type(pin_data) == "dict" and type(pin_data.get("public_api_allowlist")) == "list":
            allowed_symbols = {str(s): True for s in pin_data["public_api_allowlist"]}

    for path in ctx.scm.all_files(glob = "*.py"):
        raw = str(ctx.io.read_file(path))
        in_multiline = False
        for idx, line in enumerate(raw.splitlines()):
            if ctx.re.match(_PRIVATE_ARTBOT_SUBMODULE_RE, line):
                ctx.emit.finding(
                    level = "error",
                    filepath = path,
                    line = idx + 1,
                    message = "Custom ArtBOTs must import only from top-level public `artbot` (`from artbot import ...`), never internal submodules.",
                )
                continue

            code_line = _strip_comment(line).strip()
            segment = ""
            if in_multiline:
                segment = code_line
                if ")" in code_line:
                    in_multiline = False
                    segment = code_line.partition(")")[0]
            elif ctx.re.match(r"^\s*from\s+artbot\s+import\s+", line):
                after_import = code_line.partition("import")[2].strip()
                if after_import.startswith("("):
                    after_open = after_import[1:]
                    if ")" in after_open:
                        segment = after_open.partition(")")[0]
                    else:
                        in_multiline = True
                        segment = after_open
                else:
                    segment = after_import

            if segment:
                for part in segment.split(","):
                    sym = part.strip().partition(" as ")[0].strip()
                    if not sym:
                        continue
                    if sym.startswith("_"):
                        ctx.emit.finding(
                            level = "error",
                            filepath = path,
                            line = idx + 1,
                            message = "Custom ArtBOTs must not import private underscore-prefixed symbols from `artbot`.",
                        )
                    elif allowed_symbols != None and sym not in allowed_symbols:
                        ctx.emit.finding(
                            level = "error",
                            filepath = path,
                            line = idx + 1,
                            message = "Symbol '%s' imported from `artbot` is not in UPSTREAM_ARTBOT.json public_api_allowlist." % sym,
                        )

def register_api_contract_checks():
    shac.register_check(upstream_artbot_pin_valid)
    shac.register_check(no_private_artbot_apis)
